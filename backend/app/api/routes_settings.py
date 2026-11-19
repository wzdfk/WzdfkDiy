"""LLM 设置 API：读取（掩码）/ 保存 / 测试连接。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..core import llm

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LlmSettingsIn(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""       # 空 = 保留已存 key


@router.get("/llm")
def get_llm_settings():
    return llm.get_settings()


@router.put("/llm")
def put_llm_settings(payload: LlmSettingsIn):
    return llm.save_settings(payload.base_url, payload.model, payload.api_key or None)


@router.post("/llm/test")
def test_llm():
    return llm.test_connection()
