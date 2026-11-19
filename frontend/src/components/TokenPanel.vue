<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton, NColorPicker, NRadioButton, NRadioGroup,
  NSelect, NSlider, NTabPane, NTabs,
} from 'naive-ui'
import { useStyleStore } from '../stores/style'

const store = useStyleStore()

// ---------- 圆角：基准值 + 策略 → 四角字符串 ----------
const radiusBase = ref(16)

function buildRadius(base: number, strategy: string) {
  const f = (n: number) => `${Math.max(n, 0)}px`
  if (strategy === 'uniform') {
    return { lg: f(base), md: f(base), sm: f(base) }
  }
  // fold / asymmetric：三圆一利
  return {
    lg: `${f(base)} ${f(base)} ${f(base)} ${f(Math.max(base - 13, 3))}`,
    md: `${f(base - 4)} ${f(base - 4)} ${f(base - 4)} ${f(Math.max(base - 13, 3))}`,
    sm: `${f(base - 8)} ${f(base - 8)} ${f(base - 8)} ${f(Math.max(base - 14, 2))}`,
  }
}

// tokens 变化时只同步面板显示值，不回写；
// 否则对话/撤销/档案带来的圆角改动会被面板归一化后覆盖。
watch(() => store.tokens, (t) => {
  if (!t) return
  const m = t.shape.radius.lg.match(/^(\d+(?:\.\d+)?)px/)
  if (m) radiusBase.value = Number(m[1])
}, { immediate: true })

function onRadiusBaseChange(v: number) {
  radiusBase.value = v
  store.patch((t) => { t.shape.radius = buildRadius(v, t.shape.strategy) })
}

const strategyOptions = [
  { label: '折角 · 三圆一利', value: 'fold' },
  { label: '统一圆角', value: 'uniform' },
  { label: '不对称', value: 'asymmetric' },
]

function onStrategyChange(v: string) {
  store.patch((t) => {
    t.shape.strategy = v as 'fold' | 'uniform' | 'asymmetric'
    t.shape.radius = buildRadius(radiusBase.value, v)
  })
}

// ---------- 投影类型 → 整套 levels ----------
const LEVELS: Record<string, { e1: string; e2: string; e3: string }> = {
  'offset-solid': {
    e1: '3px 3px 0 var(--s-shadow)',
    e2: '5px 5px 0 var(--s-shadow)',
    e3: '8px 8px 0 var(--s-shadow)',
  },
  'soft-blur': {
    e1: '0 2px 8px var(--s-shadow)',
    e2: '0 4px 16px var(--s-shadow)',
    e3: '0 8px 28px var(--s-shadow)',
  },
  layered: {
    e1: '0 1px 2px var(--s-shadow), 0 2px 6px var(--s-shadow)',
    e2: '0 2px 4px var(--s-shadow), 0 5px 12px var(--s-shadow)',
    e3: '0 3px 6px var(--s-shadow), 0 10px 24px var(--s-shadow)',
  },
}

function onElevChange(v: string) {
  store.patch((t) => {
    t.elevation.type = v as 'offset-solid' | 'soft-blur' | 'layered'
    t.elevation.levels = { ...LEVELS[v] }
  })
}

// ---------- 主色：改 500 档，并派生整套色阶，保证预览明显联动 ----------
function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([\da-f]{3}|[\da-f]{6})$/i.exec(hex.trim())
  if (!m) return null
  const h = m[1].length === 3 ? m[1].split('').map(c => c + c).join('') : m[1]
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

function mixHex(hex: string, target: [number, number, number], ratio: number) {
  const rgb = hexToRgb(hex)
  if (!rgb) return hex
  return '#' + rgb
    .map((c, i) => Math.round(c + (target[i] - c) * ratio).toString(16).padStart(2, '0'))
    .join('')
}

function deriveAccent(hex: string) {
  const white: [number, number, number] = [255, 255, 255]
  const black: [number, number, number] = [0, 0, 0]
  return {
    s50: mixHex(hex, white, 0.92),
    s100: mixHex(hex, white, 0.82),
    s200: mixHex(hex, white, 0.65),
    s300: mixHex(hex, white, 0.45),
    s400: mixHex(hex, white, 0.22),
    s500: hex,
    s600: mixHex(hex, black, 0.16),
    s700: mixHex(hex, black, 0.32),
  }
}

function onAccentChange(v: string | null) {
  if (!v) return
  store.patch((t) => { Object.assign(t.color.accent, deriveAccent(v)) })
}

function onColor(path: 'paper' | 'surface' | 'ink900' | 'ink600' | 'ink400') {
  return (v: string | null) => {
    if (!v) return
    store.patch((t) => {
      if (path.startsWith('ink')) (t.color.ink as unknown as Record<string, string>)[path] = v
      else (t.color as unknown as Record<string, string>)[path] = v
    })
  }
}

const onPaperChange = onColor('paper')
const onSurfaceChange = onColor('surface')
const onInk900Change = onColor('ink900')

const hoverOptions = [
  { label: '抬起', value: 'lift' },
  { label: '收拢', value: 'press' },
  { label: '倾斜', value: 'tilt' },
  { label: '无位移', value: 'none' },
]
const activeOptions = [
  { label: '按下压扁', value: 'press' },
  { label: '无反馈', value: 'none' },
]
const focusOptions = [
  { label: '虚线环', value: 'dashed' },
  { label: '实线环', value: 'solid' },
  { label: '柔和光圈', value: 'glow' },
]
const elevOptions = [
  { label: '偏移实心（印刷感）', value: 'offset-solid' },
  { label: '柔和模糊', value: 'soft-blur' },
  { label: '分层投影', value: 'layered' },
]

const accent500 = computed(() => store.tokens?.color.accent.s500 ?? '#000000')
const paper = computed(() => store.tokens?.color.paper ?? '#ffffff')
const surface = computed(() => store.tokens?.color.surface ?? '#ffffff')
const ink900 = computed(() => store.tokens?.color.ink.ink900 ?? '#000000')
</script>

<template>
  <div v-if="store.tokens" class="token-panel">
    <n-tabs type="line" size="small" animated>
      <n-tab-pane name="color" tab="色彩">
        <div class="field">
          <div class="field-label">主色 accent-500</div>
          <n-color-picker :value="accent500" :show-alpha="false" @update:value="onAccentChange" />
        </div>
        <div class="field">
          <div class="field-label">页面底色 paper</div>
          <n-color-picker :value="paper" :show-alpha="false" @update:value="onPaperChange" />
        </div>
        <div class="field">
          <div class="field-label">面板色 surface</div>
          <n-color-picker :value="surface" :show-alpha="false" @update:value="onSurfaceChange" />
        </div>
        <div class="field">
          <div class="field-label">墨色 ink-900（文字与描边）</div>
          <n-color-picker :value="ink900" :show-alpha="false" @update:value="onInk900Change" />
        </div>
      </n-tab-pane>

      <n-tab-pane name="shape" tab="形状">
        <div class="field">
          <div class="field-label">圆角策略</div>
          <n-select :value="store.tokens.shape.strategy" :options="strategyOptions" @update:value="onStrategyChange" />
        </div>
        <div class="field">
          <div class="field-label">圆角基准（lg）</div>
          <n-slider :value="radiusBase" :min="2" :max="28" :step="1" :format-tooltip="(v: number) => `${v}px`"
            @update:value="onRadiusBaseChange" />
        </div>
        <div class="radius-show">
          <code>lg</code> {{ store.tokens.shape.radius.lg }}<br>
          <code>md</code> {{ store.tokens.shape.radius.md }}<br>
          <code>sm</code> {{ store.tokens.shape.radius.sm }}
        </div>
      </n-tab-pane>

      <n-tab-pane name="line-elev" tab="线与投影">
        <div class="field">
          <div class="field-label">边框宽度</div>
          <n-slider :value="store.tokens.line.border_width" :min="1" :max="3" :step="0.5"
            @update:value="(v: number) => store.patch(t => { t.line.border_width = v })" />
        </div>
        <div class="field">
          <div class="field-label">投影类型</div>
          <n-radio-group :value="store.tokens.elevation.type" @update:value="onElevChange">
            <n-radio-button v-for="o in elevOptions" :key="o.value" :value="o.value">{{ o.label }}</n-radio-button>
          </n-radio-group>
        </div>
        <div class="field">
          <div class="field-label">焦点样式</div>
          <n-radio-group :value="store.tokens.line.focus_style"
            @update:value="(v: string) => store.patch(t => { t.line.focus_style = v as 'dashed' | 'solid' | 'glow' })">
            <n-radio-button v-for="o in focusOptions" :key="o.value" :value="o.value">{{ o.label }}</n-radio-button>
          </n-radio-group>
        </div>
        <div class="elev-show">
          <code>e1</code> {{ store.tokens.elevation.levels.e1 }}<br>
          <code>e2</code> {{ store.tokens.elevation.levels.e2 }}<br>
          <code>e3</code> {{ store.tokens.elevation.levels.e3 }}
        </div>
      </n-tab-pane>

      <n-tab-pane name="motion" tab="动效">
        <div class="field">
          <div class="field-label">时长 {{ store.tokens.motion.duration }}ms</div>
          <n-slider :value="store.tokens.motion.duration" :min="100" :max="400" :step="20"
            @update:value="(v: number) => store.patch(t => { t.motion.duration = v })" />
        </div>
        <div class="field">
          <div class="field-label">hover 反馈</div>
          <n-select :value="store.tokens.motion.hover" :options="hoverOptions"
            @update:value="(v: string) => store.patch(t => { t.motion.hover = v as 'lift' | 'press' | 'tilt' | 'none' })" />
        </div>
        <div class="field">
          <div class="field-label">active 反馈</div>
          <n-select :value="store.tokens.motion.active" :options="activeOptions"
            @update:value="(v: string) => store.patch(t => { t.motion.active = v as 'press' | 'none' })" />
        </div>
        <div class="elev-show">
          <code>ease-pop</code> {{ store.tokens.motion.easing_pop }}
        </div>
      </n-tab-pane>
    </n-tabs>

    <div class="panel-foot">
      <n-button quaternary size="small" @click="store.reset()">重置为系统默认风格</n-button>
    </div>
  </div>
</template>

<style scoped>
.token-panel {
  padding: 12px 16px 8px;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.field { margin-bottom: 16px; }
.field-label {
  font-size: 12px;
  color: var(--fd-ink-600);
  font-weight: 600;
  margin-bottom: 6px;
}
.radius-show, .elev-show {
  font-size: 11.5px;
  color: var(--fd-ink-400);
  line-height: 1.8;
  word-break: break-all;
}
.radius-show code, .elev-show code {
  background: var(--fd-accent-50);
  color: var(--fd-accent-700);
  padding: 0 6px;
  border-radius: 4px;
  margin-right: 6px;
}
.panel-foot {
  margin-top: auto;
  padding-top: 8px;
  border-top: 1.5px dashed var(--fd-accent-200);
  display: flex;
  justify-content: flex-end;
}
</style>
