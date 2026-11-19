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
    reasoning_effort: str = "auto"
    provider: str = ""


@router.get("/llm")
def get_llm_settings():
    return llm.get_settings()


@router.put("/llm")
def put_llm_settings(payload: LlmSettingsIn):
    logger.info(
        "保存 LLM 设置 provider=%r base_url=%r model=%r reasoning_effort=%r",
        payload.provider, payload.base_url, payload.model, payload.reasoning_effort,
    )
    return llm.save_settings(
        payload.base_url,
        payload.model,
        payload.api_key or None,
        payload.reasoning_effort,
        payload.provider,
    )


@router.post("/llm/test")
def test_llm():
    logger.info("测试 LLM 连接")
    return llm.test_connection()


@router.post("/llm/probe-reasoning")
def probe_reasoning():
    logger.info("探测当前模型思考强度支持项")
    return llm.probe_reasoning_options()
