const fs = require('node:fs')
const path = require('node:path')
const { execSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')
const backend = path.join(root, 'backend')

const moduleText = read('backend/app/core/logging_config.py')
const mainText = read('backend/app/main.py')
const styleRoutes = read('backend/app/api/routes_style.py')
const settingsRoutes = read('backend/app/api/routes_settings.py')
const gitignore = read('.gitignore')

const checks = [
  {
    name: '日志文件为 backend/logs/diy.log',
    ok: /_LOG_DIR = _BASE_DIR \/ "logs"/.test(moduleText)
      && /_LOG_FILE = _LOG_DIR \/ "diy\.log"/.test(moduleText),
  },
  {
    name: '每日 24 小时轮转',
    ok: /when="midnight"/.test(moduleText) && /interval=1/.test(moduleText),
  },
  {
    name: '轮转文件名为 diy.log_年月日',
    ok: /file_handler\.suffix = "%Y%m%d"/.test(moduleText)
      && /path\.replace\("diy\.log\.", "diy\.log_", 1\)/.test(moduleText),
  },
  {
    name: '控制台格式比文件更详细（文件名/行号/函数名）',
    ok: /_CONSOLE_FORMAT[\s\S]*?filename[\s\S]*?lineno[\s\S]*?funcName/.test(moduleText),
  },
  {
    name: '入口初始化日志并接管 uvicorn',
    ok: /logger = setup_logging\(\)/.test(mainText)
      && /log_config=None/.test(mainText),
  },
  {
    name: '不再逐请求输出访问日志',
    ok: !/REQ %s/.test(mainText) && /只在异常时记录/.test(mainText),
  },
  {
    name: 'uvicorn 访问日志静音，错误级保留',
    ok: /getLogger\("uvicorn\.access"\)[\s\S]*?NullHandler/.test(moduleText)
      && /getLogger\("uvicorn\.error"\)[\s\S]*?WARNING/.test(moduleText),
  },
  {
    name: '控制台只显示 INFO，DEBUG 仅写文件',
    ok: /console_handler\.setLevel\(logging\.INFO\)/.test(moduleText)
      && /file_handler\.setLevel\(logging\.DEBUG\)/.test(moduleText),
  },
  {
    name: '只保留用户操作类业务日志',
    ok: /对话调整 message=/.test(styleRoutes)
      && /存档 name=/.test(styleRoutes)
      && /加载档案 id=/.test(styleRoutes)
      && /保存 LLM 设置/.test(settingsRoutes),
  },
  {
    name: 'logs 目录已被 .gitignore 忽略',
    ok: /logs\//.test(gitignore),
  },
]

let runtimeOk = false
let runtimeDetail = ''
try {
  execSync('python -c "from app.core.logging_config import setup_logging; setup_logging().info(\'verify-logging-runtime\')"', {
    cwd: backend,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  const logFile = path.join(backend, 'logs', 'diy.log')
  runtimeOk = fs.existsSync(logFile) && fs.readFileSync(logFile, 'utf8').includes('verify-logging-runtime')
  runtimeDetail = runtimeOk ? '' : ' diy.log 未写入测试标记'
} catch (e) {
  runtimeDetail = String(e.stderr || e.message).trim().split('\n').pop()
}
checks.push({ name: '运行时双写文件可写', ok: runtimeOk })

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}${c.ok ? '' : `  ${runtimeDetail}`}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
