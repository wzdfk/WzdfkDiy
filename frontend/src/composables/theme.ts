import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'uidiy.theme'

function readInitial(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* 忽略存储异常 */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const themeMode = ref<ThemeMode>(readInitial())
export const themeDirection = ref<'dark' | 'light'>('dark')

function apply(mode: ThemeMode) {
  document.documentElement.setAttribute('data-theme', mode)
  document.documentElement.style.colorScheme = mode
}

export function initTheme() {
  apply(themeMode.value)
}

export function toggleTheme() {
  const next: ThemeMode = themeMode.value === 'light' ? 'dark' : 'light'
  themeDirection.value = next
  const commit = () => {
    apply(next)
    themeMode.value = next
    try { localStorage.setItem(STORAGE_KEY, next) } catch { /* 忽略存储异常 */ }
  }

  const doc = document as Document & {
    startViewTransition?: (cb: () => void) => { finished: Promise<void> }
  }
  if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    commit()
    return
  }
  doc.startViewTransition(commit)
}
