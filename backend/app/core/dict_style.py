"""风格词典：模糊指令 → token 定向 diff。

这是"不抽卡"的关键：每轮对话只动相关维度，其余不动。
规则本体在 style_dict.yaml（数据文件，mtime 热加载）——加词条改 YAML，不改代码。
本模块是 YAML 指令的通用解释器：set / set_elevation / levels / num_delta /
floor_min / cap_max / round_fold / radius_delta，支持 if 条件。
"""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .tokens import StyleTokens

DiffItem = dict[str, Any]  # {path, from, to, reason}

_DICT_FILE = Path(__file__).resolve().parent / "style_dict.yaml"
_cache: dict[str, Any] = {"mtime": 0.0, "data": {"levels": {}, "rules": []}}


def _load(force: bool = False) -> dict[str, Any]:
    """带 mtime 热加载：YAML 改动后下次调用自动生效。"""
    mtime = _DICT_FILE.stat().st_mtime
    if force or mtime != _cache["mtime"]:
        with open(_DICT_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _cache["data"] = {"levels": data.get("levels", {}), "rules": data.get("rules", [])}
        _cache["mtime"] = mtime
    return _cache["data"]


def reload() -> None:
    """强制重载词典（供测试/管理接口用）。"""
    _load(force=True)


# ---------- 投影级别组（从 YAML 预设读取，保持向后兼容） ----------
def _LEVELS() -> dict[str, dict[str, str]]:
    return deepcopy(_load()["levels"])


# ---------- token dict 路径读写 ----------
def _get(d: dict, path: str) -> Any:
    cur: Any = d
    for seg in path.split("."):
        cur = cur[seg]
    return cur


def _set(d: dict, path: str, value: Any) -> None:
    segs = path.split(".")
    cur = d
    for seg in segs[:-1]:
        cur = cur[seg]
    cur[segs[-1]] = value


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------- 操作解释器 ----------
def _run_op(op: dict[str, Any], d: dict, diff: list[DiffItem]) -> None:
    kind = op.get("op")
    reason = op.get("reason", "")

    # 通用 if 条件
    cond = op.get("if")
    if cond and _get(d, cond["path"]) != cond["equals"]:
        return

    if kind == "set":
        path, value = op["path"], op["value"]
        if _get(d, path) != value:
            diff.append({"path": path, "from": _get(d, path), "to": value, "reason": reason})
            _set(d, path, value)

    elif kind == "set_elevation":
        etype, path = op["type"], "elevation.type"
        if _get(d, path) != etype:
            diff.append({"path": path, "from": _get(d, path), "to": etype, "reason": reason})
            _set(d, path, etype)
            _set(d, "elevation.levels", deepcopy(_load()["levels"][etype]))

    elif kind == "levels":
        levels = {k: op[k] for k in ("e1", "e2", "e3")}
        if _get(d, "elevation.levels") != levels:
            diff.append({"path": "elevation.levels", "from": "当前", "to": str(levels), "reason": reason})
            _set(d, "elevation.levels", deepcopy(levels))

    elif kind == "num_delta":
        path, delta = op["path"], float(op["delta"])
        lo, hi = op.get("clamp", [-1e9, 1e9])
        old = float(_get(d, path))
        new = _clamp(old + delta, lo, hi)
        if new != old:
            diff.append({"path": path, "from": old, "to": new, "reason": reason})
            _set(d, path, new)

    elif kind == "floor_min":
        path, value = op["path"], op["value"]
        old = _get(d, path)
        if old < value:
            diff.append({"path": path, "from": old, "to": value, "reason": reason})
            _set(d, path, value)

    elif kind == "cap_max":
        path, value = op["path"], op["value"]
        old = _get(d, path)
        if old > value:
            diff.append({"path": path, "from": old, "to": value, "reason": reason})
            _set(d, path, value)

    elif kind == "round_fold":
        path = op["path"]
        r = str(_get(d, path)).split()
        if len(r) == 4 and r[-1] != r[0]:
            _set(d, path, f"{r[0]} {r[1]} {r[2]} {r[0]}")
            diff.append({"path": path, "from": " ".join(r), "to": _get(d, path), "reason": reason})

    elif kind == "radius_delta":
        add = int(op["add"])
        for key in ("lg", "md", "sm"):
            path = f"shape.radius.{key}"
            parts = str(_get(d, path)).split()
            _set(d, path, " ".join(f"{int(float(p.replace('px', '')) + add)}px" for p in parts))
        diff.append({"path": "shape.radius", "from": "原圆角", "to": f"各角 +{add}px", "reason": reason})

    else:
        raise ValueError(f"未知词典操作：{kind!r}（style_dict.yaml）")


# ---------- 匹配入口（对外 API 不变） ----------
def apply_message(tokens: StyleTokens, message: str) -> tuple[StyleTokens, list[DiffItem], str]:
    """解析用户消息 → 修改 tokens（dict 形式）→ 返回新 tokens、diff、回复文案。

    V0 规则引擎实现；V1 由 llm.py 接管，本函数退化为兜底。
    """
    data = _load()
    d = tokens.model_dump()
    diff: list[DiffItem] = []
    matched = 0
    for rule in data["rules"]:
        pattern = "|".join(rule["keywords"])
        if re.search(pattern, message):
            matched += 1
            for op in rule.get("ops", []):
                _run_op(op, d, diff)

    new_tokens = StyleTokens.model_validate(d)

    if matched == 0:
        words = "」「".join(w for r in data["rules"] for w in r["keywords"][:1])
        reply = (
            "这句我还不会映射到具体风格维度。试试这些说法：「"
            + words + "」，"
            "或者直接说维度，比如「边框细一点」「投影轻一点」。（V1 接入大模型后可自由表达）"
        )
    else:
        parts = "；".join(f"{item['reason']}（{item['path']}）" for item in diff)
        reply = f"已按「{message.strip()}」调整：{parts}。右侧预览已同步。"

    return new_tokens, diff, reply


def keywords() -> list[str]:
    """全部词条首关键词（给前端快捷指令用）。"""
    return [r["keywords"][0] for r in _load()["rules"]]
