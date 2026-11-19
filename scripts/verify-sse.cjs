const fs = require('node:fs')
const path = require('node:path')
const { execSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')

const llm = read('backend/app/core/llm.py')
const route = read('backend/app/api/routes_style.py')
const api = read('frontend/src/api/style.ts')
const store = read('frontend/src/stores/style.ts')
const panel = read('frontend/src/components/ChatPanel.vue')
const types = read('frontend/src/types/style.ts')

const checks = [
  {
    name: '后端支持 OpenAI 兼容流式调用与 reasoning 透传',
    ok: /async def raw_chat_stream\(/.test(llm)
      && /reasoning_content.*reasoning/.test(llm)
      && /"stream": True/.test(llm),
  },
  {
    name: 'chat_diff_stream 输出思考/整理/校验/最终阶段',
    ok: /async def chat_diff_stream\(/.test(llm)
      && ['thinking', 'generating', 'organizing', 'validating', 'applying', 'done']
        .every(s => llm.includes(`"${s}"`)),
  },
  {
    name: '后端提供 SSE 路由并写入会话/撤销栈',
    ok: /@router\.post\("\/chat\/stream"\)/.test(route)
      && /text\/event-stream/.test(route)
      && /_push_snapshot\(\)/.test(route)
      && /_session\["default"\] = StyleTokens\.model_validate\(final\["tokens"\]\)/.test(route),
  },
  {
    name: '前端 fetch 解析 SSE 并逐条回调',
    ok: /export async function chatStream\(/.test(api)
      && /getReader\(\)/.test(api)
      && /split\('\\n\\n'\)/.test(api)
      && /onEvent\(JSON\.parse\(data\)/.test(api),
  },
  {
    name: 'store 用流式消息承载 trace/raw/reasoning',
    ok: /await api\.chatStream\(/.test(store)
      && /streaming: true, trace: \[\]/.test(store)
      && /msg\.raw = \(msg\.raw \?\? ''\)/.test(store)
      && /msg\.reasoning = \(msg\.reasoning \?\? ''\)/.test(store),
  },
  {
    name: '聊天气泡可展开查看过程',
    ok: /查看思考 \/ 整理过程/.test(panel)
      && /stageLabel\(t\)/.test(panel)
      && /msg\.reasoning/.test(panel)
      && /ChatStreamEvent/.test(types),
  },
  {
    name: 'SSE done 载荷使用 JSON 兼容 tokens',
    ok: (llm.match(/nt\.model_dump\(mode="json"\)/g) || []).length >= 3
      && /default=str/.test(route),
  },
  {
    name: '异常时下发 error 事件且前端退出生成中',
    ok: /_sse\("error"/.test(route)
      && /ev\.type === 'error'/.test(store)
      && /if \(msg\?\.streaming\) msg\.streaming = false/.test(store),
  },
]

let runtimeOk = false
let runtimeDetail = ''
const py = [
  'import asyncio',
  'from app.core import llm',
  'from app.core.tokens import fold_default',
  'llm.enabled = lambda: False',
  'async def main():',
  '    events = []',
  '    async for ev in llm.chat_diff_stream(fold_default(), "俏皮一点"):',
  '        events.append(ev)',
  '    return events',
  'events = asyncio.run(main())',
  "types = [e['type'] for e in events]",
  "assert 'stage' in types and 'thought' in types and 'done' in types",
  "assert any(e.get('stage') == 'thinking' for e in events)",
  "done = [e for e in events if e['type'] == 'done'][0]",
  "assert done['tokens']['meta']['name']",
  "assert isinstance(done['tokens']['meta']['created'], str)",
  'import json',
  "json.dumps(done['tokens'], ensure_ascii=False)",
  "assert isinstance(done['diff'], list)",
  "print('RUNTIME_OK')",
].join('\n')
const tmpPy = path.join(root, 'backend', '_verify_sse_tmp.py')
try {
  fs.writeFileSync(tmpPy, py, 'utf8')
  const out = execSync('python _verify_sse_tmp.py', {
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
checks.push({ name: '流式生成器可产出完整事件序列', ok: runtimeOk })

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}${c.ok ? '' : `  ${runtimeDetail}`}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
