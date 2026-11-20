import axios from 'axios'
import type { ArtifactDiffItem, ChatStreamEvent, StyleBundle, StyleTokens } from '../types/style'

const http = axios.create({ baseURL: '/api', timeout: 300000 })  // 产物包生成输出较大，放宽到 5 分钟

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
export const parsePrompt = (prompt: string) =>
  http.post<StyleBundle>('/style/parse', { prompt }).then(r => r.data)

/** 对话优化 → { bundle, diff, reply } */
export const chat = (
  message: string,
  history: { role: string; text: string }[] = [],
) =>
  http.post<{ bundle: StyleBundle; diff: ArtifactDiffItem[]; reply: string }>(
    '/style/chat', { message, history },
  ).then(r => r.data)

/** 流式对话：解析 SSE 事件并逐条回调 */
export async function chatStream(
  message: string,
  history: { role: string; text: string }[],
  onEvent: (event: ChatStreamEvent) => void,
  mode?: 'rewrite' | 'adjust',
  signal?: AbortSignal,
) {
  const res = await fetch('/api/style/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(mode ? { message, history, mode } : { message, history }),
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
  reasoning_options: ReasoningOption[]
  hint?: string
}

export const LLM_PROVIDERS: ProviderPreset[] = [
  {
    value: 'zhipu',
    label: '智谱 GLM',
    base_url: 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
    model: 'glm-5.3-flash',
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
    model: 'deepseek-chat',
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
    model: 'moonshot-v1-8k',
    reasoning_options: [{ value: 'auto', label: '不指定（跟随模型默认）' }],
    hint: '未验证思考强度字段，默认不指定。',
  },
  {
    value: 'qwen',
    label: '通义千问 OpenAI 兼容',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
    model: 'qwen-plus',
    reasoning_options: [{ value: 'auto', label: '不指定（跟随模型默认）' }],
    hint: '未验证思考强度字段，默认不指定。',
  },
  {
    value: 'custom',
    label: '自定义 OpenAI 兼容',
    base_url: '',
    model: '',
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

/** 读设置（key 掩码） */
export const getLlmSettings = () =>
  http.get<LlmSettings>('/settings/llm').then(r => r.data)

/** 保存设置（api_key 空串 = 保留已存 key） */
export const saveLlmSettings = (data: {
  provider: LlmProvider
  base_url: string
  model: string
  api_key?: string
  reasoning_effort?: ReasoningEffort
}) => http.put<LlmSettings>('/settings/llm', data).then(r => r.data)

/** 实测当前模型支持的思考强度 */
export const probeReasoning = () =>
  http.post<ReasoningProbeResult>('/settings/llm/probe-reasoning').then(r => r.data)

/** 测试连接 → { ok, latency_ms?, sample?, error? } */
export const testLlm = () =>
  http.post<{ ok: boolean; latency_ms?: number; sample?: string; error?: string }>(
    '/settings/llm/test',
  ).then(r => r.data)

/** 重置为系统默认产物包 */
export const resetStyle = () => http.post<StyleBundle>('/style/reset').then(r => r.data)

/** 切换到零装饰产物包基线 */
export const useBlankTemplate = () => http.post<StyleBundle>('/style/blank').then(r => r.data)

/** 导出固定结构产物包 zip */
export async function exportZip(fileName: string): Promise<void> {
  const res = await http.post('/style/export', null, { responseType: 'blob' })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
}
