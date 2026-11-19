"""LLM 设置 API：读取（掩码）/ 保存 / 测试连接。"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from ..core import llm

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger(__name__)


class LlmSettingsIn(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""       # 空 = 保留已存 key


@router.get("/llm")
def get_llm_settings():
    return llm.get_settings()


@router.put("/llm")
def put_llm_settings(payload: LlmSettingsIn):
    logger.info("保存 LLM 设置 base_url=%r model=%r", payload.base_url, payload.model)
    return llm.save_settings(payload.base_url, payload.model, payload.api_key or None)


@router.post("/llm/test")
def test_llm():
    logger.info("测试 LLM 连接")
    return llm.test_connection()
