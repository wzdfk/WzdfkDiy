import { ref } from 'vue'
import type { LlmProvider, ReasoningEffort } from '../api/style'

export interface LocalLlmSettings {
  provider: LlmProvider
  base_url: string
  model: string
  reasoning_effort: ReasoningEffort
  api_key: string
}

const STORAGE_KEY = 'uidiy.llmSettings'

const DEFAULT_SETTINGS: LocalLlmSettings = {
  provider: 'zhipu',
  base_url: '',
  model: '',
  reasoning_effort: 'auto',
  api_key: '',
}

const PROVIDERS: LlmProvider[] = ['zhipu', 'deepseek', 'openai', 'moonshot', 'qwen', 'custom']
const EFFORTS: ReasoningEffort[] = ['auto', 'none', 'low', 'medium', 'high', 'max']

function readSettings(): LocalLlmSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    const saved = JSON.parse(raw) as Partial<LocalLlmSettings>
    return {
      provider: PROVIDERS.includes(saved.provider as LlmProvider)
        ? saved.provider as LlmProvider
        : DEFAULT_SETTINGS.provider,
      base_url: typeof saved.base_url === 'string' ? saved.base_url : '',
      model: typeof saved.model === 'string' ? saved.model : '',
      reasoning_effort: EFFORTS.includes(saved.reasoning_effort as ReasoningEffort)
        ? saved.reasoning_effort as ReasoningEffort
        : 'auto',
      api_key: typeof saved.api_key === 'string' ? saved.api_key : '',
    }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export const llmSettings = ref<LocalLlmSettings>(readSettings())

export function updateLlmSettings(patch: Partial<LocalLlmSettings>) {
  llmSettings.value = { ...llmSettings.value, ...patch }
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(llmSettings.value)) } catch { /* 忽略存储异常 */ }
}

export function localLlmRuntime(): LocalLlmSettings {
  return { ...llmSettings.value }
}
