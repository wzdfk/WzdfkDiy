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
    .uidiy-menu-static { display:flex; flex-direction:column; gap:4px; min-width:220px; }
  </style>
  <header>
    <span class="fd-label">STYLE PREVIEW · 实时预览</span>
    <h1 class="fd-display">风格预览</h1>
    <p class="uidiy-muted">五组件展示：Button 定调 · Card 定骨架 · Input 定质感 · Toast 定气质 · Dropdown 定延展。</p>
  </header>

  <section>
    <span class="fd-label">BUTTON · 按钮（交互签名）</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <button class="fd-btn fd-btn-primary">主要操作</button>
      <button class="fd-btn">次要操作</button>
      <button class="fd-btn fd-btn-ghost">幽灵按钮</button>
      <button class="fd-btn fd-btn-danger">危险操作</button>
      <button class="fd-btn" disabled>禁用状态</button>
    </div>
  </section>

  <section>
    <span class="fd-label">CARD · 卡片（骨架与层次）</span>
    <div class="uidiy-grid">
      <div class="fd-card"><h3 class="fd-title">站点概览</h3><p class="uidiy-muted">设备接入数量与整体运行状态。</p><div class="meta"><span>更新于 12 分钟前</span><span class="fd-badge fd-badge-ok">✓ 运行中</span></div></div>
      <div class="fd-card"><h3 class="fd-title">今日告警</h3><p class="uidiy-muted">共 3 条未处理告警。</p><div class="meta"><span>更新于 3 分钟前</span><span class="fd-badge fd-badge-warn">! 待处理</span></div></div>
      <div class="fd-card"><h3 class="fd-title">同步任务</h3><p class="uidiy-muted">夜间批量同步已完成 87%。</p><div class="meta"><span>更新于 1 分钟前</span><span class="fd-badge fd-badge-info">● 进行中</span></div></div>
    </div>
  </section>

  <section>
    <span class="fd-label">INPUT · 输入框（质感与焦点）</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <input class="fd-input" placeholder="点进来看 focus" style="min-width:260px;">
      <input class="fd-input" value="90000" style="min-width:160px;">
      <span class="uidiy-muted">Tab 键切换，感受焦点环样式</span>
    </div>
  </section>

  <section>
    <span class="fd-label">TOAST · 轻通知（气质与状态）</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <span class="fd-toast fd-toast-ok">配置已保存</span>
      <span class="fd-toast fd-toast-warn">信号波动</span>
      <span class="fd-toast fd-toast-danger">设备离线</span>
      <span class="fd-toast fd-toast-info">任务进行中</span>
    </div>
  </section>

  <section>
    <span class="fd-label">DROPDOWN · 下拉（浮层与延展）</span>
    <div class="fd-card uidiy-row" style="padding:24px;">
      <button class="fd-btn fd-btn-primary">选择主题色 ▾</button>
      <div class="fd-menu uidiy-menu-static">
        <div class="fd-opt fd-opt-selected">✓ 当前主题</div>
        <div class="fd-opt">备选主题 A</div>
        <div class="fd-opt">备选主题 B</div>
      </div>
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
        name=_text(meta_data.get("name"), prev_meta.name) or "未命名风格",
        version=_text(meta_data.get("version"), prev_meta.version) or "1.0",
        note=_text(meta_data.get("note"), prev_meta.note),
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
