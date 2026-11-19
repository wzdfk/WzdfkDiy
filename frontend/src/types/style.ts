/** 风格 tokens 类型定义 —— 与后端 app/core/tokens.py 一一对应 */

export interface AccentScale {
  s50: string; s100: string; s200: string; s300: string
  s400: string; s500: string; s600: string; s700: string
}

export interface InkScale { ink900: string; ink600: string; ink400: string }

export interface StatusColors { ok: string; warn: string; danger: string; info: string }

export interface StyleTokens {
  schemaVersion: string
  prefix: string
  meta: { name: string; version: string; created: string; note: string }
  color: {
    accent: AccentScale
    ink: InkScale
    paper: string
    surface: string
    shadow: string | null
    status: StatusColors
  }
  shape: { strategy: 'fold' | 'uniform' | 'asymmetric'; radius: { lg: string; md: string; sm: string } }
  line: { border_width: number; border_style: 'solid' | 'dashed'; focus_style: 'dashed' | 'solid' | 'glow' }
  elevation: {
    type: 'offset-solid' | 'soft-blur' | 'layered'
    levels: { e1: string; e2: string; e3: string }
    shadow_color: string | null
  }
  motion: {
    duration: number
    duration_slow: number
    easing_pop: string
    easing_out: string
    hover: 'lift' | 'press' | 'tilt' | 'none'
    active: 'press' | 'none'
  }
  type: {
    font_stack: string
    display_size: string; display_weight: number; display_tracking: string
    title_size: string; title_weight: number
    body_size: string; body_line_height: number
    label_size: string; label_weight: number; label_tracking: string
  }
  spacing: { unit: number; steps: number[] }
  /** 组件盒模型字段 —— 控件详情面板（未来）直接读写这里 */
  components: {
    button: ControlBox; card: ControlBox; input: ControlBox
    badge: ControlBox; toast: ControlBox; menu: ControlBox
  }
}

export interface ControlBox {
  padding_x: string; padding_y: string
  font_size: string            // 空 = 跟随 body_size
  font_weight: number
  radius_ref: 'sm' | 'md' | 'lg'
  shadow_ref: 'none' | 'e1' | 'e2' | 'e3'
  custom_shadow: string | null
  margin_bottom: string
}

export interface DiffItem {
  path: string
  from: string | number
  to: string | number
  reason: string
}

/** V2 自由产物包：结构固定，视觉内容自由 */
export interface ArtifactDiffItem {
  kind?: 'semantic' | 'file' | string
  path: string
  from: string | number
  to: string | number
  reason: string
}

export interface StyleBundle {
  schemaVersion: '2.0'
  meta: { name: string; version: string; created: string; note: string }
  reply: string
  style_prompt: string
  preview_html: string
  base_css: string
  style_css: string
  semantic_diff: ArtifactDiffItem[]
  history: { role: 'user' | 'assistant' | string; text: string; at?: string }[]
  source: {
    prompt: string
    model: string
    base_url: string
    generated_at: string
    parent_hash: string
    raw_response: string
  }
}

export interface TokenUsage {
  available: boolean
  provider?: string
  model?: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cached_tokens: number
  cache_miss_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  raw?: Record<string, unknown> | null
}

export interface ChatStreamEvent {
  type: 'stage' | 'thought' | 'reasoning' | 'delta' | 'usage' | 'done' | 'error' | 'message'
  stage?: string
  label?: string
  thought?: string
  delta?: string
  message?: string
  mode?: 'artifact' | 'rewrite' | 'adjust'
  tokens?: StyleTokens
  bundle?: StyleBundle
  diff?: ArtifactDiffItem[]
  reply?: string
  usage?: TokenUsage
  duration_ms?: number
}

export interface ChatMessage {
  role: 'user' | 'bot'
  text: string
  diff?: ArtifactDiffItem[]
  streaming?: boolean
  stopped?: boolean
  started_at?: number
  mode?: 'artifact' | 'rewrite' | 'adjust'
  trace?: ChatStreamEvent[]
  raw?: string
  reasoning?: string
  usage?: TokenUsage
  duration_ms?: number
}
