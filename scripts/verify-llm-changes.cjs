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
