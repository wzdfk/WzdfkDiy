const fs = require('node:fs')
const path = require('node:path')
const { execSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')

const llm = read('backend/app/core/llm.py')
const route = read('backend/app/api/routes_style.py')

const checks = [
  {
    name: '提示词要求 reply 与 changes 一致',
    ok: /reply 必须与 changes 一致/.test(llm),
  },
  {
    name: '提示词给出悬停缩放/回弹的字段映射',
    ok: /悬停放大\/缩放\/俏皮.*motion\.hover = "tilt"/s.test(llm)
      && /回弹更强\/更软\/更慢.*motion\.easing_pop/s.test(llm),
  },
  {
    name: 'easing 已进入白名单并做格式校验',
    ok: /_EASINGS = \{"motion\.easing_pop", "motion\.easing_out"\}/.test(llm)
      && /if path in _EASINGS:[\s\S]*?_EASING_RE\.fullmatch/.test(llm),
  },
  {
    name: '导出仍包含 style.json/base.css/style.css/STYLE_PROMPT.md',
    ok: ['style.json', 'base.css', 'style.css', 'STYLE_PROMPT.md']
      .every((f) => route.includes(`zf.writestr("${f}"`)),
  },
  {
    name: '中文色彩词会归一化为 hex 再校验',
    ok: /def _normalize_value\(/.test(llm)
      && /_COLOR_WORDS/.test(llm)
      && /value = _normalize_value\(path, raw_value\)/.test(llm),
  },
  {
    name: '模型有回复但改动无效时不再落到 V0 占位文案',
    ok: /模型改动全部未通过字段校验，保留当前风格/.test(llm)
      && /本轮模型建议未通过字段校验，样式保持不变/.test(llm),
  },
]

let runtimeOk = false
let runtimeDetail = ''
const py = [
  'from app.core import llm',
  'from app.core.tokens import fold_default',
  "assert llm._valid_change('motion.hover', 'tilt')",
  "assert llm._valid_change('motion.easing_pop', 'cubic-bezier(.2, 1.8, .4, 1)')",
  "assert not llm._valid_change('motion.easing_pop', 'url(javascript:alert(1))')",
  'd = fold_default().model_dump()',
  'applied = llm._apply_changes(d, [',
  "  {'path': 'motion.hover', 'value': 'tilt', 'reason': 'x'},",
  "  {'path': 'motion.easing_pop', 'value': 'cubic-bezier(.2, 1.8, .4, 1)', 'reason': 'y'},",
  '])',
  'assert len(applied) == 2',
  't = type(fold_default()).model_validate(d)',
  "assert t.motion.hover == 'tilt'",
  "assert t.motion.easing_pop == 'cubic-bezier(.2, 1.8, .4, 1)'",
  'd2 = fold_default().model_dump()',
  'applied2 = llm._apply_changes(d2, [',
  "  {'path': 'color.paper', 'value': '深灰底色', 'reason': 'x'},",
  "  {'path': 'color.accent.s500', 'value': '钢青金属主色', 'reason': 'y'},",
  "  {'path': 'color.ink.ink900', 'value': '浅色', 'reason': 'z'},",
  '])',
  'assert len(applied2) == 10',
  't2 = type(fold_default()).model_validate(d2)',
  "assert t2.color.paper == '#2f3437'",
  "assert t2.color.accent.s500 == '#5b7c89'",
  "assert t2.color.ink.ink900 == '#eef1f4'",
  "print('RUNTIME_OK')",
].join('\n')
const tmpPy = path.join(root, 'backend', '_verify_llm_changes_tmp.py')
try {
  fs.writeFileSync(tmpPy, py, 'utf8')
  const out = execSync('python _verify_llm_changes_tmp.py', {
    cwd: path.join(root, 'backend'),
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  runtimeOk = out.includes('RUNTIME_OK')
} catch (e) {
  runtimeDetail = String(e.stderr || e.message).trim().split('\n').pop()
} finally {
  fs.rmSync(tmpPy, { force: true })
}
checks.push({ name: '动效改动可通过校验并写入 tokens', ok: runtimeOk })

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}${c.ok ? '' : `  ${runtimeDetail}`}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
