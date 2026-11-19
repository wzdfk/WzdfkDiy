const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')

const db = read('backend/app/core/db.py')
const route = read('backend/app/api/routes_style.py')
const store = read('frontend/src/stores/style.ts')
const view = read('frontend/src/views/StudioView.vue')

const checks = [
  {
    name: 'db.load_archive 返回 (tokens, 档案名)',
    ok: /def load_archive\(archive_id: int\) -> tuple\[StyleTokens, str\]:/.test(db)
      && /return StyleTokens\.model_validate_json\(row\.tokens_json\), row\.name/.test(db),
  },
  {
    name: '加载路由用档案名覆盖 meta.name',
    ok: /tokens, archive_name = archive_db\.load_archive\(archive_id\)/.test(route)
      && /tokens\.meta\.name = archive_name/.test(route),
  },
  {
    name: '不再以单值方式调用 load_archive',
    ok: !/tokens = archive_db\.load_archive\(archive_id\)/.test(route),
  },
  {
    name: '前端加载提示读取更新后的 meta.name',
    ok: /已加载档案「\$\{res\.tokens\.meta\.name\}」/.test(store),
  },
  {
    name: '顶栏读取当前 tokens.meta.name',
    ok: /store\.tokens\.meta\.name/.test(view),
  },
  {
    name: 'store 维护当前档案名',
    ok: /const activeArchiveName = ref<string \| null>\(null\)/.test(store)
      && /activeArchiveName,/.test(store),
  },
  {
    name: '加载档案时记录当前档案名',
    ok: /activeArchiveName\.value = res\.tokens\.meta\.name/.test(store),
  },
  {
    name: '另存为后新名字成为当前档案并同步后端',
    ok: /next\.meta\.name = name/.test(store)
      && /api\.saveCurrent\(next\)/.test(store)
      && /activeArchiveName\.value = name/.test(store),
  },
  {
    name: '存档弹窗默认取当前档案名，回退到风格名',
    ok: /store\.activeArchiveName \?\? store\.tokens\?\.meta\.name \?\? ''/.test(view),
  },
  {
    name: '新建/重置风格时清空当前档案名',
    ok: (store.match(/activeArchiveName\.value = null/g) || []).length >= 2,
  },
]

let failed = 0
for (const c of checks) {
  console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}`)
  if (!c.ok) failed++
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`)
process.exitCode = failed ? 1 : 0
