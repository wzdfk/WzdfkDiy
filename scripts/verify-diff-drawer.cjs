const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')

const store = read('frontend/src/stores/style.ts')
const view = read('frontend/src/views/StudioView.vue')
const preview = read('frontend/src/components/StylePreview.vue')

const checks = [
  {
    name: '预览组件支持传入基准 CSS',
    ok: /defineProps<\{ css\?: string \}\>/.test(preview)
      && /const activeCss = computed\(\(\) => props\.css \?\? store\.css\)/.test(preview)
      && /if \(tag\) tag\.textContent = activeCss\.value/.test(preview),
  },
  {
    name: 'store 保存基准 CSS 并标记待确认 diff',
    ok: /export interface PendingDiff/.test(store)
      && /const pendingDiff = ref<PendingDiff \| null>\(null\)/.test(store)
      && /const baselineCss = css\.value/.test(store)
      && /pendingDiff\.value = \{ baselineCss, diff, reply: res\.reply \}/.test(store),
  },
  {
    name: '接受只收起对比，不撤销后端改动',
    ok: /function acceptDiff\(\)/.test(store)
      && /pendingDiff\.value = null[\s\S]{0,120}已接受本轮修改/.test(store),
  },
  {
    name: '拒绝通过 undo 回到基准',
    ok: /async function rejectDiff\(\)/.test(store)
      && /const res = await queueWrite\(\(\) => api\.undo\(\)\)/.test(store)
      && /tokens\.value = res\.tokens/.test(store),
  },
  {
    name: '其他变更会清除待确认 diff',
    ok: (store.match(/pendingDiff\.value = null/g) || []).length >= 6,
  },
  {
    name: '中间预览有基准/新预览并排与接受拒绝按钮',
    ok: /class="diff-view"/.test(view)
      && /:css="store\.pendingDiff\.baselineCss"/.test(view)
      && /store\.acceptDiff\(\)/.test(view)
      && /store\.rejectDiff\(\)/.test(view),
  },
  {
    name: 'TokenPanel 收起为预览区右上角图标按钮',
    ok: /const tokenDrawerOpen = ref\(false\)/.test(view)
      && /class="drawer-fab"/.test(view)
      && /\.drawer-fab \{[\s\S]*?position: absolute;[\s\S]*?top: 10px;[\s\S]*?right: 10px;/.test(view)
      && /<section v-if="tokenDrawerOpen" class="right">/.test(view)
      && !/class="token-handle"/.test(view),
  },
]

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
