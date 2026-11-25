"""LLM adapter · V1 真实现（OpenAI 兼容接口：智谱 GLM / DeepSeek / OpenAI 等）。

接口约定（对外 API 与 V0 一致）：
- parse_prompt(text) -> StyleTokens                       首次定义风格
- chat_diff(tokens, message, history) -> (tokens', diff, reply)   多轮优化

配置优先级：界面设置（app/data/llm_settings.json）> .env（BASE_URL/API_KEY）> 默认值。
LLM 不可用/输出不合法时自动兜底回风格词典（dict_style），服务永不因 LLM 挂掉而挂。
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

import httpx

from . import dict_style
from .bundle import (
    StyleBundle,
    append_history,
    bundle_from_legacy_tokens,
    diff_bundles,
    normalize_bundle_payload,
)
from .tokens import ControlBox, StyleTokens, blank_default, fold_default

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
_DEFAULT_MODEL = "glm-4-flash"
_TIMEOUT = 60.0
_ARTIFACT_TIMEOUT = 300.0
_REASONING_EFFORTS = {"auto", "none", "low", "medium", "high", "max"}
_PROVIDERS = {"zhipu", "deepseek", "openai", "moonshot", "qwen", "custom"}


def _normalize_reasoning_effort(value: Any) -> str:
    text = str(value or "auto").strip().lower()
    return text if text in _REASONING_EFFORTS else "auto"


def _normalize_provider(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in _PROVIDERS else ""

# ---------- 请求级运行时配置（不落盘，用完即弃） ----------

_RUNTIME_CONFIG: ContextVar[dict[str, Any] | None] = ContextVar(
    "uidiy_llm_runtime", default=None,
)


@contextmanager
def runtime_config(cfg: dict[str, Any] | None):
    """在单个请求内临时注入 LLM 配置，退出后自动清理。"""
    token = _RUNTIME_CONFIG.set(cfg or None)
    try:
        yield
    finally:
        _RUNTIME_CONFIG.reset(token)


def _runtime() -> dict[str, Any]:
    return _RUNTIME_CONFIG.get() or {}


def get_settings() -> dict[str, Any]:
    """设置面板默认值；密钥只来自服务端环境变量，门户模式为空。"""
    key = os.getenv("API_KEY", "")
    masked = (key[:6] + "****" + key[-4:]) if len(key) > 10 else ("已配置" if key else "")
    base = os.getenv("BASE_URL") or _DEFAULT_BASE_URL
    model = os.getenv("MODEL") or _DEFAULT_MODEL
    return {
        "provider": _normalize_provider(os.getenv("LLM_PROVIDER", "")) or _provider_key(base, model),
        "base_url": base,
        "model": model,
        "reasoning_effort": _normalize_reasoning_effort(os.getenv("REASONING_EFFORT", "auto")),
        "key_masked": masked,
        "has_key": bool(key),
        "enabled": bool(key),
    }


def _models_endpoint(base: str) -> str:
    """从 chat/completions 地址推导 OpenAI 兼容 /models 地址。"""
    url = (base or "").strip().rstrip("/")
    if not url:
        return ""
    lower = url.lower()
    for suffix in ("/chat/completions", "/completions"):
        if lower.endswith(suffix):
            return url[: -len(suffix)] + "/models"
    if lower.endswith("/models"):
        return url
    return f"{url}/models"


def list_models(base_url: str | None = None, api_key: str | None = None) -> dict[str, Any]:
    """拉取供应商可用模型列表；仅返回 id，不保存 Key。"""
    runtime = _runtime()
    base = str(base_url or runtime.get("base_url") or os.getenv("BASE_URL") or _DEFAULT_BASE_URL).strip()
    key = str(api_key or runtime.get("api_key") or os.getenv("API_KEY") or "").strip()
    endpoint = _models_endpoint(base)
    if not key:
        return {"ok": False, "models": [], "url": endpoint, "error": "未配置 API Key"}
    try:
        r = httpx.get(endpoint, headers={"Authorization": f"Bearer {key}"}, timeout=20.0)
        r.raise_for_status()
        payload = r.json()
        rows = payload.get("data") if isinstance(payload, dict) else payload
        models: list[str] = []
        if isinstance(rows, list):
            for item in rows:
                model_id = item.get("id") if isinstance(item, dict) else item
                if isinstance(model_id, str) and model_id.strip():
                    models.append(model_id.strip())
        return {"ok": True, "models": sorted(set(models))[:200], "url": endpoint}
    except Exception as e:
        return {"ok": False, "models": [], "url": endpoint, "error": f"{e.__class__.__name__}: {e}"[:300]}


# ---------- 凭据与底层调用 ----------


def _creds() -> tuple[str, str, str]:
    runtime = _runtime()
    base = str(runtime.get("base_url") or os.getenv("BASE_URL") or _DEFAULT_BASE_URL).strip()
    key = str(runtime.get("api_key") or os.getenv("API_KEY") or "").strip()
    model = str(runtime.get("model") or os.getenv("MODEL") or _DEFAULT_MODEL).strip()
    return base, key, model


def enabled() -> bool:
    return bool(_creds()[1])


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _provider_name(base: str, model: str) -> str:
    text = f"{base} {model}".lower()
    if "bigmodel" in text or "zhipu" in text or "glm" in text:
        return "智谱 GLM"
    if "deepseek" in text:
        return "DeepSeek"
    if "anthropic" in text or "claude" in text:
        return "Anthropic"
    if "generativelanguage" in text or "gemini" in text:
        return "Google Gemini"
    if "moonshot" in text or "kimi" in text:
        return "Moonshot"
    if "dashscope" in text or "qwen" in text or "tongyi" in text:
        return "通义千问"
    if "openai" in text:
        return "OpenAI"
    return "OpenAI 兼容接口"


def _provider_key(base: str, model: str) -> str:
    text = f"{base} {model}".lower()
    if "bigmodel" in text or "zhipu" in text or "glm" in text:
        return "zhipu"
    if "deepseek" in text:
        return "deepseek"
    if "anthropic" in text or "claude" in text:
        return "anthropic"
    if "generativelanguage" in text or "gemini" in text:
        return "gemini"
    return "openai"


def _current_provider_key(base: str, model: str) -> str:
    stored = _normalize_provider(_runtime().get("provider") or os.getenv("LLM_PROVIDER", ""))
    return stored or _provider_key(base, model)


def _usage_stream_options(base: str, model: str) -> list[dict[str, bool]]:
    """不同供应商流式 usage 开关不同：智谱用 chunk_include_usage，OpenAI/DeepSeek 用 include_usage。"""
    key = _current_provider_key(base, model)
    if key == "zhipu":
        return [{"chunk_include_usage": True}, {"include_usage": True}, {}]
    if key == "deepseek":
        return [{"include_usage": True}, {"chunk_include_usage": True}, {}]
    return [{"include_usage": True}, {"chunk_include_usage": True}, {}]


def _reasoning_payload(base: str, model: str, effort: str) -> dict[str, Any]:
    """统一思考强度 → 各供应商请求参数。auto 表示不下发，跟随模型默认。"""
    effort = _normalize_reasoning_effort(effort)
    if effort == "auto":
        return {}
    key = _current_provider_key(base, model)
    if key in ("zhipu", "deepseek"):
        return {"reasoning_effort": effort}
    if key == "openai":
        mapped = {"none": "minimal", "low": "low", "medium": "medium", "high": "high", "max": "xhigh"}
        return {"reasoning": {"effort": mapped.get(effort, "medium")}}
    if key == "anthropic":
        budget = {"none": 0, "low": 1024, "medium": 2048, "high": 4096, "max": 8192}
        if effort == "none":
            return {}
        return {"thinking": {"type": "enabled", "budget_tokens": budget.get(effort, 2048)}}
    if key == "gemini":
        mapped = {"none": "low", "low": "low", "medium": "medium", "high": "high", "max": "high"}
        return {"thinking_level": mapped.get(effort, "medium")}
    return {"reasoning_effort": effort}


def _current_reasoning_payload(base: str, model: str) -> dict[str, Any]:
    effort = _normalize_reasoning_effort(
        _runtime().get("reasoning_effort") or os.getenv("REASONING_EFFORT", "auto")
    )
    return _reasoning_payload(base, model, effort)


def normalize_usage(usage: Any, model: str = "", base: str = "") -> dict[str, Any]:
    """把不同供应商的 usage 归一到统一结构。"""
    available = isinstance(usage, dict) and bool(usage)
    usage = usage if available else {}
    if isinstance(usage.get("usageMetadata"), dict):
        usage = usage["usageMetadata"]
        available = bool(usage)
    prompt_details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    completion_details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}

    prompt_tokens = _as_int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("promptTokenCount")
    )
    completion_tokens = _as_int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("candidatesTokenCount")
    )
    total_tokens = _as_int(
        usage.get("total_tokens")
        or usage.get("totalTokenCount")
        or (prompt_tokens + completion_tokens if available else 0)
    )
    cached_tokens = _as_int(
        prompt_details.get("cached_tokens")
        or prompt_details.get("cache_read_input_tokens")
        or usage.get("prompt_cache_hit_tokens")
        or usage.get("cache_read_input_tokens")
        or usage.get("cached_tokens")
        or usage.get("cachedContentTokenCount")
    )
    cache_miss_tokens = _as_int(
        usage.get("prompt_cache_miss_tokens")
        or (prompt_tokens - cached_tokens if available and prompt_tokens >= cached_tokens else 0)
    )
    cache_write_tokens = _as_int(
        prompt_details.get("cache_creation_input_tokens")
        or prompt_details.get("cache_write_tokens")
        or usage.get("cache_creation_input_tokens")
        or usage.get("cache_write_tokens")
    )
    reasoning_tokens = _as_int(
        completion_details.get("reasoning_tokens")
        or usage.get("reasoning_tokens")
        or usage.get("thoughtsTokenCount")
    )

    return {
        "available": available,
        "provider": _provider_name(base, model),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "cache_miss_tokens": cache_miss_tokens,
        "cache_write_tokens": cache_write_tokens,
        "reasoning_tokens": reasoning_tokens,
        "raw": usage if available else None,
    }


def raw_chat_with_usage(
    system: str,
    user: str,
    history: list[dict] | None = None,
    timeout: float | None = None,
) -> tuple[str, dict[str, Any], int]:
    """OpenAI 兼容非流式调用，返回 (文本, usage, 耗时ms)。失败抛异常。"""
    started = time.perf_counter()
    base, key, model = _creds()
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in (history or []):
        if m.get("role") in ("user", "bot") and m.get("text"):
            messages.append({"role": "user" if m["role"] == "user" else "assistant",
                             "content": m["text"]})
    messages.append({"role": "user", "content": user})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
    }
    payload.update(_current_reasoning_payload(base, model))
    r = httpx.post(
        base,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout or _TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    usage = normalize_usage(data.get("usage") or data.get("usageMetadata"), model, base)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return text, usage, duration_ms


def raw_chat(
    system: str,
    user: str,
    history: list[dict] | None = None,
    timeout: float | None = None,
) -> str:
    """兼容旧调用：只返回 assistant 文本。"""
    text, _usage, _duration_ms = raw_chat_with_usage(system, user, history, timeout)
    return text


async def _raw_chat_stream_once(
    system: str,
    user: str,
    history: list[dict] | None,
    timeout: float | None,
    stream_options: dict[str, bool] | None,
):
    base, key, model = _creds()
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in (history or []):
        if m.get("role") in ("user", "bot") and m.get("text"):
            messages.append({"role": "user" if m["role"] == "user" else "assistant",
                             "content": m["text"]})
    messages.append({"role": "user", "content": user})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "stream": True,
    }
    payload.update(_current_reasoning_payload(base, model))
    if stream_options:
        payload["stream_options"] = stream_options

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    usage: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=timeout or _TIMEOUT) as client:
        async with client.stream("POST", base, headers=headers, json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except Exception:
                    continue

                obj_usage = obj.get("usage") or obj.get("usageMetadata")
                if obj_usage:
                    usage = normalize_usage(obj_usage, model, base)

                try:
                    delta = obj["choices"][0]["delta"]
                except Exception:
                    continue
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                content = delta.get("content")
                if reasoning:
                    yield "reasoning", reasoning
                if content:
                    yield "content", content

    if usage is not None:
        yield "usage", usage


async def raw_chat_stream(
    system: str,
    user: str,
    history: list[dict] | None = None,
    timeout: float | None = None,
):
    """OpenAI 兼容流式调用； yields ('reasoning'|'content'|'usage', text/dict)。

    智谱使用 chunk_include_usage；OpenAI/DeepSeek 使用 include_usage。
    若候选参数不被支持导致 400，自动尝试下一组，最后降级为普通流式。
    """
    base, key, model = _creds()
    if not key:
        raise RuntimeError("未配置 API Key")

    last_error: Exception | None = None
    for options in _usage_stream_options(base, model):
        try:
            async for item in _raw_chat_stream_once(system, user, history, timeout, options or None):
                yield item
            return
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 400:
                raise
            last_error = e
            logger.warning("流式 usage 参数 %s 不被接受，尝试下一组", options)
            continue
    if last_error:
        raise last_error


_REVERSE_SYSTEM = """你是 UI 风格复原提示词生成器。读取 StyleTokens JSON，输出一段中文提示词，让另一个设计助手据此重建同款风格。
只输出提示词正文，不要 JSON、不要代码围栏、不要解释。
必须覆盖：色彩（主色/底色/面板/文字）、圆角、边框与焦点、投影、字体、动效、组件密度。
不要提折角，除非 tokens 的 shape.strategy 明确是 fold。"""


def reverse_prompt(tokens: StyleTokens) -> str:
    """tokens → 可复刻提示词；LLM 不可用时退回本地模板。"""
    from .prompt_gen import render_style_prompt

    if not enabled():
        return render_style_prompt(tokens)
    try:
        text = raw_chat(_REVERSE_SYSTEM, tokens.model_dump_json(indent=2)).strip()
        return text or render_style_prompt(tokens)
    except Exception:
        return render_style_prompt(tokens)


def test_connection() -> dict[str, Any]:
    """设置面板「测试连接」。"""
    t0 = time.time()
    try:
        text = raw_chat("你是连通性测试器。", "回复两个字：通了")
        return {"ok": True, "latency_ms": int((time.time() - t0) * 1000), "sample": text[:20]}
    except Exception as e:
        return {"ok": False, "error": f"{e.__class__.__name__}: {e}"[:300]}


def probe_reasoning_options() -> dict[str, Any]:
    """用当前 Key 实测各思考强度档位，返回可渲染选项。"""
    base, key, model = _creds()
    if not key:
        return {"ok": False, "error": "未配置 API Key", "options": []}

    labels = {
        "auto": "不指定（跟随模型默认）",
        "none": "关闭思考 / 最快",
        "low": "低强度 / 快",
        "medium": "中强度",
        "high": "高强度",
        "max": "最大强度 / 最慢",
    }
    options: list[dict[str, Any]] = [{
        "value": "auto", "label": labels["auto"], "accepted": True, "latency_ms": 0,
    }]

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for effort in ["none", "low", "medium", "high", "max"]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "只回复 ok"}],
            "temperature": 0,
            "max_tokens": 8,
        }
        payload.update(_reasoning_payload(base, model, effort))
        started = time.perf_counter()
        try:
            r = httpx.post(base, headers=headers, json=payload, timeout=20.0)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            error = body.get("error") if isinstance(body, dict) else None
            accepted = 200 <= r.status_code < 300 and not error
            options.append({
                "value": effort,
                "label": labels[effort],
                "accepted": accepted,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": "" if accepted else _probe_error_text(r.status_code, error),
            })
        except Exception as e:
            options.append({
                "value": effort,
                "label": labels[effort],
                "accepted": False,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": f"{e.__class__.__name__}: {e}"[:180],
            })

    return {"ok": True, "model": model, "options": options}


def _probe_error_text(status: int, error: Any) -> str:
    if isinstance(error, dict):
        message = error.get("message") or error.get("msg") or str(error)
    else:
        message = str(error or "")
    return f"HTTP {status}: {message}"[:180]


# ---------- JSON 提取与路径校验 ----------


def _extract_json(text: str) -> Any:
    """从回复中抠 JSON（容忍 ```json 围栏与前后废话）。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("回复中没有 JSON")
    # 从尾往前找配对括号
    for end in range(len(text), start, -1):
        try:
            return json.loads(text[start:end])
        except Exception:
            continue
    raise ValueError("JSON 解析失败")


_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_ENUMS: dict[str, set[str]] = {
    "shape.strategy": {"fold", "uniform", "asymmetric"},
    "line.border_style": {"solid", "dashed"},
    "line.focus_style": {"dashed", "solid", "glow"},
    "elevation.type": {"offset-solid", "soft-blur", "layered"},
    "motion.hover": {"lift", "press", "tilt", "none"},
    "motion.active": {"press", "none"},
}
_NUMBERS = {
    "line.border_width", "motion.duration", "motion.duration_slow", "spacing.unit",
}
_EASINGS = {"motion.easing_pop", "motion.easing_out"}
_ELEVATION_LEVELS = {"elevation.levels.e1", "elevation.levels.e2", "elevation.levels.e3"}
_CSS_SAFE_RE = re.compile(r"^[^{};]+$")
_EASING_RE = re.compile(
    r"^(?:linear|ease(?:-in|-out|-in-out)?"
    r"|cubic-bezier\(\s*-?\d*\.?\d+\s*,\s*-?\d*\.?\d+\s*,\s*-?\d*\.?\d+\s*,\s*-?\d*\.?\d+\s*\)"
    r"|steps\(\s*\d+\s*,\s*(?:start|end)\s*\))$",
    re.IGNORECASE,
)
_RADIUS_KEYS = {"lg", "md", "sm"}
_BOX_FIELDS = set(ControlBox.model_fields.keys())
_COMPONENTS = {"button", "card", "input", "badge", "toast", "menu"}


def _valid_change(path: str, value: Any) -> bool:
    """路径白名单 + 值域校验。不合法的修改直接丢弃。"""
    segs = path.split(".")
    if path in _ENUMS:
        return value in _ENUMS[path]
    if path in _NUMBERS:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if path in _EASINGS:
        return isinstance(value, str) and bool(_EASING_RE.fullmatch(value.strip()))
    if path in ("color.paper", "color.surface", "color.shadow", "elevation.shadow_color"):
        return isinstance(value, str) and (_HEX.match(value) is not None or value is None)
    if path in _ELEVATION_LEVELS:
        return isinstance(value, str) and bool(_CSS_SAFE_RE.fullmatch(value.strip())) and bool(value.strip())
    if path == "spacing.steps":
        return (
            isinstance(value, list) and len(value) >= 2
            and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)
        )
    if path.startswith("color.accent.s") and path.split(".")[-1] in {f"s{i}" for i in (50, 100, 200, 300, 400, 500, 600, 700)}:
        return isinstance(value, str) and _HEX.match(value) is not None
    if path.startswith("color.ink."):
        return isinstance(value, str) and _HEX.match(value) is not None
    if path.startswith("color.status."):
        return isinstance(value, str) and _HEX.match(value) is not None
    if segs[0] == "shape" and len(segs) == 3 and segs[1] == "radius" and segs[2] in _RADIUS_KEYS:
        return isinstance(value, str) and all(p.endswith("px") for p in value.split())
    if segs[0] == "components" and len(segs) == 3 and segs[1] in _COMPONENTS and segs[2] in _BOX_FIELDS:
        return True
    if segs[0] == "type" and len(segs) == 2:
        return True
    return False


def _mix_hex(a: str, b: str, ratio: float) -> str:
    """a 向 b 混合 ratio（0=a，1=b），返回 #RRGGBB。"""
    a = a.lstrip("#"); b = b.lstrip("#")
    if len(a) == 3:
        a = "".join(c * 2 for c in a)
    if len(b) == 3:
        b = "".join(c * 2 for c in b)
    ra, ga, ba = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    rb, gb, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    f = lambda x, y: round(x + (y - x) * ratio)
    return "#{:02x}{:02x}{:02x}".format(f(ra, rb), f(ga, gb), f(ba, bb)).replace("0x", "")


def _derive_scale(s500: str) -> dict[str, str]:
    """由主色推导 8 级色阶：向白/黑按比例混合，保证同色系由浅到深。"""
    white, black = "#ffffff", "#000000"
    return {
        "s50": _mix_hex(s500, white, 0.90),
        "s100": _mix_hex(s500, white, 0.78),
        "s200": _mix_hex(s500, white, 0.58),
        "s300": _mix_hex(s500, white, 0.38),
        "s400": _mix_hex(s500, white, 0.16),
        "s500": s500,
        "s600": _mix_hex(s500, black, 0.18),
        "s700": _mix_hex(s500, black, 0.34),
    }


# 常见中文色彩词 → hex；模型偶尔不按 #RRGGBB 输出时兜底
_COLOR_WORDS: list[tuple[str, str]] = [
    ("珊瑚红", "#ff7f6a"), ("钢青", "#5b7c89"), ("金属蓝", "#5b7c89"),
    ("工业灰", "#3a4145"), ("深灰", "#2f3437"), ("炭灰", "#2f3437"),
    ("青灰", "#6b7f86"), ("浅灰", "#d9dde0"), ("浅色", "#eef1f4"),
    ("白", "#ffffff"), ("黑", "#111111"),
    ("红", "#d0453b"), ("蓝", "#4a92bd"), ("绿", "#3f8f6b"),
    ("黄", "#d9a441"), ("紫", "#7a5ea8"), ("橙", "#e08a3c"),
]


def _normalize_value(path: str, value: Any) -> Any:
    if not isinstance(value, str) or _HEX.match(value.strip()):
        return value
    for word, hex_value in _COLOR_WORDS:
        if word in value:
            return hex_value
    return value


def _apply_changes(d: dict, changes: list[dict]) -> list[dict]:
    """逐条校验并应用；每条独立试装，防一条坏改毁整包。返回真正生效的 diff。"""
    applied: list[dict] = []
    for ch in changes:
        path = ch.get("path", "")
        raw_value = ch.get("value")
        reason = ch.get("reason", "")
        value = _normalize_value(path, raw_value)
        if not path or not _valid_change(path, value):
            continue
        notes = ["（色彩词已转 hex）"] if value != raw_value else []

        # 主色变更：自动推导整套色阶（不指望 LLM 算色阶）
        expand: list[tuple[str, Any]] = [(path, value)]
        if path == "color.accent.s500" and isinstance(value, str) and _HEX.match(value):
            expand = [(f"color.accent.{k}", v) for k, v in _derive_scale(value).items()]
            notes.append("（色阶自动推导）")

        for p, v in expand:
            probe = deepcopy(d)
            try:
                segs = p.split(".")
                cur = probe
                for seg in segs[:-1]:
                    cur = cur[seg]
                cur[segs[-1]] = v
                StyleTokens.model_validate(probe)
            except Exception:
                continue
            old = None
            try:
                old = _get_path(d, p)
            except Exception:
                pass
            segs = p.split(".")
            cur = d
            for seg in segs[:-1]:
                cur = cur[seg]
            cur[segs[-1]] = v
            applied.append({
                "path": p, "from": old, "to": v,
                "reason": (reason or "AI 调整") + "".join(dict.fromkeys(notes)),
            })
    return applied


def _tokens_from_rewrite_payload(data: dict) -> StyleTokens:
    """把 rewrite 模式的 tokens 片段合并到空模板并校验。"""
    payload = data.get("tokens") if isinstance(data.get("tokens"), dict) else data
    base = blank_default()
    merged = _deep_merge(base.model_dump(), payload)    # type: ignore
    merged["schemaVersion"] = "1.0"
    merged["prefix"] = base.prefix
    s500 = payload.get("color", {}).get("accent", {}).get("s500") # type: ignore
    if isinstance(s500, str) and _HEX.match(s500):
        merged["color"]["accent"] = _derive_scale(s500)
    return StyleTokens.model_validate(merged)


def _leaf_paths(obj: dict, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(_leaf_paths(value, path))
        else:
            out[path] = value
    return out


def _diff_tokens(before: StyleTokens, after: StyleTokens) -> list[dict]:
    """重写模式：对比全部叶子字段，生成可展示 diff。"""
    b = _leaf_paths(before.model_dump())
    a = _leaf_paths(after.model_dump())
    skip = {"schemaVersion", "prefix", "meta.created"}
    diff: list[dict] = []
    for path in sorted(set(b) | set(a)):
        if path in skip:
            continue
        if b.get(path) != a.get(path):
            diff.append({
                "path": path,
                "from": b.get(path),
                "to": a.get(path),
                "reason": "整体风格重写",
            })
    return diff


def _decide_mode(message: str, data: dict) -> str:
    """优先用 LLM 给出的 mode；缺失时做保守兜底。"""
    mode = str(data.get("mode") or "").strip().lower()
    if mode in ("rewrite", "adjust"):
        return mode
    return "rewrite" if re.search(
        r"做|改成|换成|换个|风格|工业|极简|赛博|复古|未来|科技|拟物|布局|排版|重新排|组件展示",
        message,
    ) else "adjust"


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 有值就用，没有保留 base（容忍 LLM 只回改动区块）。"""
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _get_path(d: dict, path: str) -> Any:
    cur: Any = d
    for seg in path.split("."):
        cur = cur[seg]
    return cur


# ---------- 对外接口 ----------

_PARSE_SYSTEM = """你是 UI 风格设计专家。用户会用一段话描述想要的 UI 风格，你输出风格 tokens JSON。

规则：
1. 只输出 JSON，不要任何解释和代码围栏
2. 允许只输出需要修改的顶层区块（meta/color/shape/line/elevation/motion/type/components），未提区块将被保留
3. 色值必须 #RRGGBB 格式；改主色只输出 color.accent.s500 一个值即可，系统会自动推导 50-700 整套色阶
4. 尊重用户明说的维度（圆角、投影、边框、动效、字体等），没提到的保持默认
5. meta 区务必给出：{"meta": {"name": "风格名(≤12字)", "note": "一句话风格要点"}}"""

_CHAT_SYSTEM = """你是 UI 风格设计与调整助手。先自行判断用户意图，选择一种输出模式，并在 JSON 里给出 mode 字段。

只输出 JSON，两种模式二选一：

A) 用户要做一个新风格、明确风格名、或整体大改：
   {"mode":"rewrite","tokens":{完整或部分 StyleTokens},"reply":"给用户的一句话回复"}
   - 基底是系统提供的「空模板」，不要继承折角/偏移投影/虚线焦点等旧签名
   - 可以自由覆盖颜色、圆角、边框、投影、字体、动效、组件等几十个字段
   - shape.radius 允许四角同值如 "8px"，也允许三圆一利旧写法
   - 未写的字段由空模板补齐；color.accent.s500 给出后系统自动推导整套色阶

B) 用户要在当前风格上微调：
   {"mode":"adjust","changes":[{"path":"字段路径","value":新值,"reason":"简短中文理由"}],"reply":"给用户的一句话回复"}
   - 修改数量不限，按用户意图决定，不要刻意压到 2-5 项
   - path 必须来自当前 tokens JSON 的真实字段
   - 改主色只改 color.accent.s500，系统自动推导整套色阶
   - "再XX一点"才表示在当前值基础上小步调整

通用规则：
1. 色值为 #RRGGBB；数值单位按原字段惯例（px 字符串 / ms 数字）
2. reply 必须只描述本次实际输出的字段；没写进 tokens/changes 的效果不许提
3. 动效映射：悬停放大→motion.hover="tilt"；缩小→"press"；上浮→"lift"；关闭→"none"；回弹强度→motion.easing_pop（CSS timing-function）或 motion.duration（ms）
4. 用户明确说「做一个…风格」「改成…」「工业风/极简风/赛博风」时，优先 rewrite；用户说「再柔和一点」「边框细一点」时，优先 adjust"""


def parse_prompt(text: str) -> StyleTokens:
    """提示词 → 初始风格档案。LLM 不可用/失败时兜底回 V0 关键词解析。"""
    if not enabled():
        return _stub_parse(text)
    try:
        template = blank_default().model_dump_json(indent=2)
        raw = raw_chat(_PARSE_SYSTEM, f"用户风格描述：\n{text}\n\n空模板基底：\n{template}")
        data = _extract_json(raw)
        data.setdefault("schemaVersion", "1.0")
        data.setdefault("prefix", "fd")
        # 深合并到空模板：LLM 只回改动区块也能拼出完整 tokens
        merged = _deep_merge(blank_default().model_dump(), data)
        merged["schemaVersion"] = "1.0"
        merged["prefix"] = "fd"
        # 主色统一走自动色阶推导，保证 50-700 同色系单调
        s500 = (data or {}).get("color", {}).get("accent", {}).get("s500")
        if isinstance(s500, str) and _HEX.match(s500):
            merged["color"]["accent"] = _derive_scale(s500)
        return StyleTokens.model_validate(merged)
    except Exception:
        return _stub_parse(text)


def chat_diff(
    tokens: StyleTokens,
    message: str,
    history: list[dict] | None = None,
) -> tuple[StyleTokens, list[dict], str]:
    """多轮对话优化。LLM 不可用/失败时兜底回风格词典。"""
    if not enabled():
        return dict_style.apply_message(tokens, message)
    try:
        user = (
            f"当前风格 tokens：\n{tokens.model_dump_json(indent=2)}\n\n"
            f"空模板基底（rewrite 用）：\n{blank_default().model_dump_json(indent=2)}\n\n"
            f"用户消息：{message}"
        )
        raw = raw_chat(_CHAT_SYSTEM, user, history=history)
        data = _extract_json(raw)
        reply = str(data.get("reply") or "").strip()
        mode = _decide_mode(message, data)
        logger.info("LLM 判定模式=%s message=%r", mode, message[:60])
        if mode == "rewrite":
            nt = _tokens_from_rewrite_payload(data)
            return nt, _diff_tokens(tokens, nt), reply or f"已重写为「{message.strip()}」对应的完整风格。"
        changes = data.get("changes", [])
        d = tokens.model_dump()
        applied = _apply_changes(d, changes)
        if applied:
            return StyleTokens.model_validate(d), applied, reply or f"已按「{message.strip()}」调整 {len(applied)} 项。"
        if changes:
            return tokens, [], "本轮模型建议未通过字段校验，样式保持不变。可以说得更具体，例如「主色改成 #5b7c89」「边框细一点」。"
        return tokens, [], reply or "本轮没有具体改动，样式保持不变。"
    except Exception:
        return dict_style.apply_message(tokens, message)


async def chat_diff_stream(
    tokens: StyleTokens,
    message: str,
    history: list[dict] | None = None,
):
    """SSE 版对话调整：系统思考 → 模型输出 → 整理校验 → 最终方案。

    reasoning 只在供应商显式返回时透传；系统思考是编排步骤，不伪装成模型内部推理。
    """
    yield {"type": "stage", "stage": "thinking", "label": "思考中"}
    yield {
        "type": "thought", "stage": "thinking",
        "thought": f"读取当前风格「{tokens.meta.name}」，用户要求：{message.strip()}",
    }
    yield {"type": "thought", "stage": "thinking", "thought": "正在确定需要调整的维度与约束…"}

    if not enabled():
        yield {"type": "thought", "stage": "thinking", "thought": "未配置模型，改用本地风格词典。"}
        nt, diff, reply = dict_style.apply_message(tokens, message)
        yield {"type": "stage", "stage": "done", "label": "完成"}
        yield {"type": "done", "mode": "adjust", "tokens": nt.model_dump(mode="json"), "diff": diff, "reply": reply}
        return

    buf = ""
    reasoning = ""
    changes: list[dict] = []
    reply = ""
    try:
        yield {"type": "stage", "stage": "generating", "label": "模型输出"}
        user = (
            f"当前风格 tokens：\n{tokens.model_dump_json(indent=2)}\n\n"
            f"空模板基底（rewrite 用）：\n{blank_default().model_dump_json(indent=2)}\n\n"
            f"用户消息：{message}"
        )
        async for kind, chunk in raw_chat_stream(_CHAT_SYSTEM, user, history=history):
            if kind == "usage":
                continue
            text = chunk if isinstance(chunk, str) else ""
            if kind == "reasoning":
                reasoning += text
                yield {"type": "reasoning", "delta": text}
            else:
                buf += text
                yield {"type": "delta", "delta": text}

        yield {"type": "stage", "stage": "organizing", "label": "整理中"}
        yield {
            "type": "thought", "stage": "organizing",
            "thought": f"收到模型输出 {len(buf)} 字符，正在提取 changes 与 reply。",
        }
        if reasoning:
            yield {
                "type": "thought", "stage": "organizing",
                "thought": f"供应商额外返回 {len(reasoning)} 字符推理摘要，已单独展示。",
            }

        data = _extract_json(buf)
        mode = _decide_mode(message, data)
        reply = str(data.get("reply") or "").strip()
        logger.info("LLM 判定模式=%s message=%r", mode, message[:60])
        yield {
            "type": "thought", "stage": "organizing",
            "thought": f"LLM 判定模式：{'重写基底 rewrite' if mode == 'rewrite' else '增量调整 adjust'}",
        }

        if mode == "rewrite":
            yield {"type": "stage", "stage": "applying", "label": "生成方案"}
            yield {"type": "thought", "stage": "applying", "thought": "以空模板为基底重建完整 tokens。"}
            nt = _tokens_from_rewrite_payload(data)
            diff = _diff_tokens(tokens, nt)
            yield {"type": "thought", "stage": "applying", "thought": f"重写完成，共 {len(diff)} 项差异。"}
            yield {"type": "stage", "stage": "done", "label": "完成"}
            yield {
                "type": "done", "mode": "rewrite",
                "tokens": nt.model_dump(mode="json"), "diff": diff,
                "reply": reply or f"已重写为「{message.strip()}」对应的完整风格。",
            }
            return

        changes = data.get("changes", [])
        yield {"type": "thought", "stage": "organizing", "thought": f"解析到 {len(changes)} 条候选修改。"}

        yield {"type": "stage", "stage": "validating", "label": "校验中"}
        for ch in changes:
            path = str(ch.get("path", ""))
            raw = ch.get("value")
            value = _normalize_value(path, raw)
            ok = _valid_change(path, value)
            note = "（色彩词已转 hex）" if value != raw else ""
            yield {
                "type": "thought", "stage": "validating",
                "thought": f"{path or '(空路径)'} = {value} → {'通过' if ok else '丢弃：路径或值不合法'}{note}",
            }

        yield {"type": "stage", "stage": "applying", "label": "生成方案"}
        d = tokens.model_dump()
        applied = _apply_changes(d, changes)
        yield {"type": "thought", "stage": "applying", "thought": f"实际生效 {len(applied)} 项修改。"}

        if not applied:
            nt = tokens
            diff = []
            if changes:
                yield {"type": "thought", "stage": "applying", "thought": "模型改动全部未通过字段校验，保留当前风格。"}
                reply = reply or "本轮模型建议未通过字段校验，样式保持不变。可以说得更具体，例如「主色改成 #5b7c89」「边框细一点」。"
            else:
                yield {"type": "thought", "stage": "applying", "thought": "模型未给出具体改动，保留当前风格。"}
                reply = reply or "本轮没有具体改动，样式保持不变。"
        else:
            nt = StyleTokens.model_validate(d)
            diff = applied
            reply = reply or f"已按「{message.strip()}」调整 {len(applied)} 项。"

        yield {"type": "stage", "stage": "done", "label": "完成"}
        yield {"type": "done", "mode": "adjust", "tokens": nt.model_dump(mode="json"), "diff": diff, "reply": reply}
    except Exception as e:
        yield {"type": "thought", "stage": "organizing", "thought": f"模型输出不可用（{e.__class__.__name__}），改用本地风格词典。"}
        nt, diff, reply = dict_style.apply_message(tokens, message)
        yield {"type": "stage", "stage": "done", "label": "完成"}
        yield {"type": "done", "mode": "adjust", "tokens": nt.model_dump(mode="json"), "diff": diff, "reply": reply}


# ---------- V0 stub 兜底（原关键词解析，保留） ----------


def _stub_parse(text: str) -> StyleTokens:
    from .tokens import AccentScale

    tokens = StyleTokens()
    m = re.search(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", text)
    if m:
        tokens.color.accent = AccentScale(s500=m.group(0))
        tokens.meta.name = f"自定义风格 · {m.group(0)}"
    if re.search(r"柔和|温柔|轻柔", text):
        tokens.elevation.type = "soft-blur"
        tokens.elevation.levels = dict_style._LEVELS()["soft-blur"]
        tokens.line.border_width = 1
    if re.search(r"硬朗|利落|印刷|复古", text):
        tokens.elevation.type = "offset-solid"
        tokens.elevation.levels = dict_style._LEVELS()["offset-solid"]
        tokens.line.focus_style = "dashed"
    if re.search(r"圆润", text):
        for key in ("lg", "md", "sm"):
            parts = getattr(tokens.shape.radius, key).split()
            setattr(tokens.shape.radius, key,
                    " ".join(f"{int(float(p.replace('px', '')) + 4)}px" for p in parts))
    if re.search(r"俏皮|活泼", text):
        tokens.motion.hover = "tilt"
    return tokens


# ---------- V2 自由产物包：生成阶段只限制输出位置，不限制视觉发挥 ----------

_FREE_ARTIFACT_SYSTEM = """你是 UI 风格生成与改造助手。你的任务不是填写字段表，而是直接产出一套完整风格包。
只输出一个 JSON 对象，不要解释，不要代码围栏。

JSON 字段固定如下：
{
  "meta": {"name":"风格名≤12字","version":"1.0","note":"一句话风格要点"},
  "reply":"给用户的一句话说明",
  "style_prompt":"一段可复刻该风格的中文提示词，必须覆盖颜色、材质/纹理、背景层、边框、投影、字体、动效、展示结构",
  "preview_html":"用于展示该风格的完整 HTML 片段；rewrite 时自主设计布局，adjust 时原样保留上一版布局",
  "base_css":"基础 CSS，可包含任意 :root 变量、reset、字体、背景层",
  "style_css":"组件与视觉 CSS，可包含任意渐变、纹理、伪元素、动画、 inset shadow、状态灯、装饰件",
  "semantic_diff":[
    {"kind":"visual","path":"材质/背景/字体等语义维度","from":"旧值或空","to":"新值","reason":"为什么改"}
  ]
}

硬性要求：
1. 每次都输出完整产物；不要输出 tokens、changes、path 白名单或字段映射。
2. base_css、style_css 的视觉内容完全自由；不要为了适配任何内部 schema 而简化视觉。
3. style_prompt 必须足够具体，让另一个助手只凭它就能复刻同款视觉 DNA。
4. preview_html 展示规则：
   - 用户消息会标注 [MODE: rewrite] 或 [MODE: adjust]。
   - rewrite（首次定义 / 整体换风格）：布局由你自主决定，但必须展示七个核心组件用于验证视觉 DNA：Button、Card、Input、Toast、Dropdown、Modal、Select；可以附 Badge & Link。它们只是风格样板，不代表风格被组件绑定。
   - Toast、Dropdown、Modal 与 Select 必须可交互：Toast 由按钮点击后动态弹出（带进出动效，不静态摊开）；Dropdown 默认收起，点击或 hover 展开，选项点击能触发一条 Toast 反馈；Modal 默认隐藏，由按钮打开，点遮罩 / 关闭按钮 / Esc 可关，确认按钮弹一条 Toast；Select 默认收起，点击触发器展开浮层，选项点击即选中并弹 Toast，点外部 / Esc 关闭。
   - 禁止用浏览器原生 <select> 元素：它的展开面板由浏览器绘制，无法体现折角、硬边与实心投影；Select 必须用自定义触发器 + 浮层实现。
   - adjust（微调）：原样保留上一版 preview_html 的 HTML 结构与布局，不要新增、删除、重排组件；只改 CSS、Prompt、reply 和 semantic_diff。除非用户明确要求改布局，否则绝不改布局。
5. reply 只描述本次真实写入产物的变化，不要承诺未写进 CSS/HTML 的效果。
6. 用户消息里的「场景/载体/风格/色彩/材质/密度/字体：」前缀是表达辅助，不是硬约束；如果与「用户补充」冲突，以用户补充为准。"""


def _artifact_context(bundle: StyleBundle, mode: str = "adjust") -> str:
    mode = "rewrite" if mode == "rewrite" else "adjust"
    mode_note = (
        "[MODE: rewrite] 首次定义或整体重写：可自主设计 preview_html 布局，但必须展示七个核心组件样板。"
        if mode == "rewrite"
        else "[MODE: adjust] 微调：必须原样保留当前 preview_html 的结构与布局，只调整视觉产物。"
    )
    return (
        f"{mode_note}\n\n"
        f"当前产物包：\n{bundle.model_dump_json(indent=2)}\n\n"
        "注意：当前产物包只作为上下文。rewrite 可重写所有文件；adjust 不允许改 preview.html 布局。"
    )


def _source_meta() -> tuple[str, str]:
    base, _key, model = _creds()
    return model, base


def parse_prompt_bundle(prompt: str, baseline: StyleBundle | None = None) -> StyleBundle:
    """用户提示词 → V2 自由产物包。失败时保留传入基线，不回退 V1。"""
    model, base = _source_meta()

    def failed_bundle(reply: str) -> StyleBundle:
        failed = (baseline or StyleBundle()).model_copy(deep=True)
        failed.reply = reply
        failed.source.prompt = prompt
        failed.source.model = model
        failed.source.base_url = base
        append_history(failed, "user", prompt)
        append_history(failed, "assistant", reply)
        return failed

    if not enabled():
        return failed_bundle("未配置模型，当前产物包保持不变。")
    try:
        raw, usage, duration_ms = raw_chat_with_usage(
            _FREE_ARTIFACT_SYSTEM,
            f"[MODE: rewrite]\n用户要求：\n{prompt}\n\n请输出完整风格产物包。",
            timeout=_ARTIFACT_TIMEOUT,
        )
        data = _extract_json(raw)
        bundle = normalize_bundle_payload(
            data,
            previous=None,
            source_prompt=prompt,
            raw_response=raw,
            model=model,
            base_url=base,
            usage=usage,
            duration_ms=duration_ms,
        )
        logger.info("首次生成完成 usage=%s duration_ms=%s", usage, duration_ms)
        append_history(bundle, "user", prompt)
        append_history(bundle, "assistant", bundle.reply or f"已生成风格「{bundle.meta.name}」。")
        return bundle
    except Exception:
        logger.exception("自由产物生成失败，保留当前产物包")
        return failed_bundle("本轮模型输出不可用，当前产物包保持不变。")


def chat_bundle(
    bundle: StyleBundle,
    message: str,
    history: list[dict] | None = None,
    mode: str = "adjust",
) -> tuple[StyleBundle, list[dict], str]:
    """多轮对话 → 完整 V2 产物包。mode=rewrite 时允许重排 preview.html。"""
    model, base = _source_meta()
    if not enabled():
        reply = "未配置模型，当前产物包保持不变。"
        append_history(bundle, "user", message)
        append_history(bundle, "assistant", reply)
        return bundle, [], reply
    try:
        raw, usage, duration_ms = raw_chat_with_usage(
            _FREE_ARTIFACT_SYSTEM,
            f"{_artifact_context(bundle, mode)}\n\n用户消息：{message}",
            history=history,
            timeout=_ARTIFACT_TIMEOUT,
        )
        data = _extract_json(raw)
        reply = str(data.get("reply") or "").strip() or f"已按「{message.strip()}」更新完整风格包。"
        next_bundle = normalize_bundle_payload(
            data,
            previous=bundle,
            source_prompt=message,
            raw_response=raw,
            model=model,
            base_url=base,
            preserve_preview_html=(mode != "rewrite"),
            usage=usage,
            duration_ms=duration_ms,
        )
        next_bundle.reply = reply
        append_history(next_bundle, "user", message)
        append_history(next_bundle, "assistant", reply)
        logger.info("对话完成 mode=%s usage=%s duration_ms=%s", mode, usage, duration_ms)
        return next_bundle, diff_bundles(bundle, next_bundle), reply
    except Exception:
        logger.exception("自由产物对话失败，保留当前产物包")
        reply = "本轮模型输出不可用，当前产物包保持不变。"
        append_history(bundle, "user", message)
        append_history(bundle, "assistant", reply)
        return bundle, [], reply


async def chat_bundle_stream(
    bundle: StyleBundle,
    message: str,
    history: list[dict] | None = None,
    mode: str = "adjust",
):
    """SSE 版 V2 产物包生成。mode=rewrite 时允许重排 preview.html。"""
    started = time.perf_counter()
    model, base = _source_meta()
    usage: dict[str, Any] | None = None
    yield {"type": "stage", "stage": "thinking", "label": "思考中"}
    yield {
        "type": "thought", "stage": "thinking",
        "thought": f"读取当前产物「{bundle.meta.name}」，用户要求：{message.strip()}",
    }
    yield {
        "type": "thought", "stage": "thinking",
        "thought": ("重写模式：preview.html 布局自主决定，但需展示七个核心组件。"
                    if mode == "rewrite" else "微调模式：保留 preview.html 布局，只调整视觉产物。"),
    }

    if not enabled():
        reply = "未配置模型，当前产物包保持不变。"
        append_history(bundle, "user", message)
        append_history(bundle, "assistant", reply)
        yield {"type": "stage", "stage": "done", "label": "完成"}
        yield {
            "type": "done", "mode": "artifact", "bundle": bundle.model_dump(mode="json"),
            "diff": [], "reply": reply,
            "usage": normalize_usage(None, model, base),
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        return

    buf = ""
    reasoning = ""
    try:
        yield {"type": "stage", "stage": "generating", "label": "模型输出"}
        async for kind, chunk in raw_chat_stream(
            _FREE_ARTIFACT_SYSTEM,
            f"{_artifact_context(bundle, mode)}\n\n用户消息：{message}",
            history=history,
            timeout=_ARTIFACT_TIMEOUT,
        ):
            if kind == "usage":
                usage = chunk if isinstance(chunk, dict) else None
                if usage is not None:
                    yield {"type": "usage", "usage": usage}
                continue
            text = chunk if isinstance(chunk, str) else ""
            if kind == "reasoning":
                reasoning += text
                yield {"type": "reasoning", "delta": text}
            else:
                buf += text
                yield {"type": "delta", "delta": text}

        yield {"type": "stage", "stage": "organizing", "label": "整理中"}
        yield {
            "type": "thought", "stage": "organizing",
            "thought": f"收到模型输出 {len(buf)} 字符，正在写入固定产物包结构。",
        }
        if reasoning:
            yield {
                "type": "thought", "stage": "organizing",
                "thought": f"供应商额外返回 {len(reasoning)} 字符推理摘要，已单独展示。",
            }

        data = _extract_json(buf)
        reply = str(data.get("reply") or "").strip() or f"已按「{message.strip()}」更新完整风格包。"
        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = usage or normalize_usage(None, model, base)
        next_bundle = normalize_bundle_payload(
            data,
            previous=bundle,
            source_prompt=message,
            raw_response=buf,
            model=model,
            base_url=base,
            preserve_preview_html=(mode != "rewrite"),
            usage=usage,
            duration_ms=duration_ms,
        )
        next_bundle.reply = reply
        append_history(next_bundle, "user", message)
        append_history(next_bundle, "assistant", reply)
        diff = diff_bundles(bundle, next_bundle)
        logger.info("流式生成完成 mode=%s usage=%s duration_ms=%s", mode, usage, duration_ms)

        yield {"type": "stage", "stage": "done", "label": "完成"}
        yield {
            "type": "done", "mode": "artifact",
            "bundle": next_bundle.model_dump(mode="json"),
            "diff": diff,
            "reply": reply,
            "usage": usage,
            "duration_ms": duration_ms,
        }
    except Exception as e:
        logger.exception("自由产物流式生成失败")
        yield {
            "type": "thought", "stage": "organizing",
            "thought": f"模型输出不可用（{e.__class__.__name__}），保留当前产物包。",
        }
        reply = "本轮模型输出不可用，当前产物包保持不变。"
        append_history(bundle, "user", message)
        append_history(bundle, "assistant", reply)
        yield {"type": "stage", "stage": "done", "label": "完成"}
        yield {
            "type": "done", "mode": "artifact", "bundle": bundle.model_dump(mode="json"),
            "diff": [], "reply": reply,
            "usage": usage or normalize_usage(None, model, base),
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
