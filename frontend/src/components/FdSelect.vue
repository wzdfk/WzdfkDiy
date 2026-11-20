<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface FdSelectOption {
  label: string
  value: string
}

const props = withDefaults(defineProps<{
  modelValue: string
  options: FdSelectOption[]
  placeholder?: string
}>(), { placeholder: '请选择' })

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const root = ref<HTMLElement | null>(null)
const open = ref(false)
const selectedLabel = computed(
  () => props.options.find(o => o.value === props.modelValue)?.label ?? props.placeholder,
)

function choose(option: FdSelectOption) {
  emit('update:modelValue', option.value)
  open.value = false
}

function toggle() {
  open.value = !open.value
}

function onDocumentClick(event: MouseEvent) {
  if (root.value && !root.value.contains(event.target as Node)) open.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    open.value = false
    return
  }
  if (!open.value || (event.key !== 'ArrowDown' && event.key !== 'ArrowUp')) return
  event.preventDefault()
  const index = props.options.findIndex(o => o.value === props.modelValue)
  const delta = event.key === 'ArrowDown' ? 1 : -1
  const next = (index + delta + props.options.length) % props.options.length
  if (props.options[next]) choose(props.options[next])
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="root" class="fd-select">
    <button
      type="button"
      class="fd-input fd-select-trigger"
      :class="{ 'is-open': open }"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="toggle"
    >
      <span class="fd-select-value">{{ selectedLabel }}</span>
      <span class="fd-select-caret" aria-hidden="true">▾</span>
    </button>
    <div v-if="open" class="fd-select-menu" role="listbox">
      <div
        v-for="option in options"
        :key="option.value"
        class="fd-select-opt"
        :class="{ 'is-selected': option.value === modelValue }"
        role="option"
        :aria-selected="option.value === modelValue"
        @click="choose(option)"
      >
        <span class="fd-select-check" aria-hidden="true">✓</span>
        <span>{{ option.label }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.fd-select,
.fd-select * { box-sizing: border-box; }
.fd-select { position: relative; display: block; width: 100%; min-width: 0; }
.fd-select-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  text-align: left;
  cursor: pointer;
  padding: 6px 12px;
  font-size: 13px;
}
.fd-select-trigger.is-open {
  border-color: var(--fd-accent-500);
  box-shadow: 3px 3px 0 var(--fd-accent-300);
}
.fd-select-value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fd-select-caret {
  flex: none;
  color: var(--fd-ink-400);
  font-size: 11px;
  transition: transform var(--fd-dur) var(--fd-ease-pop);
}
.fd-select-trigger.is-open .fd-select-caret { transform: rotate(180deg); }
.fd-select-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  z-index: 30;
  max-height: 240px;
  overflow-y: auto;
  background: var(--fd-surface);
  border: var(--fd-border);
  border-radius: var(--fd-r-md);
  box-shadow: var(--fd-e2);
  padding: 4px;
  animation: fd-select-in var(--fd-dur) var(--fd-ease-pop);
}
.fd-select-opt {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: var(--fd-r-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--fd-ink-600);
  transition: background var(--fd-dur) var(--fd-ease-out),
              color var(--fd-dur) var(--fd-ease-out);
}
.fd-select-opt:hover { background: var(--fd-accent-50); color: var(--fd-ink-900); }
.fd-select-opt.is-selected {
  background: var(--fd-accent-100);
  color: var(--fd-ink-900);
  font-weight: 600;
}
.fd-select-check {
  width: 14px;
  flex: none;
  color: var(--fd-accent-600);
  opacity: 0;
}
.fd-select-opt.is-selected .fd-select-check { opacity: 1; }
@keyframes fd-select-in {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
