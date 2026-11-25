<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { NButton, NConfigProvider, NModal } from 'naive-ui'
import { useStyleStore } from '../stores/style'
import {
  LLM_PROVIDERS,
  exportZip,
  getLlmSettings,
  getProviderPreset,
  inferLlmProvider,
  listLlmModels,
  pickDirectory,
  saveExportToDir,
  testLlm,
  type LlmProvider,
  type LlmRuntime,
  type LlmSettings,
  type ReasoningEffort,
} from '../api/style'
import ChatPanel from '../components/ChatPanel.vue'
import ArtifactPanel from '../components/ArtifactPanel.vue'
import StylePreview from '../components/StylePreview.vue'
import FdSelect from '../components/FdSelect.vue'
import helpMd from '../assets/帮助文档.md?raw'
import { toast } from '../composables/toast'
import { setThemePreference, themeMode, themePreference, toggleTheme, type ThemePreference } from '../composables/theme'
import { DEFAULT_OUTPUT_DIR, systemSettings, updateSystemSettings } from '../composables/systemSettings'
import { llmSettings, updateLlmSettings } from '../composables/llmSettings'

const store = useStyleStore()
const activeTab = ref('chat')
const tokenDrawerOpen = ref(false)
const showHelp = ref(false)

const promptInput = ref('')

// —— 使用帮助：本地静态 md 的极简渲染（先转义再套标签，不引依赖） ——
function escapeHtml(text: string) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function inlineMd(text: string) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}
const helpHtml = computed(() => {
  const lines = helpMd.replace(/\r\n?/g, '\n').split('\n')
  const out: string[] = []
  const cells = (row: string) => row.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const heading = /^(#{1,3})\s+(.*)$/.exec(line)
    if (heading) {
      out.push(`<h${heading[1].length}>${inlineMd(heading[2])}</h${heading[1].length}>`)
      i++
      continue
    }
    if (line.startsWith('|') && (lines[i + 1] ?? '').includes('---')) {
      const head = cells(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) { rows.push(cells(lines[i])); i++ }
      out.push(`<table><thead><tr>${head.map(c => `<th>${inlineMd(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${inlineMd(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`)
      continue
    }
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(`<li>${inlineMd(lines[i].replace(/^\d+\.\s/, ''))}</li>`)
        i++
      }
      out.push(`<ol>${items.join('')}</ol>`)
      continue
    }
    if (/^>\s?/.test(line)) {
      const parts: string[] = []
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        parts.push(inlineMd(lines[i].replace(/^>\s?/, '')))
        i++
      }
      out.push(`<blockquote>${parts.join('<br>')}</blockquote>`)
      continue
    }
    if (!line.trim()) { i++; continue }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|\d+\.\s|[-*]\s|>|\|)/.test(lines[i])) {
      para.push(inlineMd(lines[i].trim()))
      i++
    }
    if (para.length) out.push(`<p>${para.join('<br>')}</p>`)
    else i++
  }
  return out.join('')
})

// —— 双预览同步滚动 ——
const baselineBox = ref<HTMLElement | null>(null)
const newBox = ref<HTMLElement | null>(null)
const syncTrack = ref<HTMLElement | null>(null)
const syncState = ref({ ratio: 0, thumb: 100 })
let syncing = false
let dragging = false

function clamp(value: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value))
}

function maxScrollOf(el: HTMLElement | null) {
  return el ? Math.max(0, el.scrollHeight - el.clientHeight) : 0
}

function updateThumb() {
  const a = baselineBox.value
  const b = newBox.value
  const viewport = Math.max(a?.clientHeight ?? 0, b?.clientHeight ?? 0)
  const content = Math.max(a?.scrollHeight ?? 0, b?.scrollHeight ?? 0)
  syncState.value.thumb = content > 0
    ? clamp(viewport / content * 100, 12, 100)
    : 100
}

function syncFrom(source: 'baseline' | 'new') {
  if (syncing) return
  const a = baselineBox.value
  const b = newBox.value
  const src = source === 'baseline' ? a : b
  const target = source === 'baseline' ? b : a
  if (!src || !target) return

  updateThumb()
  const srcMax = maxScrollOf(src)
  const targetMax = maxScrollOf(target)
  const ratio = srcMax > 0 ? clamp(src.scrollTop / srcMax) : 0
  syncState.value.ratio = ratio
  syncing = true
  target.scrollTop = ratio * targetMax
  requestAnimationFrame(() => { syncing = false })
}

function applyScrollRatio(ratio: number) {
  const next = clamp(ratio)
  syncState.value.ratio = next
  syncing = true
  for (const box of [baselineBox.value, newBox.value]) {
    if (box) box.scrollTop = next * maxScrollOf(box)
  }
  requestAnimationFrame(() => { syncing = false })
}

function applyTrackScroll(event: MouseEvent) {
  const track = syncTrack.value
  if (!track) return
  const rect = track.getBoundingClientRect()
  const thumbPx = Math.max(24, rect.height * syncState.value.thumb / 100)
  const travel = Math.max(1, rect.height - thumbPx)
  const ratio = (event.clientY - rect.top - thumbPx / 2) / travel
  applyScrollRatio(ratio)
}

function stopDrag() {
  dragging = false
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', stopDrag)
}

function onDrag(event: MouseEvent) {
  if (dragging) applyTrackScroll(event)
}

function startDrag(event: MouseEvent) {
  dragging = true
  applyTrackScroll(event)
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', stopDrag)
}

function onTrackWheel(event: WheelEvent) {
  event.preventDefault()
  applyScrollRatio(syncState.value.ratio + event.deltaY / 900)
}

watch(() => store.pendingDiff, async () => {
  await nextTick()
  updateThumb()
})

onBeforeUnmount(() => {
  stopDrag()
  stopSplitDrag()
})

// —— 左右侧栏宽度分隔条 ——
const LEFT_DEFAULT = 540
const RIGHT_DEFAULT = 330
const leftWidth = ref(LEFT_DEFAULT)
const rightWidth = ref(RIGHT_DEFAULT)
let splitSide: 'left' | 'right' | null = null
let splitStartX = 0
let splitStartWidth = 0

function loadSplitWidths() {
  try {
    const saved = JSON.parse(localStorage.getItem('uidiy.split') || '{}')
    if (typeof saved.left === 'number') leftWidth.value = saved.left
    if (typeof saved.right === 'number') rightWidth.value = saved.right
  } catch { /* 忽略脏数据 */ }
}
function saveSplitWidths() {
  localStorage.setItem('uidiy.split', JSON.stringify({ left: leftWidth.value, right: rightWidth.value }))
}
let splitOverlay: HTMLDivElement | null = null

function startSplitDrag(side: 'left' | 'right', event: MouseEvent) {
  if (event.button !== 0) return
  splitSide = side
  splitStartX = event.clientX
  splitStartWidth = side === 'left' ? leftWidth.value : rightWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'

  // 拖拽期间用透明遮罩接管全部鼠标事件，避免 iframe 吞掉 mousemove/mouseup 导致粘手
  const overlay = document.createElement('div')
  overlay.className = 'split-overlay'
  document.body.appendChild(overlay)
  splitOverlay = overlay
  overlay.addEventListener('mousemove', onSplitDrag)
  overlay.addEventListener('mouseup', stopSplitDrag)
  window.addEventListener('mouseup', stopSplitDrag)
  window.addEventListener('blur', stopSplitDrag)
}
function onSplitDrag(event: MouseEvent) {
  if (!splitSide) return
  const delta = event.clientX - splitStartX
  const next = splitSide === 'left'
    ? splitStartWidth + delta
    : splitStartWidth - delta
  const clamped = Math.min(700, Math.max(280, next))
  if (splitSide === 'left') leftWidth.value = clamped
  else rightWidth.value = clamped
}
function stopSplitDrag() {
  if (splitOverlay) {
    splitOverlay.removeEventListener('mousemove', onSplitDrag)
    splitOverlay.removeEventListener('mouseup', stopSplitDrag)
    splitOverlay.remove()
    splitOverlay = null
  }
  window.removeEventListener('mouseup', stopSplitDrag)
  window.removeEventListener('blur', stopSplitDrag)
  if (!splitSide) return
  splitSide = null
  saveSplitWidths()
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}
function resetSplit(side: 'left' | 'right') {
  if (side === 'left') leftWidth.value = LEFT_DEFAULT
  else rightWidth.value = RIGHT_DEFAULT
  saveSplitWidths()
}
loadSplitWidths()

// —— 存档 / 档案管理 ——
const showSave = ref(false)
const showArchives = ref(false)
const saveName = ref('')
const archivesLoading = ref(false)
const BLANK_TEMPLATE_NAME = '空模板'
const isBlankBaseline = computed(
  () => !store.activeArchiveName && store.bundle?.meta.name === BLANK_TEMPLATE_NAME,
)
const savePlaceholder = computed(() =>
  isBlankBaseline.value ? '空模板是内置基线，请输入你的风格名' : '档案名（同名覆盖）',
)

onMounted(() => store.init())

type SaveFilePicker = (options: {
  suggestedName?: string
  types?: { description: string; accept: Record<string, string[]> }[]
}) => Promise<{
  createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void> }>
}>

function getSaveFilePicker(): SaveFilePicker | undefined {
  return (window as Window & { showSaveFilePicker?: SaveFilePicker }).showSaveFilePicker
}

function errorText(err: unknown): string {
  const e = err as {
    message?: string
    response?: { data?: { error?: string; detail?: string } }
  }
  return e.response?.data?.error ?? e.response?.data?.detail ?? e.message ?? '未知错误'
}

const pickingDir = ref(false)

async function chooseDirectory(apply: (path: string) => void) {
  pickingDir.value = true
  try {
    const res = await pickDirectory()
    if (!res.ok || !res.selected) {
      if (res.error && res.error !== '已取消或未选择目录') toast.error(`选择目录失败：${res.error}`)
      return
    }
    apply(res.path)
  } catch (err) {
    toast.error(`选择目录失败：${errorText(err)}`)
  } finally {
    pickingDir.value = false
  }
}

const exportPathDialogOpen = ref(false)
const exportPathInput = ref('')
const exportSaving = ref(false)

async function doExport() {
  const fileName = `${store.bundle?.meta.name ?? 'style'}.zip`
  try {
    if (!systemSettings.value.askBeforeExport) {
      const dir = systemSettings.value.outputDir.trim() || DEFAULT_OUTPUT_DIR
      const res = await saveExportToDir(dir)
      toast.success(`产物包已导出到：${res.path}`)
      return
    }

    const blob = await exportZip()
    const picker = getSaveFilePicker()
    if (picker) {
      try {
        const handle = await picker({
          suggestedName: fileName,
          types: [{ description: 'ZIP 产物包', accept: { 'application/zip': ['.zip'] } }],
        })
        const writable = await handle.createWritable()
        await writable.write(blob)
        await writable.close()
        toast.success('产物包已保存到所选位置')
      } catch (err) {
        if ((err as { name?: string })?.name !== 'AbortError') throw err
      }
      return
    }

    exportPathInput.value = ''
    exportPathDialogOpen.value = true
  } catch (err) {
    toast.error(`导出失败：${errorText(err)}`)
  }
}

function pickExportDir() {
  void chooseDirectory(path => { exportPathInput.value = path })
}

async function confirmExportPath() {
  const dir = exportPathInput.value.trim()
  if (!dir) {
    toast.warning('请先选择输出目录')
    return
  }
  exportSaving.value = true
  try {
    const res = await saveExportToDir(dir)
    exportPathDialogOpen.value = false
    toast.success(`产物包已导出到：${res.path}`)
  } catch (err) {
    toast.error(`导出失败：${errorText(err)}`)
  } finally {
    exportSaving.value = false
  }
}

function openSave() {
  saveName.value = isBlankBaseline.value ? '' : (store.activeArchiveName ?? store.bundle?.meta.name ?? '')
  showSave.value = true
}

async function confirmSave() {
  const name = saveName.value.trim()
  if (!name) {
    toast.warning(isBlankBaseline.value ? '请先为你的风格起个名字' : '档案名不能为空')
    return
  }
  if (name === BLANK_TEMPLATE_NAME) {
    toast.warning('「空模板」是内置基线名称，请改成你的风格名后再存档')
    return
  }
  const res = await store.saveArchive(name)
  if (res.ok) {
    showSave.value = false
    toast.success(`已存档「${name}」到 数据库`)
  } else {
    toast.error(res.error ?? '存档失败')
  }
}

async function openArchives() {
  showArchives.value = true
  archivesLoading.value = true
  const res = await store.refreshArchives()
  archivesLoading.value = false
  if (!res.ok) toast.error(res.error ?? '档案加载失败（MySQL 是否在跑？）')
}

async function doLoad(id: number) {
  const res = await store.loadArchive(id)
  if (res.ok) {
    showArchives.value = false
    toast.success('档案已加载为当前风格')
  } else {
    toast.error(res.error ?? '加载失败')
  }
}

async function doDelete(id: number) {
  const res = await store.deleteArchive(id)
  if (!res.ok) toast.error(res.error ?? '删除失败')
}

async function doUseBlank() {
  showArchives.value = false
  try {
    await store.useBlankTemplate()
    toast.success('已切换到「空模板」，可从维度面板开始打造个人风格；存档时请另起名字')
  } catch {
    toast.error('切换空模板失败，检查后端服务')
  }
}

// —— 设置（左下角入口 · 系统设置 / 模型设置） ——
const showSettings = ref(false)
type SettingsTab = 'system' | 'model'
const settingsTab = ref<SettingsTab>('system')
const themeOptions: { value: ThemePreference; label: string; hint: string }[] = [
  { value: 'light', label: '明亮', hint: '始终使用浅色' },
  { value: 'dark', label: '暗黑', hint: '始终使用深色' },
  { value: 'system', label: '跟随系统', hint: '默认，随系统切换' },
]
const systemDraft = ref({ ...systemSettings.value })

function pickSystemDir() {
  void chooseDirectory(path => { systemDraft.value.outputDir = path })
}

function saveSystemSettings() {
  const outputDir = systemDraft.value.outputDir.trim() || DEFAULT_OUTPUT_DIR
  updateSystemSettings({ outputDir, askBeforeExport: systemDraft.value.askBeforeExport })
  systemDraft.value = { ...systemSettings.value }
  toast.success('系统设置已保存')
}

const llmCfg = ref<LlmSettings>({
  provider: 'zhipu',
  base_url: '', model: '', reasoning_effort: 'auto', key_masked: '', has_key: false, enabled: false,
})
const llmLoaded = ref(false)
const keyInput = ref('')
const showKey = ref(false)
const llmTesting = ref(false)
const llmTestResult = ref<{ ok: boolean; text: string } | null>(null)

function currentLlmRuntime(): LlmRuntime {
  return {
    provider: llmCfg.value.provider,
    base_url: llmCfg.value.base_url,
    model: llmCfg.value.model,
    reasoning_effort: llmCfg.value.reasoning_effort,
    api_key: keyInput.value,
  }
}

const providerPreset = computed(() => getProviderPreset(llmCfg.value.provider))
const reasoningOptions = computed(() => providerPreset.value.reasoning_options)
const isCustomProvider = computed(() => llmCfg.value.provider === 'custom')
const remoteModels = ref<string[]>([])
const modelsLoading = ref(false)
const modelsHint = ref('')
const modelOptions = computed(() => {
  const values = [llmCfg.value.model, ...providerPreset.value.models, ...remoteModels.value]
  return [...new Set(values.filter(Boolean))].map(value => ({ label: value, value }))
})

async function refreshModels() {
  modelsLoading.value = true
  modelsHint.value = ''
  try {
    const res = await listLlmModels({
      base_url: llmCfg.value.base_url,
      api_key: keyInput.value || undefined,
    })
    if (res.ok && res.models.length) {
      remoteModels.value = res.models
      modelsHint.value = `已从供应商获取 ${res.models.length} 个模型`
    } else {
      remoteModels.value = []
      modelsHint.value = '供应商未返回可用模型，显示内置常用模型。'
    }
  } catch {
    remoteModels.value = []
    modelsHint.value = '模型列表请求失败，显示内置常用模型。'
  } finally {
    modelsLoading.value = false
  }
}

function onModelChange(value: string) {
  llmCfg.value.model = value
}

function applyProvider(provider: LlmProvider, fillModel = true) {
  const preset = getProviderPreset(provider)
  llmCfg.value.provider = provider
  if (preset.base_url) llmCfg.value.base_url = preset.base_url
  if (fillModel && preset.model) llmCfg.value.model = preset.model
  const values = preset.reasoning_options.map(o => o.value)
  if (!values.includes(llmCfg.value.reasoning_effort)) {
    llmCfg.value.reasoning_effort = 'auto' as ReasoningEffort
  }
}

function onProviderChange(value: string) {
  applyProvider(value as LlmProvider)
  remoteModels.value = []
  void refreshModels()
}

function onReasoningChange(value: string) {
  llmCfg.value.reasoning_effort = value as ReasoningEffort
}

async function openSettings() {
  systemDraft.value = { ...systemSettings.value }
  showSettings.value = true
  llmTestResult.value = null
  try {
    const cfg = await getLlmSettings()
    const local = llmSettings.value
    const hasLocal = !!(local.base_url || local.model || local.api_key)
    llmCfg.value = {
      ...cfg,
      provider: hasLocal ? local.provider : cfg.provider,
      base_url: hasLocal ? local.base_url : cfg.base_url,
      model: hasLocal ? local.model : cfg.model,
      reasoning_effort: hasLocal ? local.reasoning_effort : cfg.reasoning_effort,
    }
    keyInput.value = local.api_key
    if (!llmCfg.value.provider) {
      applyProvider(inferLlmProvider(llmCfg.value.base_url, llmCfg.value.model), false)
    }
    llmLoaded.value = true
    void refreshModels()
  } catch {
    toast.error('读取设置失败')
  }
}

async function doTestLlm() {
  llmTesting.value = true
  llmTestResult.value = null
  try {
    const r = await testLlm(currentLlmRuntime())
    llmTestResult.value = r.ok
      ? { ok: true, text: `连通正常 · ${r.latency_ms}ms · ${r.sample ?? ''}` }
      : { ok: false, text: r.error ?? '连接失败' }
  } catch {
    llmTestResult.value = { ok: false, text: '请求失败（后端是否在跑？）' }
  } finally {
    llmTesting.value = false
  }
}

function doSaveLlm() {
  updateLlmSettings(currentLlmRuntime())
  llmTestResult.value = null
  toast.success(keyInput.value
    ? '已保存到当前浏览器（不会上传服务器）'
    : '已保存到当前浏览器（Key 为空，将走内置词典兜底）')
}

/** 工作台顶栏的首次定义入口：提示词 → 初始档案 */
async function defineStyle() {
  if (!promptInput.value.trim()) return
  store.messages.length = 0        // 新定义 = 新会话
  await store.parsePrompt(promptInput.value)
  promptInput.value = ''
  activeTab.value = 'chat'
}

// Naive UI 主题对齐 FOLD tokens（自举：工作台外壳也穿自家衣服）
const naiveTheme = computed(() => ({
  common: {
    primaryColor: themeMode.value === 'dark' ? '#7fc0e4' : '#4a92bd',
    primaryColorHover: themeMode.value === 'dark' ? '#a6d6ef' : '#3a789c',
    primaryColorPressed: themeMode.value === 'dark' ? '#63a9d0' : '#2f5f7d',
    primaryColorSuppl: themeMode.value === 'dark' ? '#a6d6ef' : '#3a789c',
    borderRadius: '8px',
    fontSizeMedium: '13px',
    bodyColor: themeMode.value === 'dark' ? '#14181d' : '#ffffff',
    cardColor: themeMode.value === 'dark' ? '#1e242b' : '#ffffff',
    textColorBase: themeMode.value === 'dark' ? '#e8edf2' : '#23282f',
  },
}))
</script>

<template>
  <n-config-provider :theme-overrides="naiveTheme">
    <div class="studio">
      <!-- 顶栏 -->
      <header class="topbar">
        <div class="brand">
          <span class="fd-label">UIDIY</span>
          <h1 class="fd-title" style="margin:0;">打造个人风格</h1>
          <span v-if="store.bundle" class="style-name">{{ store.bundle.meta.name }}</span>
        </div>
        <div class="define-row">
          <input
            v-model="promptInput"
            class="fd-input topbar-input"
            placeholder="一句话定义新风格，回车生成…"
            @keydown.enter="defineStyle"
          />
          <button
            class="fd-btn topbar-btn"
            :disabled="!promptInput.trim()"
            @click="defineStyle"
          >新建风格</button>
        </div>
        
        <div class="action-row">
          <button
            class="fd-btn help-icon theme-icon"
            type="button"
            :title="themeMode === 'light' ? '切换到深色（黑夜降临）' : '切换到浅色（划破天际）'"
            :aria-label="themeMode === 'light' ? '切换到深色' : '切换到浅色'"
            @click="toggleTheme"
          >{{ themeMode === 'light' ? '◐' : '◑' }}</button>
          <button
            class="fd-btn help-icon"
            type="button"
            title="使用帮助"
            aria-label="使用帮助"
            @click="showHelp = true"
          >?</button>
          <button class="fd-btn fd-btn-ghost topbar-btn" @click="openSave">存档</button>
          <button class="fd-btn fd-btn-ghost topbar-btn" @click="openArchives">档案</button>
          <button class="fd-btn fd-btn-primary topbar-btn" @click="doExport">导出产物包</button>
        </div>
      </header>

      <!-- 主体：左对话 · 中预览 · 右产物面板 -->
      <main class="body">
        <section class="left" :style="{ width: leftWidth + 'px' }">
          <div class="left-card chat-card">
            <ChatPanel />
          </div>
          <button class="settings-entry fd-btn fd-btn-ghost" @click="openSettings">
            ⚙ 设置
          </button>
        </section>

        <div
          class="splitter"
          title="拖动调节对话面板宽度（双击复位）"
          @mousedown.prevent="startSplitDrag('left', $event)"
          @dblclick="resetSplit('left')"
        ><span></span></div>

        <section class="center">
          <div class="center-frame">
            <n-button
              v-if="!tokenDrawerOpen && !store.pendingDiff"
              class="drawer-fab"
              quaternary
              circle
              size="small"
              title="展开产物面板"
              @click="tokenDrawerOpen = true"
            >
              <template #icon>
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </template>
            </n-button>
            <div v-if="store.pendingDiff" class="diff-view">
              <div class="diff-bar">
                <div class="diff-copy">
                  <span class="fd-label">DIFF · 本轮 {{ store.pendingDiff.diff.length }} 项修改</span>
                  <p>{{ store.pendingDiff.reply }}</p>
                </div>
                <div class="diff-actions">
                  <n-button size="tiny" quaternary :disabled="store.busy" @click="store.rejectDiff()">拒绝</n-button>
                  <n-button size="tiny" type="primary" :disabled="store.busy" @click="store.acceptDiff()">接受</n-button>
                </div>
              </div>
              <div class="preview-split">
                <div class="preview-col">
                  <span class="preview-tag">基准</span>
                  <div
                    ref="baselineBox"
                    class="preview-box"
                    @scroll.passive="syncFrom('baseline')"
                  >
                    <StylePreview
                      :css="store.pendingDiff.baselineCss"
                      :html="store.pendingDiff.baselineHtml"
                      auto-height
                      @content-resized="updateThumb"
                    />
                  </div>
                </div>

                <div
                  ref="syncTrack"
                  class="sync-scrollbar"
                  title="拖动同步滚动两侧预览"
                  @mousedown.prevent="startDrag"
                  @wheel.prevent="onTrackWheel"
                >
                  <div
                    class="sync-thumb"
                    :style="{
                      height: `${syncState.thumb}%`,
                      top: `${syncState.ratio * (100 - syncState.thumb)}%`,
                    }"
                  ></div>
                </div>

                <div class="preview-col">
                  <span class="preview-tag is-new">新预览</span>
                  <div
                    ref="newBox"
                    class="preview-box"
                    @scroll.passive="syncFrom('new')"
                  >
                    <StylePreview auto-height @content-resized="updateThumb" />
                  </div>
                </div>
              </div>
            </div>
            <StylePreview v-else />
          </div>
        </section>

        <div
          v-if="tokenDrawerOpen"
          class="splitter"
          title="拖动调节产物面板宽度（双击复位）"
          @mousedown.prevent="startSplitDrag('right', $event)"
          @dblclick="resetSplit('right')"
        ><span></span></div>

        <section v-if="tokenDrawerOpen" class="right" :style="{ width: rightWidth + 'px' }">
          <div class="right-card token-card">
            <div class="drawer-head">
              <span class="fd-label">产物查看</span>
              <button class="fd-btn fd-btn-ghost drawer-close" @click="tokenDrawerOpen = false">收起 ›</button>
            </div>
            <div class="token-body"><ArtifactPanel /></div>
          </div>
        </section>
      </main>

      <!-- 使用帮助弹窗 -->
      <n-modal v-model:show="showHelp" :auto-focus="false">
        <div class="fd-card modal-card modal-wide help-modal">
          <span class="fd-label">HELP · 使用说明</span>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="help-body" v-html="helpHtml"></div>
          <div class="modal-actions">
            <button class="fd-btn fd-btn-primary" @click="showHelp = false">知道了</button>
          </div>
        </div>
      </n-modal>

      <!-- 存档弹窗 -->
      <n-modal v-model:show="showSave" :auto-focus="false">
        <div class="fd-card modal-card">
          <h2 class="fd-title">存档当前风格</h2>
          <input
            v-model="saveName"
            class="fd-input modal-input"
            :placeholder="savePlaceholder"
            @keydown.enter="confirmSave"
          />
          <div class="modal-actions">
            <button class="fd-btn" @click="showSave = false">取消</button>
            <button class="fd-btn fd-btn-primary" @click="confirmSave">保存</button>
          </div>
        </div>
      </n-modal>

      <!-- 档案列表弹窗 -->
      <n-modal v-model:show="showArchives" :auto-focus="false">
        <div class="fd-card modal-card modal-wide">
          <h2 class="fd-title">风格档案库</h2>
          <div v-if="archivesLoading" class="archive-empty">加载中…</div>
          <div v-else-if="store.archives.length === 0" class="archive-empty">
            还没有存档。调好风格后点「存档」保存，之后随时加载回来。
          </div>
          <div v-else class="archive-list">
            <div v-for="a in store.archives" :key="a.id" class="archive-row">
              <span class="archive-swatch" :style="{ background: a.accent || 'var(--fd-accent-500)' }"></span>
              <div class="archive-meta">
                <b>{{ a.name }}</b>
                <small>{{ a.updated_at.replace('T', ' ') }}</small>
              </div>
              <div class="archive-actions">
                <button class="fd-btn fd-btn-tiny fd-btn-primary" @click="doLoad(a.id)">加载</button>
                <button class="fd-btn fd-btn-tiny fd-btn-danger" @click="doDelete(a.id)">删除</button>
              </div>
            </div>
          </div>
          <div class="modal-actions archive-foot">
            <button class="fd-btn fd-btn-ghost" @click="doUseBlank">使用空模板</button>
          </div>
        </div>
      </n-modal>
      
      <!-- 设置弹窗（系统设置 / 模型设置） -->
      <n-modal v-model:show="showSettings" :auto-focus="false">
        <div class="fd-card modal-card settings-modal">
          <h2 class="fd-title">设置</h2>
          <div class="settings-tabs">
            <button
              class="settings-tab"
              :class="{ active: settingsTab === 'system' }"
              @click="settingsTab = 'system'"
            >系统设置</button>
            <button
              class="settings-tab"
              :class="{ active: settingsTab === 'model' }"
              @click="settingsTab = 'model'"
            >模型设置</button>
          </div>

          <div v-if="settingsTab === 'system'" class="settings-form">
            <div class="settings-section">
              <h3 class="settings-section-title">偏好设置</h3>
              <p class="settings-hint">主题即时生效；默认跟随系统。</p>
              <div class="theme-options">
                <button
                  v-for="opt in themeOptions"
                  :key="opt.value"
                  class="theme-option"
                  :class="{ active: themePreference === opt.value }"
                  @click="setThemePreference(opt.value)"
                >
                  <span class="theme-option-label">{{ opt.label }}</span>
                  <small>{{ opt.hint }}</small>
                </button>
              </div>
            </div>

            <div class="settings-section">
              <h3 class="settings-section-title">产物输出路径</h3>
              <label class="fd-label">默认输出路径</label>
              <div class="path-field">
                <input
                  :value="systemDraft.outputDir || DEFAULT_OUTPUT_DIR"
                  class="fd-input"
                  readonly
                />
                <button
                  class="fd-btn fd-btn-ghost path-pick"
                  type="button"
                  :disabled="pickingDir"
                  @click="pickSystemDir"
                >{{ pickingDir ? '选择中…' : '选择…' }}</button>
              </div>
              <div class="settings-check-row">
                <label class="settings-check">
                  <input v-model="systemDraft.askBeforeExport" type="checkbox" />
                  每次导出前询问
                </label>
                <span
                  class="hint-mark"
                  tabindex="0"
                  title="勾选后忽略默认路径，每次导出都选择位置；未勾选时保存到上方路径。"
                >?</span>
              </div>
              <div class="modal-actions">
                <button class="fd-btn fd-btn-primary" @click="saveSystemSettings">保存系统设置</button>
              </div>
            </div>
          </div>

          <div v-else class="settings-form">
            <h3 class="settings-section-title">大模型配置</h3>
            <p class="settings-hint">
              OpenAI 兼容接口均可（智谱 GLM / DeepSeek / OpenAI…）。
              Key 只保存在当前浏览器，不会上传服务器；AI 未配置或调用失败时走内置风格词典。
            </p>

            <div v-if="llmLoaded">
              <label class="fd-label">厂商 PROVIDER</label>
              <FdSelect
                :model-value="llmCfg.provider"
                :options="LLM_PROVIDERS"
                @update:model-value="onProviderChange"
              />

              <label class="fd-label">接口地址 BASE_URL</label>
              <input
                v-model="llmCfg.base_url"
                class="fd-input"
                placeholder="选择厂商后自动填入"
              />

              <label class="fd-label">模型 MODEL</label>
              <div class="model-field">
                <FdSelect
                  v-if="!isCustomProvider"
                  :model-value="llmCfg.model"
                  :options="modelOptions"
                  placeholder="选择模型"
                  @update:model-value="onModelChange"
                />
                <input
                  v-else
                  v-model="llmCfg.model"
                  class="fd-input"
                  placeholder="自定义模型 ID"
                />
                <button
                  class="fd-btn fd-btn-ghost model-refresh"
                  type="button"
                  :disabled="modelsLoading"
                  @click="refreshModels"
                >{{ modelsLoading ? '拉取中…' : '刷新' }}</button>
              </div>
              <small v-if="modelsHint" class="models-hint">{{ modelsHint }}</small>

              <label class="fd-label">API KEY</label>
              <div class="key-field">
                <input
                  v-model="keyInput"
                  class="fd-input"
                  :type="showKey ? 'text' : 'password'"
                  :placeholder="llmSettings.api_key ? '本机已保存，留空则清空 Key' : '粘贴你的 key（仅保存在本浏览器）'"
                />
                <button
                  class="fd-btn fd-btn-ghost key-toggle"
                  type="button"
                  :title="showKey ? '隐藏 key' : '显示 key'"
                  @click="showKey = !showKey"
                >{{ showKey ? '隐藏' : '显示' }}</button>
              </div>
              <small v-if="llmSettings.api_key" class="models-hint">本机已保存 Key；留空点“保存到本机”可清除。</small>

              <label class="fd-label">思考强度 REASONING EFFORT</label>
              <FdSelect
                :model-value="llmCfg.reasoning_effort"
                :options="reasoningOptions"
                @update:model-value="onReasoningChange"
              />
              <div v-if="providerPreset.hint" class="settings-hint">{{ providerPreset.hint }}</div>

              <div v-if="llmTestResult" class="test-result" :class="llmTestResult.ok ? 'ok' : 'bad'">
                {{ llmTestResult.ok ? '✓ ' : '✗ ' }}{{ llmTestResult.text }}
              </div>

              <div class="modal-actions">
                <button class="fd-btn" :disabled="llmTesting" @click="doTestLlm">
                  {{ llmTesting ? '测试中…' : '测试连接' }}
                </button>
                <button class="fd-btn fd-btn-primary" @click="doSaveLlm">保存到本机</button>
              </div>
            </div>
            <div v-else class="archive-empty">加载中…</div>
          </div>
        </div>
      </n-modal>

      <!-- 导出位置输入（浏览器不支持原生保存对话框时的回退） -->
      <n-modal v-model:show="exportPathDialogOpen" :auto-focus="false">
        <div class="fd-card modal-card">
          <h2 class="fd-title">选择导出位置</h2>
          <p class="settings-hint">当前浏览器不支持原生保存对话框，请选择目标目录。</p>
          <label class="fd-label">输出目录</label>
          <div class="path-field">
            <input
              :value="exportPathInput || '请选择目录…'"
              class="fd-input modal-input"
              readonly
            />
            <button
              class="fd-btn fd-btn-ghost path-pick"
              type="button"
              :disabled="pickingDir"
              @click="pickExportDir"
            >{{ pickingDir ? '选择中…' : '选择…' }}</button>
          </div>
          <div class="modal-actions">
            <button class="fd-btn" @click="exportPathDialogOpen = false">取消</button>
            <button class="fd-btn fd-btn-primary" :disabled="exportSaving" @click="confirmExportPath">
              {{ exportSaving ? '导出中…' : '导出' }}
            </button>
          </div>
        </div>
      </n-modal>
    </div>
  </n-config-provider>
</template>

<style scoped>
.studio {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--fd-paper);
}

/* —— 顶栏 —— */
.topbar {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--fd-surface);
  border-bottom: var(--fd-border);
  flex: none;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}
.style-name {
  font-size: 12px;
  color: var(--fd-accent-600);
  background: var(--fd-accent-50);
  border: 1px solid var(--fd-accent-200);
  padding: 2px 10px;
  border-radius: 999px;
}
.define-row {
  display: flex;
  justify-self: center;
  justify-content: center;
  gap: 10px;
  align-items: center;
}
.action-row {
  display: flex;
  justify-self: end;
  gap: 10px;
  align-items: center;
}
/* 顶栏折角控件：沿用 fd-* 签名，仅收紧尺寸适配顶栏高度 */
.topbar-input {
  width: 300px;
  padding: 6px 12px;
  font-size: 13px;
}
.topbar-btn {
  padding: 6px 14px;
  font-size: 13px;
  white-space: nowrap;
}
.help-icon {
  width: 26px;
  height: 26px;
  padding: 0;
  font-size: 14px;
  font-weight: 700;
  border-radius: 50%;
}
.theme-icon { font-size: 16px; }
@media (max-width: 980px) {
  .topbar {
    grid-template-columns: 1fr auto;
    row-gap: 10px;
  }
  .define-row {
    grid-column: 1 / -1;
    grid-row: 2;
  }
  .action-row {
    grid-column: 2;
    grid-row: 1;
  }
}

/* —— 主体 —— */
.body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 14px;
  padding: 14px;
}

.left {
  width: clamp(380px, 26vw, 460px);
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  min-width: 0;
}
.left-card {
  background: var(--fd-surface);
  border: var(--fd-border);
  border-radius: var(--fd-r-lg);
  box-shadow: var(--fd-e1);
  overflow: hidden;
}
.chat-card { flex: 1; min-height: 0; }

/* 左下角统一设置入口 */
.settings-entry {
  flex: none;
  justify-content: center;
  padding: 7px 12px;
  font-size: 13px;
}
.settings-entry small { color: var(--fd-ink-400); font-size: 11px; }

/* 设置弹窗 */
.settings-hint {
  margin: 0;
  font-size: 12.5px;
  color: var(--fd-ink-600);
  background: var(--fd-accent-50);
  border: 1.5px solid var(--fd-accent-200);
  border-radius: var(--fd-r-sm);
  padding: 8px 12px;
}
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.settings-form > .fd-input {
  box-sizing: border-box;
  padding: 6px 12px;
  font-size: 13px;
}
.settings-modal { min-width: 760px; max-height: 86vh; overflow-y: auto; }
.settings-tabs {
  display: flex;
  gap: 8px;
  margin: 10px 0 16px;
  border-bottom: 1px solid var(--fd-accent-200);
}
.settings-tab {
  padding: 8px 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--fd-ink-500, var(--fd-ink-600));
  font-size: 13px;
  cursor: pointer;
}
.settings-tab.active {
  color: var(--fd-accent-600);
  border-bottom-color: var(--fd-accent-500);
  font-weight: 600;
}
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--fd-accent-200);
}
.settings-section:last-child { border-bottom: 0; padding-bottom: 0; }
.settings-section-title {
  margin: 0;
  font-size: 14px;
  color: var(--fd-ink-900);
}
.settings-form .fd-input {
  box-sizing: border-box;
  padding: 6px 12px;
  font-size: 13px;
}
.path-field { display: flex; align-items: center; gap: 8px; }
.path-field .fd-input { flex: 1; min-width: 0; cursor: default; }
.path-pick { flex: none; padding: 6px 10px; font-size: 12px; white-space: nowrap; }
.theme-options { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.theme-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 10px 12px;
  border: 1.5px solid var(--fd-accent-200);
  border-radius: var(--fd-r-sm);
  background: var(--fd-paper);
  color: var(--fd-ink-700, var(--fd-ink-600));
  cursor: pointer;
  text-align: left;
}
.theme-option.active { border-color: var(--fd-accent-500); background: var(--fd-accent-50); }
.theme-option-label { font-size: 13px; font-weight: 600; color: var(--fd-ink-900); }
.theme-option small { font-size: 11px; color: var(--fd-ink-400); }
.settings-check-row { display: flex; align-items: center; gap: 4px; }
.settings-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--fd-ink-900);
  cursor: pointer;
}
.hint-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border: 1px solid var(--fd-accent-300, var(--fd-accent-200));
  border-radius: 50%;
  color: var(--fd-accent-600);
  font-size: 11px;
  line-height: 1;
  cursor: help;
}
.model-field { display: flex; align-items: center; gap: 8px; }
.model-field .fd-select, .model-field .fd-input { flex: 1; min-width: 0; }
.model-refresh { flex: none; padding: 6px 10px; font-size: 12px; white-space: nowrap; }
.models-hint {
  display: block;
  margin-top: 4px;
  color: var(--fd-ink-400);
  font-size: 11px;
  line-height: 1.4;
}
.models-hint + .fd-label { margin-top: 8px; }
.key-field { position: relative; display: flex; align-items: center; }
.key-field .fd-input {
  box-sizing: border-box;
  padding-right: 64px;
}
.key-toggle {
  position: absolute;
  right: 4px;
  padding: 3px 8px;
  font-size: 12px;
}
.reasoning-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.test-result {
  font-size: 12.5px;
  padding: 6px 10px;
  border: var(--fd-border);
  border-radius: var(--fd-r-sm);
  box-shadow: var(--fd-e1);
}
.test-result.ok {
  color: var(--fd-ok);
  background: color-mix(in srgb, var(--fd-ok) 12%, var(--fd-surface));
  border-color: var(--fd-ok);
}
.test-result.bad {
  color: var(--fd-danger);
  background: color-mix(in srgb, var(--fd-danger) 12%, var(--fd-surface));
  border-color: var(--fd-danger);
}

/* —— 侧栏宽度分隔条 —— */
.splitter {
  flex: none;
  width: 8px;
  align-self: stretch;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--fd-r-sm);
  transition: background var(--fd-dur) var(--fd-ease-out);
}
.splitter:hover { background: var(--fd-accent-50); }
.splitter span {
  width: 3px;
  height: 36px;
  border-radius: 999px;
  background: var(--fd-accent-300);
  box-shadow: var(--fd-e1);
  transition: background var(--fd-dur) var(--fd-ease-out);
}
.splitter:hover span { background: var(--fd-accent-600); }
:global(.split-overlay) {
  position: fixed;
  inset: 0;
  z-index: 9999;
  cursor: col-resize;
}

.center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.center-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 4px 10px;
}
.dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--fd-ok);
}
.center-frame {
  position: relative;
  flex: 1;
  min-height: 0;
  border: var(--fd-border);
  border-radius: var(--fd-r-lg);
  box-shadow: var(--fd-e2);
  overflow: hidden;
  background: var(--fd-paper);
}
.drawer-fab {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 5;
  opacity: .75;
}
.drawer-fab:hover { opacity: 1; }

/* —— 本轮改动：基准 / 新预览并排对比 —— */
.diff-view { height: 100%; min-height: 0; display: flex; flex-direction: column; }
.diff-bar {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: var(--fd-border);
  background: var(--fd-surface);
}
.diff-copy { min-width: 0; }
.diff-copy p { margin: 4px 0 0; font-size: 12px; color: var(--fd-ink-600); }
.diff-actions { display: flex; gap: 8px; flex: none; }
.preview-split {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 12px minmax(0, 1fr);
  gap: 8px;
  padding: 10px;
}
.preview-col { min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 6px; }
.preview-tag { font-size: 11px; color: var(--fd-ink-400); letter-spacing: .1em; }
.preview-tag.is-new { color: var(--fd-accent-600); }
.preview-box {
  flex: 1;
  min-height: 0;
  border: var(--fd-border);
  border-radius: var(--fd-r-md);
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--fd-accent-50);
  transition: background-color var(--fd-dur-slow) var(--fd-ease-out);
  scrollbar-width: none;
}
.preview-box::-webkit-scrollbar { display: none; }
.sync-scrollbar {
  position: relative;
  align-self: stretch;
  margin-top: 22px;
  border-radius: 999px;
  background: var(--fd-accent-50);
  border: 1px solid var(--fd-accent-100);
  cursor: ns-resize;
}
.sync-thumb {
  position: absolute;
  left: 2px;
  right: 2px;
  min-height: 24px;
  border-radius: 999px;
  background: var(--fd-accent-400);
  box-shadow: var(--fd-e1);
}

/* —— Token 抽屉 —— */
.right {
  width: clamp(300px, 22vw, 360px);
  flex: none;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.right-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--fd-surface);
  border: var(--fd-border);
  border-radius: var(--fd-r-lg);
  box-shadow: var(--fd-e1);
}
.drawer-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px 6px;
}
.drawer-close { padding: 4px 10px; font-size: 12px; }
.token-body { flex: 1; min-height: 0; overflow-y: auto; }

/* —— 弹窗（FOLD 折角 + 实心投影） —— */
.modal-card {
  width: 360px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--fd-surface);
  border: var(--fd-border);
  border-radius: var(--fd-r-lg);
  box-shadow: var(--fd-e3);
}
.modal-wide { width: 460px; }
.help-modal { width: 560px; max-height: 84vh; }
.help-body {
  overflow-y: auto;
  min-height: 0;
  padding-right: 6px;
  font-size: 13px;
  color: var(--fd-ink-600);
}
.help-body :deep(h1) { font-size: 17px; margin: 0 0 6px; color: var(--fd-ink-900); }
.help-body :deep(h2) {
  font-size: 14px;
  margin: 18px 0 6px;
  color: var(--fd-accent-600);
}
.help-body :deep(p) { margin: 6px 0; line-height: 1.7; }
.help-body :deep(ol) { margin: 0 0 10px; padding-left: 22px; }
.help-body :deep(li) { margin: 4px 0; line-height: 1.7; }
.help-body :deep(strong) { color: var(--fd-ink-900); }
.help-body :deep(code) {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  background: var(--fd-accent-50);
  border: 1px solid var(--fd-accent-200);
  border-radius: var(--fd-r-sm);
  padding: 1px 5px;
}
.help-body :deep(blockquote) {
  margin: 8px 0;
  padding: 8px 12px;
  background: var(--fd-accent-50);
  border-left: 3px solid var(--fd-accent-500);
  border-radius: var(--fd-r-sm);
  color: var(--fd-ink-600);
}
.help-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12.5px;
}
.help-body :deep(th),
.help-body :deep(td) {
  border: 1px solid var(--fd-accent-200);
  padding: 6px 10px;
  text-align: left;
}
.help-body :deep(th) { background: var(--fd-accent-50); color: var(--fd-ink-900); }
.modal-input {
  box-sizing: border-box;
  font-size: 13px;
}
.fd-btn-tiny {
  padding: 4px 10px;
  font-size: 12px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.archive-empty {
  color: var(--fd-ink-400);
  font-size: 13px;
  padding: 16px 4px;
}
.archive-list {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  overflow-y: auto;
}
.archive-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
  border-top: 1.5px dashed var(--fd-accent-200);
}
.archive-swatch {
  width: 26px;
  height: 26px;
  flex: none;
  border: var(--fd-border);
  border-radius: var(--fd-r-sm);
  box-shadow: var(--fd-e1);
}
.archive-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.archive-meta b { color: var(--fd-ink-900); font-size: 13px; font-weight: 600; }
.archive-meta small { color: var(--fd-ink-400); font-size: 11.5px; }
.archive-actions { display: flex; gap: 6px; flex: none; }
.archive-foot {
  justify-content: flex-start;
  border-top: 1.5px dashed var(--fd-accent-200);
  padding-top: 10px;
}
</style>
