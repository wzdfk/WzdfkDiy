<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NButton, NConfigProvider, NInput, NModal, createDiscreteApi } from 'naive-ui'
import { useStyleStore } from '../stores/style'
import { exportZip, getLlmSettings, saveLlmSettings, testLlm, type LlmSettings } from '../api/style'
import ChatPanel from '../components/ChatPanel.vue'
import TokenPanel from '../components/TokenPanel.vue'
import StylePreview from '../components/StylePreview.vue'

const store = useStyleStore()
const activeTab = ref('chat')
const { message } = createDiscreteApi(['message'])

const promptInput = ref('')

// —— 存档 / 档案管理 ——
const showSave = ref(false)
const showArchives = ref(false)
const saveName = ref('')
const archivesLoading = ref(false)
const BLANK_TEMPLATE_NAME = '空模板'
const isBlankBaseline = computed(
  () => !store.activeArchiveName && store.tokens?.meta.name === BLANK_TEMPLATE_NAME,
)
const savePlaceholder = computed(() =>
  isBlankBaseline.value ? '空模板是内置基线，请输入你的风格名' : '档案名（同名覆盖）',
)

onMounted(() => store.init())

async function doExport() {
  const name = store.tokens?.meta.name ?? 'style'
  await exportZip(`${name}.zip`)
  message.success('三件套已导出：style.json + base.css + style.css + STYLE_PROMPT.md')
}

function openSave() {
  saveName.value = isBlankBaseline.value ? '' : (store.activeArchiveName ?? store.tokens?.meta.name ?? '')
  showSave.value = true
}

async function confirmSave() {
  const name = saveName.value.trim()
  if (!name) {
    message.warning(isBlankBaseline.value ? '请先为你的风格起个名字' : '档案名不能为空')
    return
  }
  if (name === BLANK_TEMPLATE_NAME) {
    message.warning('「空模板」是内置基线名称，请改成你的风格名后再存档')
    return
  }
  const res = await store.saveArchive(name)
  if (res.ok) {
    showSave.value = false
    message.success(`已存档「${name}」到 MySQL`)
  } else {
    message.error(res.error ?? '存档失败')
  }
}

async function openArchives() {
  showArchives.value = true
  archivesLoading.value = true
  const res = await store.refreshArchives()
  archivesLoading.value = false
  if (!res.ok) message.error(res.error ?? '档案加载失败（MySQL 是否在跑？）')
}

async function doLoad(id: number) {
  const res = await store.loadArchive(id)
  if (res.ok) {
    showArchives.value = false
    message.success('档案已加载为当前风格')
  } else {
    message.error(res.error ?? '加载失败')
  }
}

async function doDelete(id: number) {
  const res = await store.deleteArchive(id)
  if (!res.ok) message.error(res.error ?? '删除失败')
}

async function doUseBlank() {
  showArchives.value = false
  try {
    await store.useBlankTemplate()
    message.success('已切换到「空模板」，可从维度面板开始打造个人风格；存档时请另起名字')
  } catch {
    message.error('切换空模板失败，检查后端服务')
  }
}

// —— 设置（左下角入口 · LLM 接入配置） ——
const showSettings = ref(false)
const llmCfg = ref<LlmSettings>({ base_url: '', model: '', key_masked: '', has_key: false, enabled: false })
const llmLoaded = ref(false)
const keyInput = ref('')
const llmTesting = ref(false)
const llmTestResult = ref<{ ok: boolean; text: string } | null>(null)
const llmSaving = ref(false)

async function openSettings() {
  showSettings.value = true
  llmTestResult.value = null
  keyInput.value = ''
  try {
    llmCfg.value = await getLlmSettings()
    llmLoaded.value = true
  } catch {
    message.error('读取设置失败')
  }
}

async function doTestLlm() {
  llmTesting.value = true
  llmTestResult.value = null
  try {
    const r = await testLlm()
    llmTestResult.value = r.ok
      ? { ok: true, text: `连通正常 · ${r.latency_ms}ms · ${r.sample ?? ''}` }
      : { ok: false, text: r.error ?? '连接失败' }
  } catch {
    llmTestResult.value = { ok: false, text: '请求失败（后端是否在跑？）' }
  } finally {
    llmTesting.value = false
  }
}

async function doSaveLlm() {
  llmSaving.value = true
  try {
    llmCfg.value = await saveLlmSettings({
      base_url: llmCfg.value.base_url,
      model: llmCfg.value.model,
      api_key: keyInput.value,     // 空串 = 保留已存 key
    })
    keyInput.value = ''
    llmTestResult.value = null
    message.success(`已保存 · AI 接入${llmCfg.value.enabled ? '已启用' : '未配置 key（将走内置词典兜底）'}`)
  } catch {
    message.error('保存失败')
  } finally {
    llmSaving.value = false
  }
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
const naiveTheme = {
  common: {
    primaryColor: '#4a92bd',
    primaryColorHover: '#3a789c',
    primaryColorPressed: '#2f5f7d',
    primaryColorSuppl: '#3a789c',
    borderRadius: '8px',
    fontSizeMedium: '13px',
  },
}
</script>

<template>
  <n-config-provider :theme-overrides="naiveTheme">
    <div class="studio">
      <!-- 顶栏 -->
      <header class="topbar">
        <div class="brand">
          <span class="fd-label">UIDIY</span>
          <h1 class="fd-title" style="margin:0;">打造个人风格</h1>
          <span v-if="store.tokens" class="style-name">{{ store.tokens.meta.name }}</span>
        </div>
        <div class="define-row">
          <n-input
            v-model:value="promptInput"
            placeholder="一句话定义新风格，回车生成…"
            size="small"
            style="width: 300px;"
            @keydown.enter="defineStyle"
          />
          <n-button size="small" @click="defineStyle">定义风格</n-button>
          <n-button size="small" quaternary @click="openSave">存档</n-button>
          <n-button size="small" quaternary @click="openArchives">档案</n-button>
          <n-button size="small" type="primary" @click="doExport">导出三件套</n-button>
        </div>
      </header>

      <!-- 主体：左对话 · 中预览 · 右 Token 面板 -->
      <main class="body">
        <section class="left">
          <div class="left-card chat-card">
            <ChatPanel />
          </div>
          <button class="settings-entry fd-btn fd-btn-ghost" @click="openSettings">
            ⚙ 设置 <small>· AI 接入</small>
          </button>
        </section>

        <section class="center">
          <div class="center-frame">
            <StylePreview />
          </div>
        </section>

        <section class="right">
          <div class="right-card token-card">
            <TokenPanel />
          </div>
        </section>
      </main>

      <!-- 存档弹窗 -->
      <n-modal v-model:show="showSave" :auto-focus="false">
        <div class="fd-card modal-card">
          <span class="fd-label">SAVE TO MYSQL</span>
          <h2 class="fd-title">存档当前风格</h2>
          <n-input
            v-model:value="saveName"
            :placeholder="savePlaceholder"
            size="small"
            @keydown.enter="confirmSave"
          />
          <div class="modal-actions">
            <n-button size="small" @click="showSave = false">取消</n-button>
            <n-button size="small" type="primary" @click="confirmSave">保存</n-button>
          </div>
        </div>
      </n-modal>

      <!-- 档案列表弹窗 -->
      <n-modal v-model:show="showArchives" :auto-focus="false">
        <div class="fd-card modal-card modal-wide">
          <span class="fd-label">ARCHIVES · MYSQL</span>
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
                <n-button size="tiny" type="primary" @click="doLoad(a.id)">加载</n-button>
                <n-button size="tiny" quaternary type="error" @click="doDelete(a.id)">删除</n-button>
              </div>
            </div>
          </div>
          <div class="modal-actions archive-foot">
            <n-button size="small" quaternary @click="doUseBlank">使用空模板</n-button>
          </div>
        </div>
      </n-modal>
      
      <!-- 设置弹窗（LLM 接入） -->
      <n-modal v-model:show="showSettings" :auto-focus="false">
        <div class="fd-card modal-card modal-wide">
          <span class="fd-label">SETTINGS · AI 接入</span>
          <h2 class="fd-title">大模型配置</h2>
          <p class="settings-hint">
            OpenAI 兼容接口均可（智谱 GLM / DeepSeek / OpenAI…）。
            AI 未配置或调用失败时，自动兜底为内置风格词典。
          </p>

          <div v-if="llmLoaded" class="settings-form">
            <label class="fd-label">接口地址 BASE_URL</label>
            <n-input v-model:value="llmCfg.base_url" size="small" placeholder="https://open.bigmodel.cn/api/paas/v4/chat/completions" />

            <label class="fd-label">模型 MODEL</label>
            <n-input v-model:value="llmCfg.model" size="small" placeholder="glm-4-flash" />

            <label class="fd-label">API KEY</label>
            <n-input
              v-model:value="keyInput"
              type="password" show-password-on="click"
              size="small"
              :placeholder="llmCfg.has_key ? `已配置（${llmCfg.key_masked}），留空保持不变` : '粘贴你的 key'"
            />

            <div v-if="llmTestResult" class="test-result" :class="llmTestResult.ok ? 'ok' : 'bad'">
              {{ llmTestResult.ok ? '✓ ' : '✗ ' }}{{ llmTestResult.text }}
            </div>

            <div class="modal-actions">
              <n-button size="small" :loading="llmTesting" @click="doTestLlm">测试连接</n-button>
              <n-button size="small" type="primary" :loading="llmSaving" @click="doSaveLlm">保存</n-button>
            </div>
          </div>
          <div v-else class="archive-empty">加载中…</div>
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
  display: flex;
  align-items: center;
  justify-content: space-between;
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
  gap: 10px;
  align-items: center;
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
  border: 1px solid var(--fd-accent-200);
  border-radius: var(--fd-r-sm);
  padding: 8px 12px;
}
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.test-result {
  font-size: 12.5px;
  padding: 6px 10px;
  border-radius: 6px;
}
.test-result.ok { color: #2e7d50; background: #e3f3e9; }
.test-result.bad { color: #a63d3d; background: #fbe6e6; }

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
  flex: 1;
  min-height: 0;
  border: var(--fd-border);
  border-radius: var(--fd-r-lg);
  box-shadow: var(--fd-e2);
  overflow: hidden;
  background: var(--fd-paper);
}

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
  overflow-y: auto;
  background: var(--fd-surface);
  border: var(--fd-border);
  border-radius: var(--fd-r-lg);
  box-shadow: var(--fd-e1);
}

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
  border-bottom-right-radius: var(--fd-r-sm);
}
.modal-wide { width: 460px; }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
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
  border-radius: 8px 8px 8px 3px;
  box-shadow: var(--fd-e1);
}
.archive-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.archive-meta small { color: var(--fd-ink-400); font-size: 11.5px; }
.archive-actions { display: flex; gap: 6px; flex: none; }
.archive-foot {
  justify-content: flex-start;
  border-top: 1.5px dashed var(--fd-accent-200);
  padding-top: 10px;
}
</style>
