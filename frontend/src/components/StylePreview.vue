<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useStyleStore } from '../stores/style'
import { buildPreviewDoc, STYLE_TAG_ID } from '../preview/previewDoc'

const props = defineProps<{ css?: string; html?: string; autoHeight?: boolean }>()
const emit = defineEmits<{ contentResized: [] }>()
const store = useStyleStore()
const iframe = ref<HTMLIFrameElement | null>(null)
const ready = ref(false)
const activeCss = computed(() => props.css ?? store.css)
const activeHtml = computed(() => props.html ?? store.previewHtml)
let observer: ResizeObserver | null = null

function injectCss() {
  const doc = iframe.value?.contentDocument
  if (!doc) return
  const tag = doc.getElementById(STYLE_TAG_ID)
  if (tag) tag.textContent = activeCss.value
}

function syncFrameHeight() {
  if (!props.autoHeight) return
  const el = iframe.value
  const doc = el?.contentDocument
  const docEl = doc?.documentElement
  if (!el || !docEl) return
  const height = Math.max(docEl.scrollHeight, doc.body?.scrollHeight ?? 0, 240)
  el.style.height = `${height}px`
  emit('contentResized')
}

function observeContent() {
  observer?.disconnect()
  if (!props.autoHeight) return
  const doc = iframe.value?.contentDocument
  const docEl = doc?.documentElement
  if (!doc || !docEl) return
  doc.documentElement.style.overflow = 'hidden'
  doc.body.style.overflow = 'hidden'
  observer = new ResizeObserver(() => syncFrameHeight())
  observer.observe(docEl)
  if (doc.body) observer.observe(doc.body)
  syncFrameHeight()
}

function rebuildDoc() {
  const el = iframe.value
  if (!el) return
  ready.value = false
  observer?.disconnect()
  if (props.autoHeight) el.style.height = ''
  el.srcdoc = buildPreviewDoc(activeHtml.value)
}

onMounted(() => {
  const el = iframe.value
  if (!el) return
  el.addEventListener('load', () => {
    ready.value = true
    injectCss()
    observeContent()
  })
  rebuildDoc()
})

onBeforeUnmount(() => observer?.disconnect())

watch(activeHtml, rebuildDoc)
watch(activeCss, () => {
  if (!ready.value) return
  injectCss()
  if (props.autoHeight) requestAnimationFrame(syncFrameHeight)
})
</script>

<template>
  <div class="preview-shell" :class="{ 'auto-height': autoHeight }">
    <div v-if="!ready || !activeCss" class="preview-loading">
      <span class="fd-label">LOADING</span>
      <p>正在加载当前产物包…</p>
    </div>
    <iframe ref="iframe" class="preview-frame" title="风格预览"></iframe>
  </div>
</template>

<style scoped>
.preview-shell {
  box-sizing: border-box;
  position: relative;
  height: 100%;
  min-height: 0;
  padding: 12px;
}
.preview-shell.auto-height {
  height: auto;
  min-height: 100%;
  padding: 0;
}
.preview-frame {
  display: block;
  width: 100%;
  height: 100%;
  border: none;
  background: var(--fd-paper);
  border-radius: var(--fd-r-lg);
}
.preview-shell.auto-height .preview-frame {
  height: 240px;
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
