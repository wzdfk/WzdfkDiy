"""自由风格产物包 V2。

V2 不再把 StyleTokens 当事实源：
- LLM 直接输出 base.css / style.css / preview.html / STYLE_PROMPT；
- 系统只固定产物包结构、导出文件结构和溯源信息；
- 视觉内容不做 schema、枚举、白名单限制。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .css_gen import render_base_css, render_style_css
from .tokens import StyleTokens

EXPORT_FILES = (
    "manifest.json",
    "STYLE_PROMPT.md",
    "preview.html",
    "base.css",
    "style.css",
    "raw-llm.json",
    "source-conversation.json",
    "CHANGELOG.md",
)

_FALLBACK_PREVIEW_HTML = """<main class="uidiy-showcase">
  <style>
    .uidiy-showcase { max-width:980px; margin:0 auto; display:flex; flex-direction:column; gap:28px; }
    .uidiy-showcase header { display:flex; flex-direction:column; gap:6px; }
    .uidiy-showcase section { display:flex; flex-direction:column; gap:10px; }
    .uidiy-row { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
    .uidiy-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }
    .uidiy-muted { color:var(--fd-ink-600); font-size:13px; margin-top:4px; }

    /* Dropdown：点击型由 JS 切 is-open，hover 型由 CSS :hover */
    .uidiy-dropdown { position:relative; display:inline-flex; }
    .uidiy-menu {
      position:absolute; top:calc(100% + 6px); left:0; z-index:10;
      opacity:0; visibility:hidden; transform:translateY(-4px);
      transition:opacity var(--fd-dur) var(--fd-ease-out),
                 transform var(--fd-dur) var(--fd-ease-pop),
                 visibility var(--fd-dur);
    }
    .uidiy-dropdown.is-open .uidiy-menu,
    .uidiy-hover-dd:hover .uidiy-menu {
      opacity:1; visibility:visible; transform:translateY(0);
    }

    /* Toast 栈：点击按钮后动态插入，复用 fd-toast 的签名动效 */
    .uidiy-toast-stack { display:flex; flex-direction:column; align-items:flex-start; gap:10px; min-height:40px; }
    .uidiy-toast-stack:empty::before { content:"点上方按钮，看通知弹出 ↓"; color:var(--fd-ink-400); font-size:13px; }
  </style>
  <header>
    <h1 class="fd-display">风格预览</h1>
    <p class="uidiy-muted">七组件展示：Button · Card · Input · Toast · Dropdown · Modal · Select</p>
  </header>

  <section>
    <span class="fd-label">BUTTON · 按钮</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <button class="fd-btn fd-btn-primary">主要操作</button>
      <button class="fd-btn">次要操作</button>
      <button class="fd-btn fd-btn-ghost">幽灵按钮</button>
      <button class="fd-btn fd-btn-danger">危险操作</button>
      <button class="fd-btn" disabled>禁用状态</button>
    </div>
  </section>

  <section>
    <span class="fd-label">CARD · 卡片</span>
    <div class="uidiy-grid">
      <div class="fd-card"><h3 class="fd-title">站点概览</h3><p class="uidiy-muted">设备接入数量与整体运行状态。</p><div class="meta"><span>更新于 12 分钟前</span><span class="fd-badge fd-badge-ok">✓ 运行中</span></div></div>
      <div class="fd-card"><h3 class="fd-title">今日告警</h3><p class="uidiy-muted">共 3 条未处理告警。</p><div class="meta"><span>更新于 3 分钟前</span><span class="fd-badge fd-badge-warn">! 待处理</span></div></div>
      <div class="fd-card"><h3 class="fd-title">同步任务</h3><p class="uidiy-muted">夜间批量同步已完成 87%。</p><div class="meta"><span>更新于 1 分钟前</span><span class="fd-badge fd-badge-info">● 进行中</span></div></div>
    </div>
  </section>

  <section>
    <span class="fd-label">INPUT · 输入框</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <input class="fd-input" placeholder="点进来看 focus" style="min-width:260px;">
      <input class="fd-input" value="90000" style="min-width:160px;">
      <span class="uidiy-muted">Tab 键切换，感受焦点环样式</span>
    </div>
  </section>

  <section>
    <span class="fd-label">TOAST · 轻通知</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <button class="fd-btn" data-toast="ok">✓ 保存成功</button>
      <button class="fd-btn" data-toast="warn">! 信号波动</button>
      <button class="fd-btn" data-toast="danger">✕ 设备离线</button>
      <button class="fd-btn" data-toast="info">● 任务进行中</button>
    </div>
    <div class="uidiy-toast-stack" id="uidiy-toast-stack" aria-live="polite"></div>
  </section>

  <section>
    <span class="fd-label">DROPDOWN · 下拉</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <div class="uidiy-dropdown" id="uidiy-dd-click">
        <button class="fd-btn fd-btn-primary uidiy-trigger" aria-haspopup="true" aria-expanded="false">选择主题色 ▾</button>
        <div class="fd-menu uidiy-menu" role="menu">
          <div class="fd-opt fd-opt-selected" data-opt="当前主题">✓ 当前主题</div>
          <div class="fd-opt" data-opt="备选主题 A">备选主题 A</div>
          <div class="fd-opt" data-opt="备选主题 B">备选主题 B</div>
        </div>
      </div>
      <div class="uidiy-dropdown uidiy-hover-dd">
        <button class="fd-btn uidiy-trigger">悬停展开 ▾</button>
        <div class="fd-menu uidiy-menu" role="menu">
          <div class="fd-opt" data-opt="湖蓝">湖蓝</div>
          <div class="fd-opt" data-opt="天青">天青</div>
          <div class="fd-opt" data-opt="玫红">玫红</div>
        </div>
      </div>
    </div>
  </section>

  <section>
    <span class="fd-label">MODAL · 弹窗</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <button class="fd-btn fd-btn-primary" id="uidiy-modal-open">打开弹窗</button>
      <span class="uidiy-muted">点开看遮罩、折角与弹性入场；点遮罩或按 Esc 关闭</span>
    </div>
    <div class="fd-modal-mask" id="uidiy-modal" hidden>
      <div class="fd-modal" role="dialog" aria-modal="true" aria-labelledby="uidiy-modal-title">
        <div class="fd-modal-head">
          <span class="fd-title" id="uidiy-modal-title">确认操作</span>
          <button class="fd-btn fd-btn-ghost fd-btn-tiny" id="uidiy-modal-x" aria-label="关闭">✕</button>
        </div>
        <div class="fd-modal-body">这是第六个验证组件：Modal 弹窗。遮罩、浮层圆角、偏移投影与弹性入场都由当前风格令牌驱动。</div>
        <div class="fd-modal-actions">
          <button class="fd-btn" data-modal-close>取消</button>
          <button class="fd-btn fd-btn-primary" id="uidiy-modal-ok">确认</button>
        </div>
      </div>
    </div>
  </section>

  <section>
    <span class="fd-label">SELECT · 选择器</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <div class="fd-select" id="uidiy-select">
        <button type="button" class="fd-select-trigger" aria-haspopup="listbox" aria-expanded="false">
          <span class="fd-select-value">智谱 GLM</span>
          <span class="fd-select-caret" aria-hidden="true">▾</span>
        </button>
        <div class="fd-select-menu" role="listbox" hidden>
          <div class="fd-select-opt is-selected" data-label="智谱 GLM" role="option"><span class="fd-select-check">✓</span>智谱 GLM</div>
          <div class="fd-select-opt" data-label="DeepSeek" role="option"><span class="fd-select-check">✓</span>DeepSeek</div>
          <div class="fd-select-opt" data-label="OpenAI 兼容" role="option"><span class="fd-select-check">✓</span>OpenAI 兼容</div>
        </div>
      </div>
      <span class="uidiy-muted">点触发器展开，选项点击即选中并弹通知</span>
    </div>
  </section>

  <section>
    <span class="fd-label">BADGE &amp; LINK</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <span class="fd-badge fd-badge-ok">✓ 正常</span>
      <span class="fd-badge fd-badge-warn">! 预警</span>
      <span class="fd-badge fd-badge-danger">✕ 故障</span>
      <span class="fd-badge fd-badge-info">● 待机</span>
      <a class="fd-link" href="javascript:void(0)">下划线扫入效果</a>
    </div>
  </section>

  <script>
  (function () {
    var clickDD = document.getElementById('uidiy-dd-click');
    var trigger = clickDD.querySelector('.uidiy-trigger');
    var stack = document.getElementById('uidiy-toast-stack');
    var toastText = { ok:'配置已保存', warn:'信号波动', danger:'设备离线', info:'任务进行中' };

    function showToast(kind, text) {
      var el = document.createElement('div');
      el.className = 'fd-toast fd-toast-' + kind;
      el.textContent = text || toastText[kind];
      stack.appendChild(el);
      window.setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 3200);
    }
    function setClickOpen(open) {
      clickDD.classList.toggle('is-open', open);
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      setClickOpen(!clickDD.classList.contains('is-open'));
    });
    document.addEventListener('click', function (e) {
      if (!clickDD.contains(e.target)) setClickOpen(false);
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-toast]'), function (btn) {
      btn.addEventListener('click', function () { showToast(btn.getAttribute('data-toast')); });
    });
    Array.prototype.forEach.call(document.querySelectorAll('.uidiy-menu .fd-opt'), function (opt) {
      opt.addEventListener('click', function () {
        var dd = opt.closest('.uidiy-dropdown');
        var label = opt.getAttribute('data-opt');
        Array.prototype.forEach.call(dd.querySelectorAll('.fd-opt'), function (o) {
          o.classList.remove('fd-opt-selected');
          o.textContent = o.getAttribute('data-opt');
        });
        opt.classList.add('fd-opt-selected');
        opt.textContent = '✓ ' + label;
        showToast('info', '已选择：' + label);
        if (dd === clickDD) setClickOpen(false);
      });
    });

    var modal = document.getElementById('uidiy-modal');
    function closeModal() { modal.hidden = true; }
    document.getElementById('uidiy-modal-open').addEventListener('click', function () { modal.hidden = false; });
    document.getElementById('uidiy-modal-x').addEventListener('click', closeModal);
    Array.prototype.forEach.call(document.querySelectorAll('[data-modal-close]'), function (btn) {
      btn.addEventListener('click', closeModal);
    });
    modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });
    document.getElementById('uidiy-modal-ok').addEventListener('click', function () {
      closeModal();
      showToast('ok', '已确认操作');
    });

    var sel = document.getElementById('uidiy-select');
    var selTrigger = sel.querySelector('.fd-select-trigger');
    var selMenu = sel.querySelector('.fd-select-menu');
    var selValue = sel.querySelector('.fd-select-value');
    function setSelOpen(open) {
      selMenu.hidden = !open;
      selTrigger.classList.toggle('is-open', open);
      selTrigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    selTrigger.addEventListener('click', function (e) {
      e.stopPropagation();
      setSelOpen(selMenu.hidden);
    });
    document.addEventListener('click', function (e) {
      if (!sel.contains(e.target)) setSelOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setSelOpen(false);
    });
    Array.prototype.forEach.call(sel.querySelectorAll('.fd-select-opt'), function (opt) {
      opt.addEventListener('click', function () {
        Array.prototype.forEach.call(sel.querySelectorAll('.fd-select-opt'), function (o) {
          o.classList.remove('is-selected');
        });
        opt.classList.add('is-selected');
        var label = opt.getAttribute('data-label');
        selValue.textContent = label;
        setSelOpen(false);
        showToast('info', '已切换：' + label);
      });
    });
  })();
  </script>
</main>"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


class BundleMeta(BaseModel):
    name: str = "未命名风格"
    version: str = "1.0"
    note: str = ""
    created: datetime = Field(default_factory=_now)


class BundleSource(BaseModel):
    prompt: str = ""
    model: str = ""
    base_url: str = ""
    generated_at: datetime = Field(default_factory=_now)
    parent_hash: str = ""
    raw_response: str = ""
    usage: dict[str, Any] | None = None
    duration_ms: int | None = None


class StyleBundle(BaseModel):
    """V2 风格产物包。字段结构固定，字段内视觉内容自由。"""

    schemaVersion: str = "2.0"
    meta: BundleMeta = Field(default_factory=BundleMeta)
    reply: str = ""
    style_prompt: str = ""
    preview_html: str = _FALLBACK_PREVIEW_HTML
    base_css: str = ""
    style_css: str = ""
    semantic_diff: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    source: BundleSource = Field(default_factory=BundleSource)


def bundle_from_legacy_tokens(tokens: StyleTokens, source_prompt: str = "") -> StyleBundle:
    """把 V1 tokens 转成 V2 bundle，用于初始化 / reset / 旧档案兼容。"""
    from .prompt_gen import render_style_prompt

    return StyleBundle(
        meta=BundleMeta(
            name=tokens.meta.name,
            version=tokens.meta.version,
            note=tokens.meta.note,
            created=tokens.meta.created,
        ),
        style_prompt=render_style_prompt(tokens),
        preview_html=_FALLBACK_PREVIEW_HTML,
        base_css=render_base_css(tokens),
        style_css=render_style_css(tokens),
        source=BundleSource(prompt=source_prompt, raw_response=""),
    )


def normalize_bundle_payload(
    data: dict[str, Any],
    previous: StyleBundle | None = None,
    source_prompt: str = "",
    raw_response: str = "",
    model: str = "",
    base_url: str = "",
    preserve_preview_html: bool = False,
    usage: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> StyleBundle:
    """把 LLM JSON 收敛到固定包结构；不改写 CSS/HTML/Prompt 内容。"""
    meta_data = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    prev_meta = previous.meta if previous else BundleMeta()
    meta = BundleMeta(
        name=_text(meta_data.get("name"), prev_meta.name) or "未命名风格",  # type:ignore
        version=_text(meta_data.get("version"), prev_meta.version) or "1.0", # type:ignore
        note=_text(meta_data.get("note"), prev_meta.note), # type:ignore
        created=prev_meta.created if previous else _now(),
    )

    semantic = data.get("semantic_diff", [])
    if not isinstance(semantic, list):
        semantic = []
    semantic_diff = [
        item for item in semantic
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]

    style_prompt = _text(data.get("style_prompt"), "")
    preview_html = _text(data.get("preview_html"), "")
    base_css = _text(data.get("base_css"), "")
    style_css = _text(data.get("style_css"), "")

    if previous:
        style_prompt = style_prompt or previous.style_prompt
        preview_html = previous.preview_html if preserve_preview_html else (preview_html or previous.preview_html)
        base_css = base_css or previous.base_css
        style_css = style_css or previous.style_css
    else:
        style_prompt = style_prompt or "请用自由 HTML/CSS 复刻当前风格，保留颜色、材质、边框、字体与动效。"
        preview_html = preview_html or _FALLBACK_PREVIEW_HTML

    return StyleBundle(
        meta=meta,
        reply=_text(data.get("reply"), ""),
        style_prompt=style_prompt,
        preview_html=preview_html,
        base_css=base_css,
        style_css=style_css,
        semantic_diff=semantic_diff,
        history=list(previous.history) if previous else [],
        source=BundleSource(
            prompt=source_prompt,
            model=model,
            base_url=base_url,
            parent_hash=bundle_hash(previous) if previous else "",
            raw_response=raw_response,
            usage=usage,
            duration_ms=duration_ms,
        ),
    )


def bundle_hash(bundle: StyleBundle | None) -> str:
    if bundle is None:
        return ""
    return _sha256(json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))


def render_combined_bundle_css(bundle: StyleBundle) -> str:
    return bundle.base_css + "\n\n" + bundle.style_css


def append_history(bundle: StyleBundle, role: str, text: str) -> None:
    bundle.history.append({
        "role": role,
        "text": text,
        "at": _now().isoformat(timespec="seconds"),
    })
    bundle.history = bundle.history[-100:]


def _short(value: Any) -> str:
    text = _text(value)
    return f"{len(text)} 字符" if text else "(空)"


def diff_bundles(before: StyleBundle, after: StyleBundle) -> list[dict[str, Any]]:
    """文件级 diff + LLM 语义 diff。不把整份 CSS 塞进 SSE。"""
    items: list[dict[str, Any]] = []
    for item in after.semantic_diff:
        items.append({
            "kind": _text(item.get("kind"), "semantic"),
            "path": str(item.get("path", "")),
            "from": _text(item.get("from")),
            "to": _text(item.get("to")),
            "reason": _text(item.get("reason"), "模型语义说明"),
        })

    file_specs = (
        ("base.css", before.base_css, after.base_css),
        ("style.css", before.style_css, after.style_css),
        ("preview.html", before.preview_html, after.preview_html),
        ("STYLE_PROMPT.md", before.style_prompt, after.style_prompt),
    )
    for path, old, new in file_specs:
        if old != new:
            items.append({
                "kind": "file",
                "path": path,
                "from": _short(old),
                "to": _short(new),
                "reason": "产物文件已更新",
            })
    return items


def build_manifest(bundle: StyleBundle) -> dict[str, Any]:
    files = {
        "STYLE_PROMPT.md": bundle.style_prompt,
        "preview.html": bundle.preview_html,
        "base.css": bundle.base_css,
        "style.css": bundle.style_css,
        "raw-llm.json": json.dumps({
            "raw": bundle.source.raw_response,
            "usage": bundle.source.usage,
            "duration_ms": bundle.source.duration_ms,
        }, ensure_ascii=False, indent=2),
        "source-conversation.json": json.dumps(bundle.history, ensure_ascii=False, indent=2),
    }
    return {
        "schemaVersion": "2.0",
        "generator": "UIDiy Free Artifact Bundle",
        "styleName": bundle.meta.name,
        "styleVersion": bundle.meta.version,
        "generatedAt": bundle.source.generated_at.isoformat(timespec="seconds"),
        "model": bundle.source.model,
        "baseUrl": bundle.source.base_url,
        "parentHash": bundle.source.parent_hash,
        "lastCall": {
            "model": bundle.source.model,
            "usage": bundle.source.usage,
            "durationMs": bundle.source.duration_ms,
        },
        "bundleHash": bundle_hash(bundle),
        "files": {
            name: {
                "sha256": _sha256(content),
                "bytes": len(content.encode("utf-8")),
            }
            for name, content in files.items()
        },
        "fileList": list(EXPORT_FILES),
    }


def build_changelog(bundle: StyleBundle) -> str:
    lines = [f"# {bundle.meta.name} · 变更记录", ""]
    if bundle.meta.note:
        lines += [bundle.meta.note, ""]
    if bundle.semantic_diff:
        lines.append("## 语义差异")
        for item in bundle.semantic_diff:
            lines.append(
                f"- {item.get('path', '(未命名维度)')}: "
                f"{_text(item.get('from'))} → {_text(item.get('to'))} · {_text(item.get('reason'))}"
            )
        lines.append("")
    lines.append("## 对话记录")
    for item in bundle.history:
        role = "用户" if item.get("role") == "user" else "助手"
        lines.append(f"- {role}: {_text(item.get('text')).replace(chr(10), ' ')}")
    return "\n".join(lines) + "\n"


def build_export_files(bundle: StyleBundle) -> dict[str, str]:
    """固定导出结构；每次导出文件列表完全一致。"""
    manifest = build_manifest(bundle)
    return {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
        "STYLE_PROMPT.md": bundle.style_prompt,
        "preview.html": bundle.preview_html,
        "base.css": bundle.base_css,
        "style.css": bundle.style_css,
        "raw-llm.json": json.dumps({
            "raw": bundle.source.raw_response,
            "usage": bundle.source.usage,
            "duration_ms": bundle.source.duration_ms,
        }, ensure_ascii=False, indent=2),
        "source-conversation.json": json.dumps(bundle.history, ensure_ascii=False, indent=2),
        "CHANGELOG.md": build_changelog(bundle),
    }


def extract_accent_hint(bundle: StyleBundle) -> str:
    text = bundle.base_css + "\n" + bundle.style_css
    match = re.search(r"#[0-9a-fA-F]{6}\b", text)
    return match.group(0) if match else ""
