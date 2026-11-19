import { defineStore } from 'pinia'
import { ref, toRaw } from 'vue'
import * as api from '../api/style'
import type { ChatMessage, DiffItem, StyleTokens } from '../types/style'

export interface ArchiveItem {
  id: number
  name: string
  accent: string
  updated_at: string
}

/**
 * 风格 tokens —— 全局唯一事实源。
 * 预览 iframe 加载的就是后端按这份 tokens 生成的真实 CSS。
 */
export const useStyleStore = defineStore('style', () => {
  const tokens = ref<StyleTokens | null>(null)
  const css = ref('')
  const messages = ref<ChatMessage[]>([])
  const busy = ref(false)
  const archives = ref<ArchiveItem[]>([])
  /** 当前会话对应的档案名：决定存档弹窗默认值（覆盖 = 同名保存，改名 = 另存为） */
  const activeArchiveName = ref<string | null>(null)

  // 后端写操作串行化；CSS 响应只接受最新一次，避免拖拽滑杆时乱序覆盖
  let writeQueue: Promise<unknown> = Promise.resolve()
  let cssSeq = 0

  function queueWrite<T>(job: () => Promise<T>): Promise<T> {
    const result = writeQueue.then(job, job)
    writeQueue = result.catch(() => undefined)
    return result
  }

  async function refreshCss() {
    const seq = ++cssSeq
    const next = await api.fetchPreviewCss()
    if (seq === cssSeq) css.value = next
  }

  async function init() {
    tokens.value = await api.fetchCurrent()
    await refreshCss()
  }

  /** 对话历史（role+text），随 chat 发给后端 */
  function history() {
    return messages.value.map(m => ({ role: m.role, text: m.text }))
  }

  async function parsePrompt(prompt: string) {
    if (!prompt.trim()) return
    messages.value.push({ role: 'user', text: prompt })
    busy.value = true
    try {
      tokens.value = await queueWrite(() => api.parsePrompt(prompt))
      activeArchiveName.value = null
      messages.value.push({
        role: 'bot',
        text: `已按提示词生成初始风格「${tokens.value.meta.name}」。可以继续对话调整，比如「再柔和一点」「硬朗一些」，或到维度面板精调。`,
      })
      await refreshCss()
    } catch {
      messages.value.push({ role: 'bot', text: '生成失败，检查后端服务是否在 8300 端口运行。' })
    } finally {
      busy.value = false
    }
  }

  async function send(message: string) {
    if (!message.trim()) return
    messages.value.push({ role: 'user', text: message })
    busy.value = true
    try {
      const hist = history()
      const res = await queueWrite(() => api.chat(message, hist))
      tokens.value = res.tokens
      const diff: DiffItem[] = res.diff
      messages.value.push({ role: 'bot', text: res.reply, diff: diff.length ? diff : undefined })
      await refreshCss()
    } catch {
      messages.value.push({ role: 'bot', text: '对话失败，检查后端服务是否在 8300 端口运行。' })
    } finally {
      busy.value = false
    }
  }

  /** 撤销最近一次改动（对话/面板/加载档案均可撤销） */
  async function undo() {
    if (storeBusyGuard()) return
    busy.value = true
    try {
      const res = await queueWrite(() => api.undo())
      tokens.value = res.tokens
      messages.value.push({
        role: 'bot',
        text: res.ok ? '已撤销最近一次改动。' : '没有可撤销的改动了。',
      })
      await refreshCss()
    } finally {
      busy.value = false
    }
  }

  function storeBusyGuard() {
    return busy.value
  }

  /** 面板改动：本地修改 tokens → 同步后端 → 刷新预览 */
  async function patch(fn: (t: StyleTokens) => void) {
    if (!tokens.value) return
    const next = structuredClone(toRaw(tokens.value))
    fn(next)
    tokens.value = next
    await queueWrite(() => api.saveCurrent(next))
    await refreshCss()
  }

  async function reset() {
    tokens.value = await queueWrite(() => api.resetStyle())
    activeArchiveName.value = null
    messages.value.push({ role: 'bot', text: '已重置为「系统默认风格」。' })
    await refreshCss()
  }

  async function useBlankTemplate() {
    tokens.value = await queueWrite(() => api.useBlankTemplate())
    activeArchiveName.value = null
    messages.value.push({ role: 'bot', text: '已切换到「空模板」：无圆角、无投影、中性灰的朴素基线，可从维度面板开始打造个人风格。' })
    await refreshCss()
  }

  // ---------- 档案持久化（MySQL） ----------

  async function refreshArchives() {
    const res = await api.listArchives()
    if (res.ok) archives.value = res.items
    else archives.value = []
    return res
  }

  async function saveArchive(name: string) {
    if (tokens.value && tokens.value.meta.name !== name) {
      const next = structuredClone(toRaw(tokens.value))
      next.meta.name = name
      tokens.value = next
      await queueWrite(() => api.saveCurrent(next))
    }
    const res = await queueWrite(() => api.saveArchive(name))
    if (res.ok) {
      activeArchiveName.value = name
      messages.value.push({ role: 'bot', text: `已存档「${name}」，同名覆盖；改名即另存为。` })
      await refreshArchives()
    }
    return res
  }

  async function loadArchive(id: number) {
    const res = await queueWrite(() => api.loadArchive(id))
    if (res.ok) {
      tokens.value = res.tokens
      activeArchiveName.value = res.tokens.meta.name
      messages.value.push({ role: 'bot', text: `已加载档案「${res.tokens.meta.name}」到当前风格。` })
      await refreshCss()
    }
    return res
  }

  async function deleteArchive(id: number) {
    const res = await api.deleteArchive(id)
    if (res.ok) await refreshArchives()
    return res
  }

  return {
    tokens, css, messages, busy, archives, activeArchiveName,
    init, refreshCss, parsePrompt, send, undo, patch, reset, useBlankTemplate,
    refreshArchives, saveArchive, loadArchive, deleteArchive,
  }
})
