<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useStyleStore } from '../stores/style'
import { buildPreviewDoc, STYLE_TAG_ID } from '../preview/previewDoc'

const props = defineProps<{ css?: string }>()
const store = useStyleStore()
const iframe = ref<HTMLIFrameElement | null>(null)
const ready = ref(false)
const activeCss = computed(() => props.css ?? store.css)

function injectCss() {
  const doc = iframe.value?.contentDocument
  if (!doc) return
  const tag = doc.getElementById(STYLE_TAG_ID)
  if (tag) tag.textContent = activeCss.value
}

onMounted(() => {
  const el = iframe.value
  if (!el) return
  el.srcdoc = buildPreviewDoc()
  el.addEventListener('load', () => {
    ready.value = true
    injectCss()
  })
})

watch(activeCss, () => {
  if (ready.value) injectCss()
})
</script>

<template>
  <div class="preview-shell">
    <div v-if="!ready || !activeCss" class="preview-loading">
      <span class="fd-label">LOADING</span>
      <p>正在从后端加载生成的样式…</p>
    </div>
    <iframe ref="iframe" class="preview-frame" title="风格预览"></iframe>
  </div>
</template>

<style scoped>
.preview-shell {
  position: relative;
  height: 100%;
  min-height: 0;
}
.preview-frame {
  width: 100%;
  height: 100%;
  border: none;
  background: var(--fd-paper);
  border-radius: var(--fd-r-lg);
}
.preview-loading {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--fd-ink-600);
  background: var(--fd-paper);
  border-radius: var(--fd-r-lg);
}
</style>
