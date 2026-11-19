const fs = require('node:fs')
const path = require('node:path')

const file = path.resolve(__dirname, '..', '.gitignore')
const text = fs.readFileSync(file, 'utf8')
const lines = text.split(/\r?\n/).map(l => l.trim())

const required = [
  'node_modules/',
  'dist/',
  'backend/output/',
  '__pycache__/',
  '*.py[cod]',
  '.pytest_cache/',
  '.env',
  '*.log',
  '.playwright-cli/',
  '供电监控仪表盘UI_assets/',
  '!.env.example',
]

const forbidden = ['*.py', '*.vue', '*.ts', '*.js', '*.css', '*.html', '*.md', '*.json']

const checks = [
  ...required.map(p => ({
    name: `已忽略 ${p}`,
    ok: lines.includes(p),
  })),
  ...forbidden.map(p => ({
    name: `未误忽略源码 ${p}`,
    ok: !lines.includes(p),
  })),
]

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
