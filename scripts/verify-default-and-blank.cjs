const fs = require('node:fs')
const path = require('node:path')
const { execSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')

const tokens = read('backend/app/core/tokens.py')
const route = read('backend/app/api/routes_style.py')
const api = read('frontend/src/api/style.ts')
const store = read('frontend/src/stores/style.ts')
const view = read('frontend/src/views/StudioView.vue')
const panel = read('frontend/src/components/TokenPanel.vue')

const checks = [
  {
    name: '系统默认风格已重命名',
    ok: /name="系统默认风格"/.test(tokens),
  },
  {
    name: '空模板工厂存在且为零装饰',
    ok: /def blank_default\(\) -> StyleTokens:/.test(tokens)
      && /radius=Radius\(lg="0px", md="0px", sm="0px"\)/.test(tokens)
      && /levels=\{"e1": "none", "e2": "none", "e3": "none"\}/.test(tokens)
      && /hover="none"/.test(tokens),
  },
  {
    name: '后端提供 /style/blank 接口',
    ok: /@router\.post\("\/blank"\)/.test(route) && /blank_default\(\)/.test(route),
  },
  {
    name: '前端 API 与 store 已接入空模板',
    ok: /useBlankTemplate/.test(api)
      && /async function useBlankTemplate\(\)/.test(store)
      && /useBlankTemplate,/.test(store),
  },
  {
    name: '档案弹窗有“使用空模板”按钮',
    ok: /@click="doUseBlank">使用空模板</.test(view) && /async function doUseBlank\(\)/.test(view),
  },
  {
    name: '重置按钮文案同步为系统默认风格',
    ok: /重置为系统默认风格/.test(panel) && /已重置为「系统默认风格」/.test(store),
  },
  {
    name: '空模板基线不预填保留名，并引导重命名',
    ok: /BLANK_TEMPLATE_NAME = '空模板'/.test(view)
      && /isBlankBaseline\.value \? '' :/.test(view)
      && /:placeholder="savePlaceholder"/.test(view),
  },
  {
    name: '直接保存为“空模板”会被阻止并提示',
    ok: /name === BLANK_TEMPLATE_NAME/.test(view)
      && /「空模板」是内置基线名称/.test(view),
  },
  {
    name: '色彩控件使用具名处理器（不是只求值不调用）',
    ok: /const onPaperChange = onColor\('paper'\)/.test(panel)
      && /const onSurfaceChange = onColor\('surface'\)/.test(panel)
      && /const onInk900Change = onColor\('ink900'\)/.test(panel)
      && /@update:value="onPaperChange"/.test(panel)
      && /@update:value="onSurfaceChange"/.test(panel)
      && /@update:value="onInk900Change"/.test(panel)
      && !/@update:value="onColor\('/.test(panel),
  },
]

let runtimeOk = false
let runtimeDetail = ''
const py = [
  'from app.core.tokens import blank_default, fold_default',
  'from app.core.css_gen import render_combined_css',
  "assert fold_default().meta.name == '系统默认风格'",
  'b = blank_default()',
  "assert b.meta.name == '空模板'",
  "assert b.shape.radius.lg == '0px'",
  "assert all(v == 'none' for v in b.elevation.levels.values())",
  "assert b.motion.hover == 'none'",
  'css = render_combined_css(b)',
  "assert '--fd-r-lg: 0px' in css",
  "print('RUNTIME_OK')",
].join('; ')
try {
  const out = execSync(`python -c "${py}"`, {
    cwd: path.join(root, 'backend'),
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  runtimeOk = out.includes('RUNTIME_OK')
} catch (e) {
  runtimeDetail = String(e.stderr || e.message).trim().split('\n').pop()
}
checks.push({ name: '空模板 tokens 可生成朴素 CSS', ok: runtimeOk })

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}${c.ok ? '' : `  ${runtimeDetail}`}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
