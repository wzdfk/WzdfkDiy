<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useStyleStore } from '../stores/style'

const store = useStyleStore()
const input = ref('')
const listEl = ref<HTMLElement | null>(null)

async function send() {
  const text = input.value.trim()
  if (!text || store.busy) return
  input.value = ''
  // 空会话时首条消息走「解析提示词」，否则走对话优化
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

const SUGGESTIONS = ['再柔和一点', '硬朗一些', '圆润一点', '极简一些', '厚重一些', '俏皮一点', '从容一点']

async function suggest(text: string) {
  input.value = ''
  if (store.messages.length === 0) {
    await store.parsePrompt(text)
  } else {
    await store.send(text)
  }
  await nextTick()
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior: 'smooth' })
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
          <div class="bubble-text">{{ msg.text }}</div>
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

      <div v-if="store.busy" class="bubble bot typing">思考中…</div>
    </div>

    <div class="suggest-row">
      <button
        v-for="s in SUGGESTIONS" :key="s"
        class="fd-btn fd-btn-ghost chip" :disabled="store.busy"
        @click="suggest(s)"
      >{{ s }}</button>
    </div>

    <div class="input-row">
      <textarea
        v-model="input"
        class="fd-input chat-input"
        rows="2"
        placeholder="描述风格或说「再柔和一点」…（Enter 发送，Shift+Enter 换行）"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button
        class="fd-btn fd-btn-ghost undo-btn" :disabled="store.busy"
        title="撤销最近一次改动（对话 / 面板 / 加载档案）"
        @click="store.undo()"
      >↩ 撤销</button>
      <button class="fd-btn fd-btn-primary send-btn" :disabled="store.busy" @click="send">发送</button>
    </div>
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
