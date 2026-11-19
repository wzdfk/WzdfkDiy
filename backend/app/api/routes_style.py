"""UIDiy API 路由：风格解析 / 对话 / 导出 / 预览 CSS。"""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..core import db as archive_db
from ..core import llm
from ..core.css_gen import render_base_css, render_combined_css, render_style_css
from ..core.tokens import StyleTokens, blank_default, fold_default

router = APIRouter(prefix="/api/style", tags=["style"])
logger = logging.getLogger(__name__)


def _brief(text: str, limit: int = 60) -> str:
    value = (text or "").replace("\n", " ").strip()
    return value if len(value) <= limit else value[:limit] + "…"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# ---------- 会话内风格档案（V0 内存态；持久化到 MySQL 在 M4） ----------
_session: dict[str, StyleTokens] = {"default": fold_default()}

# 撤销快照栈：每次改动前压一份，最多保留 50 步
_undo_stack: list[StyleTokens] = []
_UNDO_MAX = 50


def _push_snapshot() -> None:
    _undo_stack.append(_session["default"].model_copy(deep=True))
    del _undo_stack[:-_UNDO_MAX]


def _db_error(e: Exception) -> dict:
    return {"ok": False, "error": str(e)}


@router.get("/current")
def get_current_style():
    return _session["default"]


@router.post("/current")
def set_current_style(tokens: StyleTokens):
    logger.debug("面板调参 -> %s", tokens.meta.name)
    _push_snapshot()
    _session["default"] = tokens
    return {"ok": True}


@router.post("/parse")
def parse_style(payload: dict):
    """提示词 → 初始风格档案。"""
    text = payload.get("prompt", "")
    logger.info("定义风格 prompt=%r", _brief(text))
    _push_snapshot()
    tokens = llm.parse_prompt(text)
    _session["default"] = tokens
    return tokens


@router.post("/chat")
def chat(payload: dict):
    """多轮对话优化：{message, history?} → 新档案 + diff + 回复。"""
    message = payload.get("message", "")
    history = payload.get("history") or []
    logger.info("对话调整 message=%r", _brief(message))
    current = _session["default"]
    _push_snapshot()
    tokens, diff, reply = llm.chat_diff(current, message, history=history)
    logger.info("对话完成 diff=%d 项", len(diff))
    _session["default"] = tokens
    return {"tokens": tokens, "diff": diff, "reply": reply}


@router.post("/chat/stream")
async def chat_stream(payload: dict):
    """流式对话：SSE 输出系统思考/模型输出/整理校验/最终方案。"""
    message = payload.get("message", "")
    history = payload.get("history") or []
    logger.info("流式对话 message=%r", _brief(message))
    current = _session["default"]

    async def generate():
        final = None
        try:
            async for event in llm.chat_diff_stream(current, message, history=history):
                if event.get("type") == "done":
                    final = event
                yield _sse(event.get("type", "message"), event)
            if final:
                _push_snapshot()
                _session["default"] = StyleTokens.model_validate(final["tokens"])
                logger.info("流式对话完成 diff=%d 项", len(final.get("diff", [])))
        except Exception as e:
            logger.exception("流式对话失败")
            yield _sse("error", {"type": "error", "message": f"{e.__class__.__name__}: {e}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/undo")
def undo_style():
    """撤销最近一次改动（parse/chat/current/面板 patch 均入栈）。"""
    if not _undo_stack:
        return {"ok": False, "error": "没有可撤销的改动", "tokens": _session["default"]}
    _session["default"] = _undo_stack.pop()
    logger.info("撤销一次，剩余 %d 步", len(_undo_stack))
    return {"ok": True, "tokens": _session["default"]}


@router.post("/reset")
def reset_style():
    logger.info("重置为系统默认风格")
    _push_snapshot()
    _session["default"] = fold_default()
    return _session["default"]


@router.post("/blank")
def use_blank_template():
    """切换到零装饰空模板，供用户从朴素基线打造个人风格。"""
    logger.info("切换到空模板")
    _push_snapshot()
    _session["default"] = blank_default()
    return _session["default"]


@router.get("/preview-css")
def preview_css():
    """预览 iframe 拉取的真实 CSS（所见即所导）。"""
    css = render_combined_css(_session["default"])
    return {"css": css}


@router.post("/export")
def export_style(payload: dict | None = None):
    """导出三件套 zip：style.json + base.css + style.css + STYLE_PROMPT.md。"""
    tokens = _session["default"]
    logger.info("导出风格包 name=%r", tokens.meta.name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(c for c in tokens.meta.name if c.isalnum() or c in "·-") or "style"
    from urllib.parse import quote
    ascii_name = f"uidiy-style-{stamp}.zip"                       # 兼容 latin-1 头
    utf8_name = quote(f"{safe_name}-{stamp}.zip")                 # RFC 5987

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("style.json", tokens.model_dump_json(indent=2))
        zf.writestr("base.css", render_base_css(tokens))
        zf.writestr("style.css", render_style_css(tokens))
        zf.writestr("STYLE_PROMPT.md", llm.reverse_prompt(tokens))
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
        },
    )


# ---------- 风格档案持久化（MySQL，M4） ----------


@router.post("/archives")
def save_archive(payload: dict):
    """当前档案存入 MySQL：{name} → 同名覆盖。"""
    name = (payload.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "档案名不能为空"}
    try:
        archive_id = archive_db.save_archive(name, _session["default"])
        logger.info("存档 name=%r id=%s", name, archive_id)
        return {"ok": True, "id": archive_id, "name": name}
    except Exception as e:
        return _db_error(e)


@router.get("/archives")
def list_archives():
    """档案列表：id / 名称 / 主色 / 更新时间。"""
    try:
        return {"ok": True, "items": archive_db.list_archives()}
    except Exception as e:
        return _db_error(e)


@router.post("/archives/{archive_id}/load")
def load_archive(archive_id: int):
    """加载档案为当前风格。"""
    try:
        _push_snapshot()
        tokens, archive_name = archive_db.load_archive(archive_id)
        tokens.meta.name = archive_name
        _session["default"] = tokens
        logger.info("加载档案 id=%s name=%r", archive_id, archive_name)
        return {"ok": True, "tokens": tokens}
    except KeyError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return _db_error(e)


@router.delete("/archives/{archive_id}")
def delete_archive(archive_id: int):
    try:
        archive_db.delete_archive(archive_id)
        logger.info("删除档案 id=%s", archive_id)
        return {"ok": True}
    except KeyError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return _db_error(e)
