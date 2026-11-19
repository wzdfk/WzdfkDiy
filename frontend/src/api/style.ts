import axios from 'axios'
import type { StyleTokens } from '../types/style'

const http = axios.create({ baseURL: '/api', timeout: 90000 })  // LLM 调用放宽到 90s

/** 当前风格档案 */
export const fetchCurrent = () => http.get<StyleTokens>('/style/current').then(r => r.data)

/** 覆盖当前档案（面板改动后同步后端会话） */
export const saveCurrent = (tokens: StyleTokens) => http.post('/style/current', tokens)

/** 预览用真实生成 CSS（所见即所导） */
export const fetchPreviewCss = () =>
  http.get<{ css: string }>('/style/preview-css').then(r => r.data.css)

/** 提示词 → 初始风格（V0 词典解析，V1 走 LLM） */
export const parsePrompt = (prompt: string) =>
  http.post<StyleTokens>('/style/parse', { prompt }).then(r => r.data)

/** 对话优化 → { tokens, diff, reply }（history 供后端 LLM 上下文，V1 用） */
export const chat = (
  message: string,
  history: { role: string; text: string }[] = [],
) =>
  http.post<{ tokens: StyleTokens; diff: { path: string; from: string | number; to: string | number; reason: string }[]; reply: string }>(
    '/style/chat', { message, history },
  ).then(r => r.data)

/** 撤销最近一次改动 → { ok, tokens, error? } */
export const undo = () =>
  http.post<{ ok: boolean; tokens: StyleTokens; error?: string }>('/style/undo').then(r => r.data)

/** 当前档案存入 MySQL（同名覆盖）→ { ok, id, name } */
export const saveArchive = (name: string) =>
  http.post<{ ok: boolean; id?: number; name?: string; error?: string }>('/style/archives', { name }).then(r => r.data)

/** 档案列表 → { ok, items: [{id,name,accent,updated_at}] } */
export const listArchives = () =>
  http.get<{ ok: boolean; items: { id: number; name: string; accent: string; updated_at: string }[]; error?: string }>(
    '/style/archives',
  ).then(r => r.data)

/** 加载档案为当前风格 → { ok, tokens } */
export const loadArchive = (id: number) =>
  http.post<{ ok: boolean; tokens: StyleTokens; error?: string }>(`/style/archives/${id}/load`).then(r => r.data)

/** 删除档案 → { ok } */
export const deleteArchive = (id: number) =>
  http.delete<{ ok: boolean; error?: string }>(`/style/archives/${id}`).then(r => r.data)

// ---------- LLM 设置 ----------

export interface LlmSettings {
  base_url: string
  model: string
  key_masked: string
  has_key: boolean
  enabled: boolean
}

/** 读设置（key 掩码） */
export const getLlmSettings = () =>
  http.get<LlmSettings>('/settings/llm').then(r => r.data)

/** 保存设置（api_key 空串 = 保留已存 key） */
export const saveLlmSettings = (data: { base_url: string; model: string; api_key?: string }) =>
  http.put<LlmSettings>('/settings/llm', data).then(r => r.data)

/** 测试连接 → { ok, latency_ms?, sample?, error? } */
export const testLlm = () =>
  http.post<{ ok: boolean; latency_ms?: number; sample?: string; error?: string }>(
    '/settings/llm/test',
  ).then(r => r.data)

/** 重置为系统默认风格 */
export const resetStyle = () => http.post<StyleTokens>('/style/reset').then(r => r.data)

/** 切换到零装饰空模板 */
export const useBlankTemplate = () => http.post<StyleTokens>('/style/blank').then(r => r.data)

/** 导出三件套 zip */
export async function exportZip(fileName: string): Promise<void> {
  const res = await http.post('/style/export', null, { responseType: 'blob' })
  const url = URL.createObjectURL(res.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  a.click()
  URL.revokeObjectURL(url)
}
