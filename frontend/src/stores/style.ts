import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '../api/style'
import type { ArtifactDiffItem, ChatMessage, StyleBundle, StyleTokens, TokenUsage } from '../types/style'

export interface ArchiveItem {
  id: number
  name: string
  accent: string
  updated_at: string
}

/** 一轮产物包改动的可视化对比 */
export interface PendingDiff {
  baselineCss: string
  baselineHtml: string
  diff: ArtifactDiffItem[]
  reply: string
}

/**
 * V2 事实源：完整自由产物包。
 * CSS / HTML / Prompt 都由后端产物包提供，前端只负责展示和交互。
 */
export const useStyleStore = defineStore('style', () => {
  const bundle = ref<StyleBundle | null>(null)
  const tokens = ref<StyleTokens | null>(null) // 兼容旧 TokenPanel，V2 不再写入
  const css = ref('')
  const previewHtml = ref('')
  const messages = ref<ChatMessage[]>([])
  const busy = ref(false)
  const archives = ref<ArchiveItem[]>([])
  const activeArchiveName = ref<string | null>(null)
  const pendingDiff = ref<PendingDiff | null>(null)

  let writeQueue: Promise<unknown> = Promise.resolve()
  let cssSeq = 0
  let currentAbort: AbortController | null = null
  let activeBotIndex: number | null = null
  let generationStartedAt = 0
  let lastUsage: TokenUsage | null = null

  function emptyUsage(): TokenUsage {
    return {
      available: false,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      cached_tokens: 0,
      cache_miss_tokens: 0,
      cache_write_tokens: 0,
      reasoning_tokens: 0,
      raw: null,
    }
  }

  function markStopped() {
    const msg = activeBotIndex === null ? null : messages.value[activeBotIndex]
    if (!msg || msg.stopped) return
    msg.streaming = false
    msg.stopped = true
    msg.text = '已停止生成。'
    msg.usage = lastUsage ?? emptyUsage()
    msg.duration_ms = Date.now() - generationStartedAt
    pendingDiff.value = null
  }

  function stopGeneration() {
    if (!currentAbort) return
    currentAbort.abort()
    markStopped()
  }

  function queueWrite<T>(job: () => Promise<T>): Promise<T> {
    const result = writeQueue.then(job, job)
    writeQueue = result.catch(() => undefined)
    return result
  }

  async function refreshCss() {
    const seq = ++cssSeq
    const next = await api.fetchPreviewCss()
    if (seq !== cssSeq) return
    css.value = next.css
    previewHtml.value = next.previewHtml
  }

  async function init() {
    bundle.value = await api.fetchCurrent()
    await refreshCss()
  }

  function history() {
    return messages.value.map(m => ({ role: m.role, text: m.text }))
  }

  /** 只清空对话记录，不改动当前产物包 */
  function clearMessages() {
    messages.value = []
    pendingDiff.value = null
    activeBotIndex = null
  }

  async function parsePrompt(prompt: string) {
    if (!prompt.trim() || busy.value) return
    const baselineCss = css.value
    const baselineHtml = previewHtml.value
    messages.value.push({ role: 'user', text: prompt })
    pendingDiff.value = null
    const startedAt = Date.now()
    const botIndex = messages.value.push({
      role: 'bot', text: '', streaming: true, started_at: startedAt, trace: [],
    }) - 1
    activeBotIndex = botIndex
    generationStartedAt = startedAt
    lastUsage = null
    currentAbort = new AbortController()
    busy.value = true
    try {
      await api.chatStream(prompt, [], (ev) => {
        const msg = messages.value[botIndex]
        if (!msg) return
        if (ev.type === 'delta') {
          msg.raw = (msg.raw ?? '') + (ev.delta ?? '')
        } else if (ev.type === 'reasoning') {
          msg.reasoning = (msg.reasoning ?? '') + (ev.delta ?? '')
        } else if (ev.type === 'usage') {
          lastUsage = ev.usage ?? null
        } else if (ev.type === 'done') {
          msg.text = ev.reply ?? ''
          msg.mode = ev.mode
          msg.diff = ev.diff?.length ? ev.diff : undefined
          msg.usage = ev.usage
          msg.duration_ms = ev.duration_ms ?? (Date.now() - generationStartedAt)
          msg.streaming = false
          if (ev.bundle) bundle.value = ev.bundle
          activeArchiveName.value = null
          if (ev.diff?.length) {
            pendingDiff.value = {
              baselineCss,
              baselineHtml,
              diff: ev.diff,
              reply: ev.reply ?? '',
            }
          }
        } else if (ev.type === 'error') {
          msg.text = `生成失败：${ev.message ?? '未知错误'}`
          msg.streaming = false
        } else {
          msg.trace = msg.trace ?? []
          msg.trace.push(ev)
        }
      }, 'rewrite', currentAbort.signal)
      await refreshCss()
    } catch (err) {
      const aborted = currentAbort?.signal.aborted
        || (err instanceof DOMException && err.name === 'AbortError')
      if (aborted) {
        markStopped()
      } else {
        const msg = messages.value[botIndex]
        if (msg) {
          msg.text = '生成失败，检查后端服务是否在 8300 端口运行。'
          msg.streaming = false
        }
      }
    } finally {
      const msg = messages.value[botIndex]
      if (msg?.streaming) msg.streaming = false
      currentAbort = null
      activeBotIndex = null
      busy.value = false
    }
  }

  async function send(message: string) {
    if (!message.trim() || busy.value) return
    const baselineCss = css.value
    const baselineHtml = previewHtml.value
    const hist = history()
    messages.value.push({ role: 'user', text: message })
    pendingDiff.value = null
    const startedAt = Date.now()
    const botIndex = messages.value.push({
      role: 'bot', text: '', streaming: true, started_at: startedAt, trace: [],
    }) - 1
    activeBotIndex = botIndex
    generationStartedAt = startedAt
    lastUsage = null
    currentAbort = new AbortController()
    busy.value = true
    try {
      await api.chatStream(message, hist, (ev) => {
        const msg = messages.value[botIndex]
        if (!msg) return
        if (ev.type === 'delta') {
          msg.raw = (msg.raw ?? '') + (ev.delta ?? '')
        } else if (ev.type === 'reasoning') {
          msg.reasoning = (msg.reasoning ?? '') + (ev.delta ?? '')
        } else if (ev.type === 'usage') {
          lastUsage = ev.usage ?? null
        } else if (ev.type === 'done') {
          msg.text = ev.reply ?? ''
          msg.mode = ev.mode
          msg.diff = ev.diff?.length ? ev.diff : undefined
          msg.usage = ev.usage
          msg.duration_ms = ev.duration_ms ?? (Date.now() - generationStartedAt)
          msg.streaming = false
          if (ev.bundle) bundle.value = ev.bundle
          if (ev.diff?.length) {
            pendingDiff.value = {
              baselineCss,
              baselineHtml,
              diff: ev.diff,
              reply: ev.reply ?? '',
            }
          }
        } else if (ev.type === 'error') {
          msg.text = `生成失败：${ev.message ?? '未知错误'}`
          msg.streaming = false
        } else {
          msg.trace = msg.trace ?? []
          msg.trace.push(ev)
        }
      }, undefined, currentAbort.signal)
      await refreshCss()
    } catch (err) {
      const aborted = currentAbort?.signal.aborted
        || (err instanceof DOMException && err.name === 'AbortError')
      if (aborted) {
        markStopped()
      } else {
        const msg = messages.value[botIndex]
        if (msg) {
          msg.text = '对话失败，检查后端服务是否在 8300 端口运行。'
          msg.streaming = false
        }
      }
    } finally {
      const msg = messages.value[botIndex]
      if (msg?.streaming) msg.streaming = false
      currentAbort = null
      activeBotIndex = null
      busy.value = false
    }
  }

  function acceptDiff() {
    if (!pendingDiff.value) return
    pendingDiff.value = null
    messages.value.push({ role: 'bot', text: '已接受本轮修改，可随时用「撤销」回退。' })
  }

  async function rejectDiff() {
    if (!pendingDiff.value || busy.value) return
    busy.value = true
    try {
      const res = await queueWrite(() => api.undo())
      if (res.ok && res.bundle) {
        bundle.value = res.bundle
        await refreshCss()
        messages.value.push({ role: 'bot', text: '已拒绝本轮修改，已回到基准产物包。' })
      } else {
        messages.value.push({ role: 'bot', text: '拒绝失败：没有可撤销的改动。' })
      }
      pendingDiff.value = null
    } finally {
      busy.value = false
    }
  }

  async function undo() {
    if (busy.value) return
    pendingDiff.value = null
    busy.value = true
    try {
      const res = await queueWrite(() => api.undo())
      if (res.ok && res.bundle) bundle.value = res.bundle
      messages.value.push({
        role: 'bot',
        text: res.ok ? '已撤销最近一次改动。' : '没有可撤销的改动了。',
      })
      await refreshCss()
    } finally {
      busy.value = false
    }
  }

  /** V2 不再提供 token 面板调参；保留签名避免旧组件破坏。 */
  async function patch(_fn: (t: StyleTokens) => void) {
    void _fn
  }

  async function reset() {
    pendingDiff.value = null
    bundle.value = await queueWrite(() => api.resetStyle())
    activeArchiveName.value = null
    messages.value.push({ role: 'bot', text: '已重置为「系统默认产物包」。' })
    await refreshCss()
  }

  async function useBlankTemplate() {
    pendingDiff.value = null
    bundle.value = await queueWrite(() => api.useBlankTemplate())
    activeArchiveName.value = null
    messages.value.push({ role: 'bot', text: '已切换到「空模板」产物包基线。' })
    await refreshCss()
  }

  async function refreshArchives() {
    const res = await api.listArchives()
    if (res.ok) archives.value = res.items
    else archives.value = []
    return res
  }

  async function saveArchive(name: string) {
    const res = await queueWrite(() => api.saveArchive(name))
    if (res.ok) {
      activeArchiveName.value = name
      messages.value.push({ role: 'bot', text: `已存档「${name}」，同名覆盖；改名即另存为。` })
      await refreshArchives()
    }
    return res
  }

  async function loadArchive(id: number) {
    pendingDiff.value = null
    const res = await queueWrite(() => api.loadArchive(id))
    if (res.ok && res.bundle) {
      bundle.value = res.bundle
      activeArchiveName.value = res.bundle.meta.name
      messages.value.push({ role: 'bot', text: `已加载档案「${res.bundle.meta.name}」。` })
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
    bundle, tokens, css, previewHtml, messages, busy, archives, activeArchiveName, pendingDiff,
    init, refreshCss, parsePrompt, send, clearMessages, stopGeneration, undo, acceptDiff, rejectDiff,
    patch, reset, useBlankTemplate,
    refreshArchives, saveArchive, loadArchive, deleteArchive,
  }
})
