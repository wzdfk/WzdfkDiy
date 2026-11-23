import { ref } from 'vue'

export interface SystemSettings {
  outputDir: string
  askBeforeExport: boolean
}

export const DEFAULT_OUTPUT_DIR = 'C:/Users/output'

const STORAGE_KEY = 'uidiy.systemSettings'

function readSettings(): SystemSettings {
  const fallback: SystemSettings = {
    outputDir: DEFAULT_OUTPUT_DIR,
    askBeforeExport: false,
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const saved = JSON.parse(raw) as Partial<SystemSettings>
    return {
      outputDir: typeof saved.outputDir === 'string' && saved.outputDir.trim()
        ? saved.outputDir
        : fallback.outputDir,
      askBeforeExport: saved.askBeforeExport === true,
    }
  } catch { return fallback }
}

export const systemSettings = ref<SystemSettings>(readSettings())

export function updateSystemSettings(patch: Partial<SystemSettings>) {
  systemSettings.value = { ...systemSettings.value, ...patch }
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(systemSettings.value)) } catch { /* 忽略存储异常 */ }
}
