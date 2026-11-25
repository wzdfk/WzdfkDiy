"""LLM 设置 API：读取（掩码）/ 保存 / 测试连接；本地目录选择。"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..core import llm

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger(__name__)

_PICK_DIR_SCRIPT = """
import sys
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
path = filedialog.askdirectory(title='选择输出目录')
root.destroy()
if path:
    sys.stdout.buffer.write(b'__PICKED_DIR__' + path.encode('utf-8'))
"""
_PICK_DIR_MARKER = b"__PICKED_DIR__"


class LlmRuntimeIn(BaseModel):
    """单次请求使用的 LLM 配置；不写盘，请求结束即丢弃。"""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    reasoning_effort: str = "auto"
    provider: str = ""


class LlmModelsIn(BaseModel):
    base_url: str = ""
    api_key: str = ""       # 空 = 使用请求级配置或环境变量


@router.get("/llm")
def get_llm_settings():
    """仅返回默认值；门户模式 key_masked 为空。"""
    return llm.get_settings()


@router.post("/llm/test")
def test_llm(payload: LlmRuntimeIn):
    logger.info("测试 LLM 连接 base_url=%r", payload.base_url)
    with llm.runtime_config(payload.model_dump()):
        return llm.test_connection()


@router.post("/llm/probe-reasoning")
def probe_reasoning(payload: LlmRuntimeIn):
    logger.info("探测思考强度 base_url=%r", payload.base_url)
    with llm.runtime_config(payload.model_dump()):
        return llm.probe_reasoning_options()


@router.post("/llm/models")
def list_llm_models(payload: LlmModelsIn):
    logger.info("拉取模型列表 base_url=%r", payload.base_url)
    return llm.list_models(payload.base_url, payload.api_key or None)


@router.post("/pick-dir")
def pick_directory():
    """打开本地原生目录选择框，返回绝对路径；取消时 selected=False。"""
    try:
        done = subprocess.run(
            [sys.executable, "-c", _PICK_DIR_SCRIPT],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "selected": False, "path": "", "error": str(exc)}

    output = done.stdout or b""
    index = output.find(_PICK_DIR_MARKER)
    if index < 0:
        return {"ok": False, "selected": False, "path": "", "error": "已取消或未选择目录"}

    raw = output[index + len(_PICK_DIR_MARKER):].decode("utf-8", errors="replace").strip()
    target = Path(raw).expanduser()
    if not raw or not target.is_dir():
        return {"ok": False, "selected": False, "path": "", "error": "目录不存在"}
    return {"ok": True, "selected": True, "path": str(target.resolve())}
