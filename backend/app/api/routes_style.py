"""UIDiy API 路由：风格解析 / 对话 / 导出 / 预览 CSS。"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from ..core import db as archive_db
from ..core import llm
from ..core.bundle import (
    StyleBundle,
    append_history,
    bundle_from_legacy_tokens,
    build_export_files,
    render_combined_bundle_css,
)
from ..core.tokens import blank_default, fold_default

router = APIRouter(prefix="/api/style", tags=["style"])
logger = logging.getLogger(__name__)


def _brief(text: str, limit: int = 60) -> str:
    value = (text or "").replace("\n", " ").strip()
    return value if len(value) <= limit else value[:limit] + "…"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# ---------- 会话内风格产物包（V2 自由产物） ----------
_session: dict[str, StyleBundle] = {
    "default": bundle_from_legacy_tokens(fold_default(), "系统默认基线")
}

# 撤销快照栈：每次改动前压一份，最多保留 50 步
_undo_stack: list[StyleBundle] = []
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
def set_current_style(bundle: StyleBundle):
    logger.debug("覆盖产物包 -> %s", bundle.meta.name)
    _push_snapshot()
    append_history(bundle, "assistant", "外部写入完整产物包。")
    _session["default"] = bundle
    return {"ok": True}


@router.post("/parse")
def parse_style(payload: dict):
    """提示词 → 完整自由产物包。"""
    text = payload.get("prompt", "")
    logger.info("定义风格 prompt=%r", _brief(text))
    _push_snapshot()
    baseline = _session["default"].model_copy(deep=True)
    bundle = llm.parse_prompt_bundle(text, baseline=baseline)
    _session["default"] = bundle
    return bundle


@router.post("/chat")
def chat(payload: dict):
    """多轮对话优化：{message, history?} → 完整产物包 + diff + 回复。"""
    message = payload.get("message", "")
    history = payload.get("history") or []
    mode = payload.get("mode") or llm._decide_mode(message, {})
    mode = "rewrite" if mode == "rewrite" else "adjust"
    logger.info("对话调整 mode=%s message=%r", mode, _brief(message))
    current = _session["default"].model_copy(deep=True)
    _push_snapshot()
    bundle, diff, reply = llm.chat_bundle(current, message, history=history, mode=mode)
    logger.info("对话完成 diff=%d 项", len(diff))
    _session["default"] = bundle
    return {"bundle": bundle, "diff": diff, "reply": reply}


@router.post("/chat/stream")
async def chat_stream(payload: dict):
    """流式对话：SSE 输出系统思考/模型输出/产物包写入。"""
    message = payload.get("message", "")
    history = payload.get("history") or []
    mode = payload.get("mode") or llm._decide_mode(message, {})
    mode = "rewrite" if mode == "rewrite" else "adjust"
    logger.info("流式对话 mode=%s message=%r", mode, _brief(message))
    current = _session["default"].model_copy(deep=True)

    async def generate():
        final = None
        try:
            async for event in llm.chat_bundle_stream(current, message, history=history, mode=mode):
                if event.get("type") == "done":
                    final = event
                yield _sse(event.get("type", "message"), event)
            if final:
                _push_snapshot()
                _session["default"] = StyleBundle.model_validate(final["bundle"])
                logger.info("流式对话完成 diff=%d 项", len(final.get("diff", [])))
        except asyncio.CancelledError:
            logger.info("流式对话被客户端终止，未写入半成品产物")
            raise
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
    """撤销最近一次改动，恢复完整产物包。"""
    if not _undo_stack:
        return {"ok": False, "error": "没有可撤销的改动", "bundle": _session["default"]}
    _session["default"] = _undo_stack.pop()
    logger.info("撤销一次，剩余 %d 步", len(_undo_stack))
    return {"ok": True, "bundle": _session["default"]}


@router.post("/reset")
def reset_style():
    logger.info("重置为系统默认产物包")
    _push_snapshot()
    _session["default"] = bundle_from_legacy_tokens(fold_default(), "系统默认基线")
    return _session["default"]


@router.post("/blank")
def use_blank_template():
    """切换到零装饰产物包基线。"""
    logger.info("切换到空模板产物包")
    _push_snapshot()
    _session["default"] = bundle_from_legacy_tokens(blank_default(), "空模板基线")
    return _session["default"]


@router.get("/preview-css")
def preview_css():
    """预览 iframe 拉取当前产物包的 CSS 与 HTML。"""
    bundle = _session["default"]
    return {
        "css": render_combined_bundle_css(bundle),
        "preview_html": bundle.preview_html,
    }


def _build_export_zip() -> tuple[io.BytesIO, str, str]:
    """打包当前风格，返回（zip 字节流, 文件名, 时间戳）。"""
    bundle = _session["default"]
    logger.info("导出风格包 name=%r", bundle.meta.name)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_name = "".join(c for c in bundle.meta.name if c.isalnum() or c in "·-") or "style"
    file_name = f"{safe_name}-{stamp}.zip"

    files = build_export_files(bundle)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf, file_name, stamp


@router.post("/export")
def export_style(payload: dict | None = None):
    """导出固定结构 zip：manifest + Prompt + preview + CSS + 溯源文件。"""
    buf, file_name, stamp = _build_export_zip()
    ascii_name = f"uidiy-style-{stamp}.zip"   # 兼容 latin-1 头
    utf8_name = quote(file_name)               # RFC 5987

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
        },
    )


@router.post("/export/save")
def export_style_to_dir(payload: dict):
    """把产物包写入本地指定目录，返回实际文件路径。"""
    raw_dir = str(payload.get("output_dir") or "").strip()
    if not raw_dir:
        return JSONResponse(status_code=400, content={"ok": False, "error": "输出路径不能为空"})
    target = Path(raw_dir).expanduser()
    if not target.is_absolute():
        return JSONResponse(status_code=400, content={"ok": False, "error": "输出路径需为绝对路径"})
    try:
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            raise NotADirectoryError(target)
        buf, file_name, _ = _build_export_zip()
        dest = target / file_name
        with dest.open("wb") as f:
            shutil.copyfileobj(buf, f)
    except OSError as exc:
        logger.warning("写出产物包失败 dir=%r err=%s", raw_dir, exc)
        return JSONResponse(status_code=400, content={"ok": False, "error": f"写入失败：{exc}"})

    return {"ok": True, "path": str(dest.resolve()), "file_name": file_name}


# ---------- 风格档案持久化（MySQL，M4） ----------


@router.post("/archives")
def save_archive(payload: dict):
    """当前档案存入 MySQL：{name} → 同名覆盖。"""
    name = (payload.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "档案名不能为空"}
    try:
        bundle = _session["default"].model_copy(deep=True)
        bundle.meta.name = name
        append_history(bundle, "assistant", f"存档为「{name}」。")
        archive_id = archive_db.save_archive(name, bundle)
        _session["default"] = bundle
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
        bundle, archive_name = archive_db.load_archive(archive_id)
        bundle.meta.name = archive_name
        append_history(bundle, "assistant", f"加载档案「{archive_name}」。")
        _session["default"] = bundle
        logger.info("加载档案 id=%s name=%r", archive_id, archive_name)
        return {"ok": True, "bundle": bundle}
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
