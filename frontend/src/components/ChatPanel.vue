<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useStyleStore } from '../stores/style'
import type { ChatMessage, TokenUsage } from '../types/style'
import PromptComposer from './PromptComposer.vue'

const store = useStyleStore()
const listEl = ref<HTMLElement | null>(null)
const now = ref(Date.now())
let tickTimer: number | null = null

onMounted(() => {
  tickTimer = window.setInterval(() => {
    if (store.messages.some(m => m.streaming)) now.value = Date.now()
  }, 250)
})

onUnmounted(() => {
  if (tickTimer !== null) window.clearInterval(tickTimer)
})

async function submitPrompt(text: string) {
  if (!text.trim() || store.busy) return
  if (store.messages.length === 0) {
    await store.parsePrompt(text)
  } else {
    await store.send(text)
  }
  await nextTick()
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior: 'smooth' })
}

watch(() => store.messages.length, async () => {
  await nextTick()
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior: 'smooth' })
})

const STAGE_LABELS: Record<string, string> = {
  thinking: '系统思考',
  generating: '模型输出',
  organizing: '整理中',
  validating: '字段校验',
  applying: '生成方案',
  done: '完成',
}

function stageLabel(ev: { type: string; stage?: string; label?: string }) {
  if (ev.type === 'reasoning') return '模型推理'
  if (ev.type === 'delta') return '模型输出'
  return ev.label ?? STAGE_LABELS[ev.stage ?? ''] ?? '过程'
}

function fmtNumber(value?: number) {
  return new Intl.NumberFormat('zh-CN').format(value ?? 0)
}

function fmtDuration(ms?: number) {
  if (ms === undefined || ms === null) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function replyTokens(usage?: TokenUsage) {
  if (!usage) return 0
  return Math.max(usage.completion_tokens - usage.reasoning_tokens, 0)
}

function cacheRate(usage?: TokenUsage) {
  if (!usage?.available || usage.prompt_tokens <= 0) return 0
  return Math.min(100, Math.round(usage.cached_tokens / usage.prompt_tokens * 1000) / 10)
}

function elapsedMs(msg: ChatMessage) {
  if (msg.role !== 'bot') return undefined
  if (!msg.streaming && msg.duration_ms !== undefined) return msg.duration_ms
  if (msg.started_at !== undefined) return Math.max(0, now.value - msg.started_at)
  return undefined
}

function fmtElapsed(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  if (total < 60) return `${total}s`
  return `${Math.floor(total / 60)}m${String(total % 60).padStart(2, '0')}s`
}

function elapsedLabel(msg: ChatMessage) {
  const ms = elapsedMs(msg)
  if (ms === undefined) return ''
  if (msg.streaming) return fmtElapsed(ms)
  if (msg.stopped) return `已停止 ${fmtElapsed(ms)}`
  return `已完成 ${fmtElapsed(ms)}`
}
</script>

<template>
  <div class="chat-panel">
    <div ref="listEl" class="msg-list">
      <div v-if="store.messages.length === 0" class="chat-empty">
        <span class="fd-label">START HERE</span>
        <p>
          描述你想要的风格，比如：<br>
          <em>「天青色主题，柔和干净，低饱和，适度圆角，纤细线条，无强烈渐变，简约清爽」</em>
        </p>
        <p style="margin-top:8px;">发送后进入多轮优化，随时说「再柔和一点」这类模糊指令。</p>
      </div>

      <template v-for="(msg, i) in store.messages" :key="i">
        <div class="bubble" :class="msg.role">
          <div class="bubble-text" :class="{ 'is-streaming': msg.streaming }">
            <div class="bubble-main">
              <span v-if="msg.stopped" class="stopped-tag">已停止</span>
              <span v-if="msg.mode === 'artifact'" class="mode-tag">完整产物</span>
              <span v-if="msg.streaming" class="streaming-label">
                <span class="loading-ring" aria-hidden="true"></span>
                <span class="streaming-text" :data-text="msg.text || '生成中…'">{{ msg.text || '生成中…' }}</span>
              </span>
              <span v-else>{{ msg.text }}</span>
            </div>
            <span
              v-if="elapsedMs(msg) !== undefined"
              class="elapsed-badge"
              :class="{ live: msg.streaming }"
            >{{ elapsedLabel(msg) }}</span>
          </div>
          <details v-if="msg.trace?.length || msg.raw || msg.reasoning" class="trace">
            <summary>查看思考 / 整理过程</summary>
            <div class="trace-body">
              <div v-for="(t, idx) in msg.trace" :key="idx" class="trace-line" :class="t.stage || t.type">
                <span class="trace-tag">{{ stageLabel(t) }}</span>
                <span>{{ t.thought || t.label || '' }}</span>
              </div>
              <div v-if="msg.reasoning" class="trace-reasoning">
                <span class="trace-tag">模型推理</span>
                <span>{{ msg.reasoning }}</span>
              </div>
              <pre v-if="msg.raw" class="trace-raw">{{ msg.raw }}</pre>
            </div>
          </details>
          <details
            v-if="msg.role === 'bot' && (msg.usage || msg.duration_ms !== undefined)"
            class="usage-card"
          >
            <summary>
              <span v-if="msg.stopped" class="usage-pill stopped-pill">已停止</span>
              <span class="usage-pill">Tokens {{ fmtNumber(msg.usage?.total_tokens ?? 0) }}</span>
              <span class="usage-pill">耗时 {{ fmtDuration(msg.duration_ms) }}</span>
              <span v-if="msg.usage?.provider" class="usage-provider">{{ msg.usage.provider }}</span>
            </summary>
            <div class="usage-body">
              <template v-if="msg.usage?.available">
                <div class="usage-row total">
                  <span>Token 消耗明细</span>
                  <b>总计 {{ fmtNumber(msg.usage.total_tokens) }}</b>
                </div>
                <div class="usage-group">
                  <div class="usage-row"><span><i class="dot input"></i>输入</span><b>{{ fmtNumber(msg.usage.prompt_tokens) }}</b></div>
                  <div class="usage-row sub"><span><i class="dot hit"></i>缓存命中</span><b>{{ fmtNumber(msg.usage.cached_tokens) }}</b></div>
                  <div class="usage-row sub"><span><i class="dot miss"></i>缓存未命中</span><b>{{ fmtNumber(msg.usage.cache_miss_tokens) }}</b></div>
                  <div class="usage-row sub"><span><i class="dot write"></i>缓存写入</span><b>{{ fmtNumber(msg.usage.cache_write_tokens) }}</b></div>
                </div>
                <div class="usage-group">
                  <div class="usage-row"><span><i class="dot output"></i>输出</span><b>{{ fmtNumber(msg.usage.completion_tokens) }}</b></div>
                  <div class="usage-row sub"><span><i class="dot reason"></i>思考过程</span><b>{{ fmtNumber(msg.usage.reasoning_tokens) }}</b></div>
                  <div class="usage-row sub"><span><i class="dot reply"></i>回复内容</span><b>{{ fmtNumber(replyTokens(msg.usage)) }}</b></div>
                </div>
                <div v-if="msg.usage.prompt_tokens > 0" class="cache-rate">
                  <span>缓存命中率</span>
                  <b>{{ cacheRate(msg.usage) }}%</b>
                  <div class="cache-bar"><span :style="{ width: cacheRate(msg.usage) + '%' }"></span></div>
                </div>
              </template>
              <div v-else class="usage-empty">
                {{ msg.stopped ? '已停止生成；供应商未返回本次 token usage，仅显示到停止时的耗时。' : '当前供应商未返回 token usage，仅显示耗时。' }}
              </div>
            </div>
          </details>
          <div v-if="msg.diff?.length" class="diff-card">
            <div class="fd-label" style="margin-bottom:6px;">本轮修改（{{ msg.diff.length }} 项）</div>
            <div v-for="d in msg.diff" :key="d.path + d.to" class="diff-item">
              <code>{{ d.path }}</code>
              <span class="diff-arrow">{{ d.from }} → <b>{{ d.to }}</b></span>
              <span class="diff-reason">{{ d.reason }}</span>
            </div>
          </div>
        </div>
      </template>

      <div v-if="store.busy && !store.messages.some(m => m.streaming)" class="bubble bot typing">
        <span class="streaming-label">
          <span class="loading-ring" aria-hidden="true"></span>
          <span class="streaming-text" data-text="思考中…">思考中…</span>
        </span>
      </div>
    </div>

    <PromptComposer @submit="submitPrompt" @stop="store.stopGeneration()" />
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.msg-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-empty {
  color: var(--fd-ink-600);
  font-size: 13.5px;
  padding: 12px 4px;
}
.chat-empty em { color: var(--fd-accent-600); font-style: normal; background: var(--fd-accent-50); padding: 1px 6px; border-radius: 6px; }

.bubble {
  max-width: 92%;
  padding: 10px 14px;
  font-size: 13.5px;
  border-radius: 10px 10px 10px 3px;
  border: var(--fd-border);
  background: var(--fd-surface);
  box-shadow: var(--fd-e1);
  white-space: pre-wrap;
  word-break: break-all;
}
.bubble.user {
  align-self: flex-end;
  border-radius: 10px 10px 3px 10px;
  background: var(--fd-accent-100);
  border-color: var(--fd-accent-300);
}
.bubble.typing { color: var(--fd-ink-400); }
.bubble-text {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.bubble-main {
  flex: 1;
  min-width: 0;
}
.bubble-text.is-streaming {
  align-items: center;
  min-height: 18px;
}
.elapsed-badge {
  flex: none;
  align-self: flex-start;
  margin-top: 1px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid var(--fd-accent-200);
  background: var(--fd-accent-50);
  color: var(--fd-accent-700);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.elapsed-badge.live {
  animation: fd-elapsed-pulse 1.4s ease-in-out infinite;
}
@keyframes fd-elapsed-pulse {
  0%, 100% { opacity: .65; }
  50% { opacity: 1; }
}
.streaming-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.loading-ring {
  width: 12px;
  height: 12px;
  flex: none;
  border-radius: 50%;
  border: 2px solid var(--fd-accent-200);
  border-top-color: var(--fd-accent-600);
  animation: fd-loading-spin .75s linear infinite;
}
.streaming-text {
  position: relative;
  display: inline-block;
  color: var(--fd-ink-400);
  font-weight: 600;
}
.streaming-text::after {
  content: attr(data-text);
  position: absolute;
  inset: 0 auto 0 0;
  width: 0;
  overflow: hidden;
  white-space: nowrap;
  color: var(--fd-accent-600);
  text-shadow: 0 0 8px var(--fd-accent-200);
  animation: fd-stream-sweep 1.8s ease-in-out infinite;
  pointer-events: none;
}
@keyframes fd-loading-spin {
  to { transform: rotate(360deg); }
}
@keyframes fd-stream-sweep {
  0% { width: 0; opacity: .25; }
  48% { width: 100%; opacity: 1; }
  100% { width: 100%; opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .loading-ring,
  .streaming-text::after { animation: none; }
  .streaming-text::after { width: 100%; opacity: .45; }
}
.mode-tag,
.stopped-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 5px;
  background: var(--fd-accent-100);
  color: var(--fd-accent-700);
  font-size: 11px;
}
.stopped-tag {
  background: var(--fd-danger-100, var(--fd-accent-100));
  color: var(--fd-danger-600, var(--fd-accent-700));
}

.trace {
  margin-top: 8px;
  font-size: 11.5px;
  color: var(--fd-ink-600);
}
.trace summary { cursor: pointer; color: var(--fd-accent-700); }
.trace-body {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--fd-accent-50);
  max-height: 180px;
  overflow-y: auto;
}
.trace-line, .trace-reasoning {
  display: flex;
  gap: 8px;
  padding: 2px 0;
  white-space: pre-wrap;
  word-break: break-all;
}
.trace-tag {
  flex: none;
  color: var(--fd-accent-700);
  font-weight: 600;
}
.trace-reasoning .trace-tag { color: var(--fd-ink-400); }
.trace-raw {
  margin: 6px 0 0;
  padding-top: 6px;
  border-top: 1px dashed var(--fd-accent-200);
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 100px;
  overflow-y: auto;
}

.usage-card {
  margin-top: 8px;
  font-size: 11px;
  color: var(--fd-ink-600);
}
.usage-card summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  list-style: none;
}
.usage-card summary::-webkit-details-marker { display: none; }
.usage-pill {
  padding: 2px 7px;
  border: 1px solid var(--fd-accent-200);
  border-radius: 999px;
  background: var(--fd-accent-50);
  color: var(--fd-accent-700);
  font-weight: 600;
}
.usage-provider {
  color: var(--fd-ink-400);
  font-size: 10.5px;
}
.stopped-pill {
  background: var(--fd-danger-100, var(--fd-accent-100));
  border-color: var(--fd-danger-300, var(--fd-accent-300));
  color: var(--fd-danger-700, var(--fd-accent-700));
}
.usage-body {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--fd-accent-50);
}
.usage-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 1px 0;
}
.usage-row.total {
  padding-bottom: 5px;
  border-bottom: 1px dashed var(--fd-accent-200);
}
.usage-row.sub {
  padding-left: 10px;
  color: var(--fd-ink-600);
}
.usage-group { margin-top: 5px; }
.dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 5px;
  border-radius: 2px;
  vertical-align: middle;
}
.dot.input { background: var(--fd-accent-500); }
.dot.hit { background: #4faf78; }
.dot.miss { background: #d96060; }
.dot.write { background: #dfa03c; }
.dot.output { background: #8a7fd6; }
.dot.reason { color: var(--fd-accent-600); }
.dot.reply { color: var(--fd-ink-400); }
.cache-rate {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 8px;
  margin-top: 7px;
  padding-top: 6px;
  border-top: 1px dashed var(--fd-accent-200);
}
.cache-bar {
  grid-column: 1 / -1;
  height: 5px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--fd-accent-100);
}
.cache-bar span {
  display: block;
  height: 100%;
  background: #4faf78;
}
.usage-empty { color: var(--fd-ink-400); }

.diff-card {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1.5px dashed var(--fd-accent-200);
}
.diff-item {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  font-size: 12px;
  color: var(--fd-ink-600);
  padding: 3px 0;
}
.diff-item code {
  background: var(--fd-accent-50);
  color: var(--fd-accent-700);
  padding: 1px 6px;
  border-radius: 5px;
  font-size: 11.5px;
}
.diff-arrow b { color: var(--fd-accent-600); }
.diff-reason { color: var(--fd-ink-400); }

.suggest-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px 0;
  border-top: 1.5px dashed var(--fd-accent-200);
}
.chip { padding: 5px 12px; font-size: 12.5px; }

.input-row {
  display: flex;
  gap: 10px;
  padding: 12px 14px 14px;
  align-items: flex-end;
}
.chat-input { flex: 1; resize: none; font-family: inherit; }
.undo-btn { flex: none; padding: 8px 10px; font-size: 12.5px; }
.send-btn { flex: none; padding: 8px 14px; font-size: 12.5px; }
</style>
