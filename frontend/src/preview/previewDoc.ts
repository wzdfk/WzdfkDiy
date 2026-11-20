/**
 * V2 预览文档：只负责承载当前产物包。
 * 预览 HTML 由模型生成；这里不再固定七组件验证页，也不注入风格样式。
 */
export const STYLE_TAG_ID = 'uidiy-style'

export const DEFAULT_PREVIEW_HTML = `<main class="uidiy-preview">
  <h1>风格预览</h1>
  <p>当前产物包未提供 preview.html，使用最小回退结构。</p>
  <button class="fd-btn fd-btn-primary">主要操作</button>
  <div class="fd-card">卡片内容</div>
</main>`

function injectStyleTag(html: string): string {
  const tag = `<style id="${STYLE_TAG_ID}">/* 生成 CSS 注入点 */</style>`
  if (/<html[\s>]/i.test(html)) {
    if (/<\/head>/i.test(html)) return html.replace(/<\/head>/i, `${tag}</head>`)
    if (/<body[^>]*>/i.test(html)) return html.replace(/<body([^>]*)>/i, `<body$1>${tag}`)
    return `${tag}${html}`
  }
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
${tag}
</head>
<body>
${html}
</body>
</html>`
}

export function buildPreviewDoc(html: string = DEFAULT_PREVIEW_HTML): string {
  return injectStyleTag(html || DEFAULT_PREVIEW_HTML)
}
