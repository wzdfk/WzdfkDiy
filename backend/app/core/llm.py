"""LLM adapter · V1 真实现（OpenAI 兼容接口：智谱 GLM / DeepSeek / OpenAI 等）。

接口约定（对外 API 与 V0 一致）：
- parse_prompt(text) -> StyleTokens                       首次定义风格
- chat_diff(tokens, message, history) -> (tokens', diff, reply)   多轮优化

配置优先级：界面设置（app/data/llm_settings.json）> .env（BASE_URL/API_KEY）> 默认值。
LLM 不可用/输出不合法时自动兜底回风格词典（dict_style），服务永不因 LLM 挂掉而挂。
"""
from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

from . import dict_style
from .tokens import ControlBox, StyleTokens, blank_default, fold_default

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "data" / "llm_settings.json"

_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
_DEFAULT_MODEL = "glm-4-flash"
_TIMEOUT = 60.0

# ---------- 运行时设置（界面可改，优先于 .env） ----------


def _read_settings() -> dict[str, Any]:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(cfg: dict[str, Any]) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_settings() -> dict[str, Any]:
    """给设置面板的当前配置（key 掩码）。"""
    cfg = _read_settings()
    env_key = os.getenv("API_KEY", "")
    key = cfg.get("api_key") or env_key
    masked = (key[:6] + "****" + key[-4:]) if len(key) > 10 else ("已配置" if key else "")
    return {
        "base_url": cfg.get("base_url") or os.getenv("BASE_URL") or _DEFAULT_BASE_URL,
        "model": cfg.get("model") or _DEFAULT_MODEL,
        "key_masked": masked,
        "has_key": bool(key),
        "enabled": bool(key),
    }


def save_settings(base_url: str, model: str, api_key: str | None = None) -> dict[str, Any]:
    """保存设置。api_key 为 None/空串 = 保留已存 key。"""
    cfg = _read_settings()
    cfg["base_url"] = (base_url or "").strip() or _DEFAULT_BASE_URL
    cfg["model"] = (model or "").strip() or _DEFAULT_MODEL
    if api_key:  # 非空才覆盖
        cfg["api_key"] = api_key.strip()
    _save_settings(cfg)
    return get_settings()


# ---------- 凭据与底层调用 ----------


def _creds() -> tuple[str, str, str]:
    cfg = _read_settings()
    base = cfg.get("base_url") or os.getenv("BASE_URL") or _DEFAULT_BASE_URL
    key = cfg.get("api_key") or os.getenv("API_KEY") or ""
    model = cfg.get("model") or _DEFAULT_MODEL
    return base, key, model


def enabled() -> bool:
    return bool(_creds()[1])


def raw_chat(system: str, user: str, history: list[dict] | None = None) -> str:
    """OpenAI 兼容 chat/completions 裸调用，返回 assistant 文本。失败抛异常。"""
    base, key, model = _creds()
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in (history or []):
        if m.get("role") in ("user", "bot") and m.get("text"):
            messages.append({"role": "user" if m["role"] == "user" else "assistant",
                             "content": m["text"]})
    messages.append({"role": "user", "content": user})

    r = httpx.post(
        base,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.4},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


async def raw_chat_stream(system: str, user: str, history: list[dict] | None = None):
    """OpenAI 兼容流式调用； yields ('reasoning'|'content', text)。

    若供应商提供 reasoning_content / reasoning 字段，会单独作为 reasoning 流输出；
    没有则不伪造模型思考，只输出 content 流。
    """
    base, key, model = _creds()
    if not key:
        raise RuntimeError("未配置 API Key")
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in (history or []):
        if m.get("role") in ("user", "bot") and m.get("text"):
            messages.append({"role": "user" if m["role"] == "user" else "assistant",
                             "content": m["text"]})
    messages.append({"role": "user", "content": user})

    payload = {"model": model, "messages": messages, "temperature": 0.4, "stream": True}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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
    merged = _deep_merge(base.model_dump(), payload)
    merged["schemaVersion"] = "1.0"
    merged["prefix"] = base.prefix
    s500 = payload.get("color", {}).get("accent", {}).get("s500")
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
    return "rewrite" if re.search(r"做|改成|换成|换个|风格|工业|极简|赛博|复古|未来|科技|拟物", message) else "adjust"


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
        if _decide_mode(message, data) == "rewrite":
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
        async for kind, text in raw_chat_stream(_CHAT_SYSTEM, user, history=history):
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
