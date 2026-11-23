import { computed, ref, watch } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'uidiy.theme'
const DEFAULT_PREFERENCE: ThemePreference = 'system'

function readPreference(): ThemePreference {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved
  } catch { /* 忽略存储异常 */ }
  return DEFAULT_PREFERENCE
}

function readSystemMode(): ThemeMode {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

const systemQuery = typeof window !== 'undefined'
  ? window.matchMedia?.('(prefers-color-scheme: dark)')
  : undefined

export const systemThemeMode = ref<ThemeMode>(readSystemMode())
export const themePreference = ref<ThemePreference>(readPreference())
export const themeMode = computed<ThemeMode>(() =>
  themePreference.value === 'system' ? systemThemeMode.value : themePreference.value,
)
export const themeDirection = ref<'dark' | 'light'>('dark')

function apply(mode: ThemeMode) {
  document.documentElement.setAttribute('data-theme', mode)
  document.documentElement.style.colorScheme = mode
  themeDirection.value = mode
}

function persist(preference: ThemePreference) {
  try { localStorage.setItem(STORAGE_KEY, preference) } catch { /* 忽略存储异常 */ }
}

function withTransition(commit: () => void) {
  const doc = document as Document & {
    startViewTransition?: (cb: () => void) => { finished: Promise<void> }
  }
  if (!doc.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    commit()
    return
  }
  doc.startViewTransition(commit)
}

let initialized = false

export function initTheme() {
  if (!initialized) {
    initialized = true
    const onSystemChange = (matches: boolean) => { systemThemeMode.value = matches ? 'dark' : 'light' }
    if (systemQuery?.addEventListener) {
      systemQuery.addEventListener('change', e => onSystemChange(e.matches))
    } else {
      systemQuery?.addListener?.(e => onSystemChange(e.matches))
    }
    watch(themeMode, mode => apply(mode), { flush: 'sync' })
  }
  apply(themeMode.value)
}

export function setThemePreference(next: ThemePreference) {
  if (next !== 'light' && next !== 'dark' && next !== 'system') return
  withTransition(() => {
    themePreference.value = next
    persist(next)
  })
}

export function toggleTheme() {
  setThemePreference(themeMode.value === 'light' ? 'dark' : 'light')
}
