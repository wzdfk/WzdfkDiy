const fs = require('node:fs')
const path = require('node:path')
const { execSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')

const llm = read('backend/app/core/llm.py')
const styleTpl = read('backend/app/templates/style.css.j2')
const baseTpl = read('backend/app/templates/base.css.j2')
const route = read('backend/app/api/routes_style.py')
const types = read('frontend/src/types/style.ts')
const store = read('frontend/src/stores/style.ts')
const panel = read('frontend/src/components/ChatPanel.vue')

const checks = [
  {
    name: '提示词支持 rewrite/adjust 且取消 2-5 项限制',
    ok: /"mode":"rewrite"/.test(llm)
      && /"mode":"adjust"/.test(llm)
      && !/通常 2-5 项/.test(llm)
      && !/宁少勿滥/.test(llm),
  },
  {
    name: 'parse_prompt 以空模板为基底',
    ok: /template = blank_default\(\)\.model_dump_json/.test(llm)
      && /merged = _deep_merge\(blank_default\(\)\.model_dump\(\), data\)/.test(llm),
  },
  {
    name: 'rewrite 构造完整 tokens 并生成全路径 diff',
    ok: /def _tokens_from_rewrite_payload\(/.test(llm)
      && /def _diff_tokens\(/.test(llm)
      && /"mode": "rewrite"/.test(llm),
  },
  {
    name: '白名单扩展到投影级别与 spacing',
    ok: /_ELEVATION_LEVELS/.test(llm)
      && /path == "spacing.steps"/.test(llm)
      && /"spacing.unit"/.test(llm),
  },
  {
    name: '预览模板去除 FOLD 硬编码签名',
    ok: /var\(--\{\{ p \}\}-border-style\)/.test(styleTpl)
      && !/border-top: 1\.5px dashed/.test(styleTpl)
      && /t\.motion\.hover == "press"/.test(styleTpl)
      && /transform: none/.test(styleTpl)
      && /--\{\{ p \}\}-border-style/.test(baseTpl),
  },
  {
    name: '导出提示词由 LLM 反向生成',
    ok: /def reverse_prompt\(/.test(llm)
      && /zf\.writestr\("STYLE_PROMPT\.md", llm\.reverse_prompt\(tokens\)\)/.test(route),
  },
  {
    name: '前端识别重写模式并展示标识',
    ok: /mode\?: 'rewrite' \| 'adjust'/.test(types)
      && /msg\.mode = ev\.mode/.test(store)
      && /msg\.mode === 'rewrite'/.test(panel),
  },
]

let runtimeOk = false
let runtimeDetail = ''
const py = [
  'import asyncio',
  'from app.core import llm',
  'from app.core.tokens import blank_default',
  'from app.core.css_gen import render_combined_css',
  'b = blank_default()',
  'assert llm._valid_change("elevation.levels.e1", "0 2px 8px rgba(0,0,0,.4)")',
  'assert llm._valid_change("spacing.unit", 8)',
  'assert llm._valid_change("spacing.steps", [4, 8, 12])',
  'r = b.model_copy(deep=True)',
  "r.color.paper = '#23262a'",
  "r.shape.radius.lg = '8px'",
  "r.meta.name = '工业风'",
  'd = llm._diff_tokens(b, r)',
  "assert any(x['path'] == 'color.paper' for x in d)",
  "assert any(x['path'] == 'shape.radius.lg' for x in d)",
  "assert all(x['reason'] == '整体风格重写' for x in d)",
  'css = render_combined_css(b)',
  "assert 'border-top: 1.5px dashed' not in css",
  "assert 'border-top: 1.5px var(--fd-border-style)' in css",
  "assert '.fd-spring:hover { transform: none; }' in css",
  'async def fake_stream(system, user, history=None):',
  '    yield "content", "{\\"mode\\":\\"rewrite\\",\\"tokens\\":{\\"meta\\":{\\"name\\":\\"工业风\\"},\\"color\\":{\\"paper\\":\\"#23262a\\"}},\\"reply\\":\\"done\\"}"',
  'async def run():',
  '    out = []',
  '    async for ev in llm.chat_diff_stream(b, "做工业风"):',
  '        out.append(ev)',
  '    return out',
  'llm.enabled = lambda: True',
  'llm.raw_chat_stream = fake_stream',
  'events = asyncio.run(run())',
  "done = [e for e in events if e['type'] == 'done'][0]",
  "assert done['mode'] == 'rewrite'",
  "assert done['tokens']['meta']['name'] == '工业风'",
  "assert any(x['path'] == 'color.paper' for x in done['diff'])",
  'llm.enabled = lambda: False',
  'assert len(llm.reverse_prompt(b)) > 20',
  "print('RUNTIME_OK')",
].join('\n')
const tmpPy = path.join(root, 'backend', '_verify_open_loop_tmp.py')
try {
  fs.writeFileSync(tmpPy, py, 'utf8')
  const out = execSync('python _verify_open_loop_tmp.py', {
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
checks.push({ name: 'rewrite 事件流 / diff / token 驱动 CSS 运行时校验', ok: runtimeOk })

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}${c.ok ? '' : `  ${runtimeDetail}`}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
