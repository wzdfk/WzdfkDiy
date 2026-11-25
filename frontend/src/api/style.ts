import axios from 'axios'
import type { ArtifactDiffItem, ChatStreamEvent, StyleBundle, StyleTokens } from '../types/style'

const http = axios.create({ baseURL: '/api', timeout: 300000 })  // 产物包生成输出较大，放宽到 5 分钟

/** 单次请求携带的 LLM 配置，来自浏览器本地存储 */
export interface LlmRuntime {
  provider: LlmProvider
  base_url: string
  model: string
  reasoning_effort: ReasoningEffort
  api_key?: string
}

function withRuntime(llm?: LlmRuntime) {
  return llm ? { llm } : {}
}

/** 当前自由产物包 */
export const fetchCurrent = () => http.get<StyleBundle>('/style/current').then(r => r.data)

/** 覆盖当前产物包（兼容旧调用） */
export const saveCurrent = (bundle: StyleBundle | StyleTokens) => http.post('/style/current', bundle)

/** 预览用真实产物：CSS + HTML */
export const fetchPreviewCss = () =>
  http.get<{ css: string; preview_html: string }>('/style/preview-css').then(r => ({
    css: r.data.css,
    previewHtml: r.data.preview_html,
  }))

/** 提示词 → 完整自由产物包 */
export const parsePrompt = (prompt: string, llm?: LlmRuntime) =>
  http.post<StyleBundle>('/style/parse', { prompt, ...withRuntime(llm) }).then(r => r.data)

/** 对话优化 → { bundle, diff, reply } */
export const chat = (
  message: string,
  history: { role: string; text: string }[] = [],
  llm?: LlmRuntime,
) =>
  http.post<{ bundle: StyleBundle; diff: ArtifactDiffItem[]; reply: string }>(
    '/style/chat', { message, history, ...withRuntime(llm) },
  ).then(r => r.data)

/** 流式对话：解析 SSE 事件并逐条回调 */
export async function chatStream(
  message: string,
  history: { role: string; text: string }[],
  onEvent: (event: ChatStreamEvent) => void,
  mode?: 'rewrite' | 'adjust',
  signal?: AbortSignal,
  llm?: LlmRuntime,
) {
  const body = { message, history, ...(mode ? { mode } : {}), ...withRuntime(llm) }
  const res = await fetch('/api/style/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`SSE 失败: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const emit = (chunk: string) => {
    const data = chunk.split('\n')
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trim())
      .join('')
    if (!data) return
    try {
      onEvent(JSON.parse(data) as ChatStreamEvent)
    } catch {
      onEvent({ type: 'error', message: '流式事件解析失败' })
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) emit(block)
  }
  if (buffer.trim()) emit(buffer)
}

/** 撤销最近一次改动 → { ok, bundle, error? } */
export const undo = () =>
  http.post<{ ok: boolean; bundle: StyleBundle; error?: string }>('/style/undo').then(r => r.data)

/** 当前档案存入 MySQL（同名覆盖）→ { ok, id, name } */
export const saveArchive = (name: string) =>
  http.post<{ ok: boolean; id?: number; name?: string; error?: string }>('/style/archives', { name }).then(r => r.data)

/** 档案列表 → { ok, items: [{id,name,accent,updated_at}] } */
export const listArchives = () =>
  http.get<{ ok: boolean; items: { id: number; name: string; accent: string; updated_at: string }[]; error?: string }>(
    '/style/archives',
  ).then(r => r.data)

/** 加载档案为当前产物包 → { ok, bundle } */
export const loadArchive = (id: number) =>
  http.post<{ ok: boolean; bundle: StyleBundle; error?: string }>(`/style/archives/${id}/load`).then(r => r.data)

/** 删除档案 → { ok } */
export const deleteArchive = (id: number) =>
  http.delete<{ ok: boolean; error?: string }>(`/style/archives/${id}`).then(r => r.data)

// ---------- LLM 设置 ----------

export type LlmProvider = 'zhipu' | 'deepseek' | 'openai' | 'moonshot' | 'qwen' | 'custom'
export type ReasoningEffort = 'auto' | 'none' | 'low' | 'medium' | 'high' | 'max'

export interface LlmSettings {
  provider: LlmProvider
  base_url: string
  model: string
  reasoning_effort: ReasoningEffort
  key_masked: string
  has_key: boolean
  enabled: boolean
}

export interface ReasoningOption {
  value: ReasoningEffort
  label: string
  accepted?: boolean
  latency_ms?: number
  error?: string
}

export interface ProviderPreset {
  value: LlmProvider
  label: string
  base_url: string
  model: string
  models: string[]
  reasoning_options: ReasoningOption[]
  hint?: string
}

export const LLM_PROVIDERS: ProviderPreset[] = [
  {
    value: 'zhipu',
    label: '智谱 GLM',
    base_url: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
    model: 'glm-5.3-flash',
    models: ['glm-5.3-flash', 'glm-4-flash', 'glm-4-plus', 'glm-4-air', 'glm-4-airx'],
    reasoning_options: [
      { value: 'auto', label: 'default' },
      { value: 'low', label: 'low' },
      { value: 'high', label: 'high' },
      { value: 'max', label: 'max' },
    ],
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    base_url: 'https://api.deepseek.com/v1/chat/completions',
    model: 'deepseek-flash',
    models: ['deepseek-flash', 'deepseek-v4-pro'],
    reasoning_options: [
      { value: 'auto', label: '不指定（跟随模型默认）' },
      { value: 'none', label: '关闭思考 none' },
      { value: 'low', label: '低强度 low' },
      { value: 'high', label: '高强度 high' },
      { value: 'max', label: '最大强度 max' },
    ],
  },
  {
    value: 'openai',
    label: 'OpenAI / Azure OpenAI 兼容',
    base_url: 'https://api.openai.com/v1/chat/completions',
    model: 'gpt-5',
    models: ['gpt-5', 'gpt-5-mini', 'gpt-4o', 'gpt-4o-mini', 'o3-mini'],
    reasoning_options: [
      { value: 'auto', label: '不指定（跟随模型默认）' },
      { value: 'none', label: '极简 minimal' },
      { value: 'low', label: '低强度 low' },
      { value: 'medium', label: '中强度 medium' },
      { value: 'high', label: '高强度 high' },
      { value: 'max', label: '极高 xhigh' },
    ],
  },
  {
    value: 'moonshot',
    label: 'Moonshot / Kimi',
    base_url: 'https://api.moonshot.cn/v1/chat/completions',
    model: 'kimi-k3.1-pro',
    models: ['kimi-k3.1-pro', 'kimi-k3.1-pro-highspeed', 'kimi-k3'],
    reasoning_options: [{ value: 'auto', label: '不指定（跟随模型默认）' }],
    hint: '未验证思考强度字段，默认不指定。',
  },
  {
    value: 'qwen',
    label: '通义千问 OpenAI 兼容',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
    model: 'qwen3.7-plus',
    models: ['qwen3.7-plus', 'qwen3.8-flash', 'qwen4-max'],
    reasoning_options: [{ value: 'auto', label: '不指定（跟随模型默认）' }],
    hint: '未验证思考强度字段，默认不指定。',
  },
  {
    value: 'custom',
    label: '自定义 OpenAI 兼容',
    base_url: '',
    model: '',
    models: [],
    reasoning_options: [{ value: 'auto', label: '不指定（跟随模型默认）' }],
    hint: '自定义接口默认不指定思考强度。',
  },
]

export function getProviderPreset(provider: LlmProvider): ProviderPreset {
  return LLM_PROVIDERS.find(p => p.value === provider) ?? LLM_PROVIDERS[LLM_PROVIDERS.length - 1]
}

export function inferLlmProvider(baseUrl: string, model: string): LlmProvider {
  const text = `${baseUrl} ${model}`.toLowerCase()
  if (text.includes('bigmodel') || text.includes('zhipu') || text.includes('glm')) return 'zhipu'
  if (text.includes('deepseek')) return 'deepseek'
  if (text.includes('openai') || text.includes('azure')) return 'openai'
  if (text.includes('moonshot') || text.includes('kimi')) return 'moonshot'
  if (text.includes('dashscope') || text.includes('qwen')) return 'qwen'
  return 'custom'
}

export interface ReasoningProbeResult {
  ok: boolean
  model?: string
  options: ReasoningOption[]
  error?: string
}

/** 读服务端默认值（门户模式无 Key） */
export const getLlmSettings = () =>
  http.get<LlmSettings>('/settings/llm').then(r => r.data)

/** 实测当前模型支持的思考强度（配置仅用于本次请求） */
export const probeReasoning = (llm: LlmRuntime) =>
  http.post<ReasoningProbeResult>('/settings/llm/probe-reasoning', llm).then(r => r.data)

/** 测试连接（配置仅用于本次请求） */
export const testLlm = (llm: LlmRuntime) =>
  http.post<{ ok: boolean; latency_ms?: number; sample?: string; error?: string }>(
    '/settings/llm/test', llm,
  ).then(r => r.data)

export interface ModelListResult {
  ok: boolean
  models: string[]
  url?: string
  error?: string
}

/** 从供应商 OpenAI 兼容 /models 接口拉取可用模型 */
export const listLlmModels = (data: { base_url: string; api_key?: string }) =>
  http.post<ModelListResult>('/settings/llm/models', data).then(r => r.data)

/** 重置为系统默认产物包 */
export const resetStyle = () => http.post<StyleBundle>('/style/reset').then(r => r.data)

/** 切换到零装饰产物包基线 */
export const useBlankTemplate = () => http.post<StyleBundle>('/style/blank').then(r => r.data)

/** 导出固定结构产物包 zip（返回 blob，供文件选择器写入） */
export async function exportZip(): Promise<Blob> {
  const res = await http.post('/style/export', null, { responseType: 'blob' })
  return res.data as Blob
}

export interface ExportSaveResult {
  ok: boolean
  path: string
  file_name: string
  error?: string
}

/** 由本地后端把产物包写入指定目录 */
export const saveExportToDir = (outputDir: string) =>
  http.post<ExportSaveResult>('/style/export/save', { output_dir: outputDir }).then(r => r.data)

export interface PickDirResult {
  ok: boolean
  selected: boolean
  path: string
  error?: string
}

/** 打开本地原生目录选择框 */
export const pickDirectory = () =>
  http.post<PickDirResult>('/settings/pick-dir').then(r => r.data)
