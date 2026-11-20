import { ref } from 'vue'

export type ToastKind = 'success' | 'warning' | 'error' | 'info'

export interface ToastItem {
  id: number
  kind: ToastKind
  text: string
}

export const toasts = ref<ToastItem[]>([])
let seq = 0

export function pushToast(kind: ToastKind, text: string, duration = 3200) {
  const id = ++seq
  toasts.value.push({ id, kind, text })
  window.setTimeout(() => dismissToast(id), duration)
  return id
}

export function dismissToast(id: number) {
  const i = toasts.value.findIndex(t => t.id === id)
  if (i >= 0) toasts.value.splice(i, 1)
}

export const toast = {
  success: (text: string) => pushToast('success', text),
  warning: (text: string) => pushToast('warning', text),
  error: (text: string) => pushToast('error', text),
  info: (text: string) => pushToast('info', text),
}
