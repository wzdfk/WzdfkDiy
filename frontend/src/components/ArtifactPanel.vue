<script setup lang="ts">
import { computed, ref } from 'vue'
import { useStyleStore } from '../stores/style'

const store = useStyleStore()
const tab = ref<'prompt' | 'html' | 'css' | 'trace'>('prompt')
const tabs = [
  { label: 'Prompt', value: 'prompt' },
  { label: 'HTML', value: 'html' },
  { label: 'CSS', value: 'css' },
  { label: '溯源', value: 'trace' },
] as { label: string; value: 'prompt' | 'html' | 'css' | 'trace' }[]

const content = computed(() => {
  const b = store.bundle
  if (!b) return ''
  if (tab.value === 'prompt') return b.style_prompt
  if (tab.value === 'html') return b.preview_html
  if (tab.value === 'css') return `${b.base_css}\n\n${b.style_css}`
  return JSON.stringify({
    source: b.source,
    history: b.history,
    semantic_diff: b.semantic_diff,
  }, null, 2)
})
</script>

<template>
  <div class="artifact-panel">
    <div class="artifact-tabs">
      <button
        v-for="item in tabs" :key="item.value"
        class="fd-btn" :class="{ 'fd-btn-primary': tab === item.value }"
        @click="tab = item.value"
      >{{ item.label }}</button>
    </div>
    <textarea class="artifact-view" readonly :value="content"></textarea>
  </div>
</template>

<style scoped>
.artifact-panel {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 8px;
  padding: 10px;
}
.artifact-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.artifact-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.artifact-view {
  box-sizing: border-box;
  flex: 1;
  min-height: 0;
  width: 100%;
  resize: none;
  font-family: Consolas, 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.55;
  padding: 10px;
  border: var(--fd-border);
  border-radius: var(--fd-r-sm);
  background: var(--fd-paper);
  color: var(--fd-ink-900);
}
</style>
