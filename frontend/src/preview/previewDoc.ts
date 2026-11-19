/**
 * 预览文档构建：五组件验证页（对应 docs/效果验证组件.md + Badge）。
 * 页面内不写任何风格样式 —— 全部样式来自注入的生成 CSS（所见即所导）。
 */
export const STYLE_TAG_ID = 'uidiy-style'

const DEMO_HTML = `
<main class="wrap">
  <header style="margin-bottom:40px;">
    <span class="fd-label">STYLE PREVIEW · 实时预览</span>
    <h1 class="fd-display" style="margin:8px 0 4px;">五组件验证页</h1>
    <p style="color:var(--fd-ink-600);font-size:14px;max-width:560px;">
      本页样式 100% 由当前风格 tokens 生成。Button 定调 · Input 定质感 · Toast 定气质 · Card 定骨架 · Dropdown 定延展。
    </p>
  </header>

  <!-- Button -->
  <section>
    <span class="fd-label">BUTTON · 按钮（交互签名在此）</span>
    <div class="fd-card" style="margin:12px 0 36px;padding:28px;">
      <div class="row">
        <button class="fd-btn fd-btn-primary">主要操作</button>
        <button class="fd-btn">次要操作</button>
        <button class="fd-btn fd-btn-ghost">幽灵按钮</button>
        <button class="fd-btn fd-btn-danger">危险操作</button>
        <button class="fd-btn" disabled>禁用状态</button>
      </div>
    </div>
  </section>

  <!-- Card -->
  <section>
    <span class="fd-label">CARD · 卡片（骨架与层次）</span>
    <div class="grid" style="margin:12px 0 36px;">
      <div class="fd-card">
        <h3 class="fd-title">站点概览</h3>
        <p class="muted">设备接入数量与整体运行状态，每 5 分钟自动刷新。</p>
        <div class="meta"><span>更新于 12 分钟前</span><span class="fd-badge fd-badge-ok">✓ 运行中</span></div>
      </div>
      <div class="fd-card">
        <h3 class="fd-title">今日告警</h3>
        <p class="muted">共 3 条未处理：1 条设备离线，2 条信号波动。</p>
        <div class="meta"><span>更新于 3 分钟前</span><span class="fd-badge fd-badge-warn">! 待处理</span></div>
      </div>
      <div class="fd-card">
        <h3 class="fd-title">同步任务</h3>
        <p class="muted">夜间批量同步已完成 87%，预计 40 分钟后结束。</p>
        <div class="meta"><span>更新于 1 分钟前</span><span class="fd-badge fd-badge-info">● 进行中</span></div>
      </div>
    </div>
  </section>

  <!-- Input -->
  <section>
    <span class="fd-label">INPUT · 输入框（质感与焦点）</span>
    <div class="fd-card" style="margin:12px 0 36px;padding:28px;">
      <div class="fd-field">
        <label>站点名称</label>
        <input class="fd-input" placeholder="请输入站点名称（点进来看 focus）">
        <span class="fd-hint">Tab 键切换，感受焦点环样式</span>
      </div>
      <div class="fd-field fd-error">
        <label>端口号</label>
        <input class="fd-input" value="90000">
        <span class="fd-hint">端口号需在 1 – 65535 之间</span>
      </div>
    </div>
  </section>

  <!-- Toast -->
  <section>
    <span class="fd-label">TOAST · 轻通知（气质与动效）</span>
    <div class="fd-card" style="margin:12px 0 36px;padding:28px;">
      <div class="row">
        <button class="fd-btn fd-btn-primary" data-toast="ok">触发成功通知</button>
        <button class="fd-btn" data-toast="warn">触发预警通知</button>
        <button class="fd-btn fd-btn-danger" data-toast="danger">触发故障通知</button>
        <button class="fd-btn fd-btn-ghost" data-toast="info">触发信息通知</button>
      </div>
      <div id="toast-area" style="margin-top:16px;display:flex;flex-direction:column;gap:10px;"></div>
    </div>
  </section>

  <!-- Dropdown -->
  <section>
    <span class="fd-label">DROPDOWN · 下拉（浮层与延展）</span>
    <div class="fd-card dd-stage" style="margin:12px 0 36px;padding:28px;">
      <div class="dd">
        <button class="fd-btn fd-btn-primary">选择主题色 ▾</button>
        <div class="fd-menu dd-menu">
          <div class="fd-opt fd-opt-selected">✓ 当前主题</div>
          <div class="fd-opt">备选主题 A</div>
          <div class="fd-opt">备选主题 B</div>
          <div class="fd-opt">备选主题 C</div>
        </div>
      </div>
    </div>
  </section>

  <!-- Badge & Link -->
  <section>
    <span class="fd-label">BADGE &amp; LINK</span>
    <div class="fd-card" style="margin:12px 0;padding:28px;">
      <div class="row">
        <span class="fd-badge fd-badge-ok">✓ 正常</span>
        <span class="fd-badge fd-badge-warn">! 预警</span>
        <span class="fd-badge fd-badge-danger">✕ 故障</span>
        <span class="fd-badge fd-badge-info">● 待机</span>
        <span class="fd-badge">默认标签</span>
      </div>
      <p style="margin-top:16px;font-size:14px;">
        链接：<a class="fd-link" href="javascript:void(0)">下划线扫入效果</a>
      </p>
    </div>
  </section>
</main>
`

const DEMO_CSS = `
/* 仅演示布局，不含任何风格值 */
body { padding: 40px 24px 64px; }
.wrap { max-width: 820px; margin: 0 auto; }
.row { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 20px; }
.muted { font-size: 13.5px; color: var(--fd-ink-600); margin-top: 8px; }
section { margin-bottom: 8px; }
section > .fd-label { display: block; margin-bottom: 12px; }
.fd-card .meta { font-size: 12px; color: var(--fd-ink-400); }
/* Dropdown 演示交互（浮层显隐，非风格） */
.dd { position: relative; display: inline-block; }
.dd-menu { position: absolute; top: calc(100% + 8px); left: 0; z-index: 10; opacity: 0; visibility: hidden; transform: translateY(-4px); transition: all .18s var(--fd-ease-pop, ease); }
.dd:hover .dd-menu { opacity: 1; visibility: visible; transform: translateY(0); }
`

const DEMO_JS = `
// Toast 触发演示
const area = document.getElementById('toast-area')
const texts = {
  ok: ['配置已保存', '站点配置已保存，5 秒后自动关闭'],
  warn: ['信号波动', '设备信号波动，请关注链路质量'],
  danger: ['设备离线', '设备离线，已触发告警并通知责任人'],
  info: ['任务进行中', '夜间批量同步正在进行，预计 40 分钟后结束'],
}
document.querySelectorAll('[data-toast]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    const type = btn.getAttribute('data-toast')
    const t = texts[type]
    const el = document.createElement('div')
    el.className = 'fd-toast fd-toast-' + type
    el.textContent = t[1]
    area.appendChild(el)
    setTimeout(function () { el.remove() }, 4000)
  })
})
`

export function buildPreviewDoc(): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style id="${STYLE_TAG_ID}">/* 生成 CSS 注入点 */</style>
<style>${DEMO_CSS}</style>
</head>
<body>
${DEMO_HTML}
<script>${DEMO_JS}<\/script>
</body>
</html>`
}
