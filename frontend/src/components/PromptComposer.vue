<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useStyleStore } from '../stores/style'
import { toast } from '../composables/toast'

type GroupKey = 'scene' | 'carrier' | 'style' | 'color' | 'material' | 'density' | 'font'

interface PresetGroup {
  key: GroupKey
  label: string
  options: string[]
}

interface SelectedBadge {
  key: GroupKey
  group: string
  value: string
}

const props = defineProps<{ draft?: { text: string; seq: number } | null }>()
const emit = defineEmits<{ submit: [prompt: string]; stop: [] }>()
const store = useStyleStore()
const generating = computed(() => store.messages.some(m => m.streaming))

watch(() => props.draft, (d) => {
  if (!d) return
  promptText.value = d.text
  nextTick(() => {
    textareaRef.value?.focus()
    textareaRef.value?.setSelectionRange(d.text.length, d.text.length)
  })
})

const presets: PresetGroup[] = [
  {
    key: 'scene',
    label: '场景',
    options: ['运行监控', '科普展示', '财经终端', '动漫社区', '电商商城', '官网落地页', '教育学习', '创作者工具'],
  },
  {
    key: 'carrier',
    label: '载体',
    options: ['网站', 'Web 后台', '桌面客户端', '移动 App', '小程序', '数据大屏'],
  },
  {
    key: 'style',
    label: '风格',
    options: ['工业机械', '极简克制', '科技未来', '赛博霓虹', '复古纸张', '拟物写实', '玻璃轻盈', '粗野排版', '日式清爽'],
  },
  {
    key: 'color',
    label: '色彩',
    options: ['深灰金属', '天空蓝', '黑金', '森林绿', '暖橙', '低饱和莫兰迪', '冷白灰', '高饱和霓虹'],
  },
  {
    key: 'material',
    label: '材质',
    options: ['金属拉丝', '玻璃磨砂', '纸张印刷', '碳纤维', '网格线', '噪点颗粒', '霓虹光晕', '纯色平面'],
  },
  {
    key: 'density',
    label: '密度',
    options: ['紧凑高信息', '标准舒适', '宽松留白'],
  },
  {
    key: 'font',
    label: '字体',
    options: ['无衬线', '等宽技术感', '衬线编辑感', '圆体亲和', '手写个性'],
  },
]

const QUICK_ADJUSTS = ['再柔和一点', '硬朗一些', '圆润一点', '极简一些', '厚重一些', '俏皮一点', '从容一点']

const selected = reactive<Record<GroupKey, string | null>>({
  scene: null,
  carrier: null,
  style: null,
  color: null,
  material: null,
  density: null,
  font: null,
})
const promptText = ref('')
const activeGroup = ref<GroupKey | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const activePreset = computed(() => presets.find(group => group.key === activeGroup.value) ?? null)

const badges = computed<SelectedBadge[]>(() =>
  presets
    .filter(group => selected[group.key])
    .map(group => ({ key: group.key, group: group.label, value: selected[group.key] as string })),
)

function contextPrefix(): string {
  return badges.value.map(b => `${b.group}：${b.value}`).join('\n')
}

function buildPrompt(text: string = promptText.value.trim()): string {
  const prefix = contextPrefix()
  if (!prefix) return text
  return text ? `${prefix}\n用户补充：${text}` : prefix
}

const canSubmit = computed(() => !store.busy && buildPrompt().length > 0)

function toggleGroup(key: GroupKey) {
  activeGroup.value = activeGroup.value === key ? null : key
}

function choose(group: PresetGroup, option: string) {
  selected[group.key] = selected[group.key] === option ? null : option
  activeGroup.value = null
  textareaRef.value?.focus()
}

function removeBadge(key: GroupKey) {
  selected[key] = null
}

function reset() {
  promptText.value = ''
  activeGroup.value = null
  ;(Object.keys(selected) as GroupKey[]).forEach(key => { selected[key] = null })
}

function submit(text: string = promptText.value.trim()) {
  const prompt = buildPrompt(text)
  if (!prompt || store.busy) return
  emit('submit', prompt)
  reset()
}

function quick(text: string) {
  submit(text)
}

function clearChat() {
  if (store.busy) return
  store.clearMessages()
  reset()
  toast.info('已清空全部对话，当前风格不受影响')
}
</script>

<template>
  <div class="composer">
    <div class="composer-tip">
      <span class="tip-mark">i</span>
      <span>建议手动选择这些语境标签，有助于一次获取预期效果，减少抽卡次数。</span>
    </div>

    <div class="preset-bar">
      <button
        v-for="group in presets" :key="group.key"
        type="button" class="fd-btn preset-btn"
        :class="{ 'fd-btn-primary': activeGroup === group.key, 'has-value': selected[group.key] }"
        :disabled="store.busy"
        @click="toggleGroup(group.key)"
      >
        {{ group.label }}<span class="preset-mark">{{ selected[group.key] ? '·' : '+' }}</span>
      </button>
    </div>

    <div v-if="activePreset" class="option-panel">
      <button
        v-for="option in activePreset.options" :key="option"
        type="button" class="fd-btn option-btn"
        :class="{ 'fd-btn-primary': selected[activePreset.key] === option }"
        @click="choose(activePreset, option)"
      >{{ option }}</button>
    </div>

    <div class="input-shell">
      <div v-if="badges.length" class="selected-badges">
        <button
          v-for="badge in badges" :key="badge.key"
          type="button" class="selected-badge"
          :disabled="store.busy"
          @click="removeBadge(badge.key)"
        >
          {{ badge.group }}·{{ badge.value }} <span class="badge-x">×</span>
        </button>
      </div>

      <textarea
        ref="textareaRef"
        v-model="promptText"
        class="fd-input composer-input"
        rows="2"
        :placeholder="badges.length ? '补充你想强调的细节，或者直接开始…（Enter 发送，Shift+Enter 换行）' : '描述想要的风格或用下方按钮微调…（Enter 发送，Shift+Enter 换行）'"
        :disabled="store.busy"
        @keydown.enter.exact.prevent="submit()"
      ></textarea>

      <div class="composer-actions">
        <template v-if="generating">
          <button
            type="button" class="fd-btn fd-btn-danger stop-btn"
            @click="emit('stop')"
          >■ 停止生成</button>
        </template>
        <template v-else>
          <button
            type="button" class="fd-btn fd-btn-ghost clear-btn" :disabled="store.busy"
            title="清空聊天面板的全部对话（不影响当前产物）" @click="clearChat"
          >✕ 清空</button>
          <button
            type="button" class="fd-btn fd-btn-ghost undo-btn" :disabled="store.busy"
            title="撤销最近一次改动" @click="store.undo()"
          >↩ 撤销</button>
          <button
            type="button" class="fd-btn fd-btn-primary send-btn" :disabled="!canSubmit"
            @click="submit()"
          >发送</button>
        </template>
      </div>
    </div>

    <div class="quick-row">
      <button
        v-for="q in QUICK_ADJUSTS" :key="q"
        type="button" class="fd-btn fd-btn-ghost quick-btn" :disabled="store.busy"
        @click="quick(q)"
      >{{ q }}</button>
      <button
        type="button" class="fd-btn fd-btn-ghost clear-chat-btn"
        :disabled="store.busy || !store.messages.length"
        title="清空上方全部对话（用户与模型回复），不影响当前产物"
        @click="clearChat"
      >✕ 清空对话</button>
    </div>
  </div>
</template>

<style scoped>
.composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px 12px;
  border-top: 1px solid var(--fd-accent-100);
  background: var(--fd-surface);
}
.composer-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--fd-ink-600);
}
.tip-mark {
  flex: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid var(--fd-accent-400);
  color: var(--fd-accent-700);
  font-size: 10px;
  line-height: 12px;
  text-align: center;
}
.preset-bar,
.quick-row,
.option-panel,
.selected-badges,
.composer-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.preset-btn,
.option-btn,
.quick-btn {
  padding: 3px 8px;
  font-size: 11px;
}
.quick-row { align-items: center; }
.clear-chat-btn {
  margin-left: auto;
  padding: 3px 8px;
  font-size: 11px;
  white-space: nowrap;
  color: var(--fd-danger-600, var(--fd-accent-700));
}
.preset-btn.has-value:not(.fd-btn-primary) {
  border-color: var(--fd-accent-400);
  color: var(--fd-accent-700);
}
.preset-mark {
  margin-left: 3px;
  font-weight: 700;
}
.option-panel {
  padding: 7px;
  border: 1px dashed var(--fd-accent-200);
  border-radius: 8px;
  background: var(--fd-accent-50);
}
.input-shell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 7px;
  border: var(--fd-border);
  border-radius: var(--fd-r-sm);
  background: var(--fd-paper);
}
.selected-badges {
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--fd-accent-200);
}
.selected-badge {
  padding: 2px 7px;
  border: 1px solid var(--fd-accent-300);
  border-radius: 999px;
  background: var(--fd-accent-50);
  color: var(--fd-accent-700);
  font-size: 11px;
  cursor: pointer;
}
.badge-x {
  margin-left: 3px;
  font-weight: 700;
}
.composer-input {
  width: 100%;
  border: none;
  outline: none;
  background: transparent;
  resize: none;
  padding: 2px;
  font-size: 12.5px;
}
.composer-actions {
  justify-content: flex-end;
}
.clear-btn,
.undo-btn,
.send-btn {
  padding: 4px 10px;
  font-size: 11.5px;
}
</style>
