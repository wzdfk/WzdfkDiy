"""tokens → base.css / style.css 渲染器。

模板在 app/templates/ 下，本模块负责：
- 推导派生值（投影色、注释文案）
- 调 Jinja2 渲染
输出即最终产物 —— 预览 iframe 加载的就是这份 CSS，所见即所导。
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .tokens import StyleTokens

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

# 投影类型 → 中文说明
_ELEV_NOTE = {
    "offset-solid": "偏移实心投影（色块硬投影，无模糊，印刷感）",
    "soft-blur": "柔和模糊投影（低透明度弥散）",
    "layered": "分层投影（多层叠加）",
}

# 圆角策略 → 中文说明
_SHAPE_NOTE = {
    "fold": "折角圆角，三圆一利",
    "uniform": "统一圆角，四角相同",
    "asymmetric": "不对称圆角",
}

# 焦点样式 → 中文说明
_FOCUS_NOTE = {
    "dashed": "虚线焦点环（打印标记感）",
    "solid": "实线焦点环",
    "glow": "柔和光圈",
}

_HOVER_CN = {"lift": "悬浮抬起", "press": "按压收拢", "tilt": "倾斜俏皮", "none": "无位移"}
_ACTIVE_CN = {"press": "按下压扁", "none": "无反馈"}


def _shadow_color(t: StyleTokens) -> str:
    """投影色：显式指定优先，否则按投影类型从墨色+主色推导。"""
    if t.color.shadow:
        return t.color.shadow
    if t.elevation.type == "soft-blur":
        return f"color-mix(in srgb, {t.color.ink.ink900} 25%, transparent)"
    # offset-solid / layered：近墨色掺主色，投影自带一点主题倾向
    return f"color-mix(in srgb, {t.color.ink.ink900} 88%, {t.color.accent.s500})"


def _context(t: StyleTokens) -> dict:
    # 投影级别里的变量占位统一按前缀归一（词典/默认值统一用 --s-shadow 占位）
    levels = {
        k: v.replace("--s-shadow", f"--{t.prefix}-shadow")
        for k, v in t.elevation.levels.items()
    }
    # 组件字段 → CSS 值映射（radius_ref / shadow_ref 解引用）
    radius_var = {k: f"var(--{t.prefix}-r-{k})" for k in ("sm", "md", "lg")}
    shadow_var = {
        "none": "none",
        "e1": "var(--%s-e1)" % t.prefix,
        "e2": "var(--%s-e2)" % t.prefix,
        "e3": "var(--%s-e3)" % t.prefix,
    }
    # 各组件解析后的盒模型值 + @token 溯源
    comp: dict[str, dict] = {}
    for name, box in t.components.model_dump().items():
        obj = getattr(t.components, name)
        shadow = box.get("custom_shadow")
        if shadow:
            shadow = shadow.replace("{p}", t.prefix)
        else:
            shadow = shadow_var[box["shadow_ref"]]
        comp[name] = {
            "padding": f"{box['padding_y']} {box['padding_x']}",
            "font_size": box["font_size"] or t.type.body_size,
            "font_weight": box["font_weight"],
            "radius": radius_var[box["radius_ref"]],
            "shadow": shadow,
            "margin_bottom": box["margin_bottom"],
            "token": f"components.{name}",       # CSS 溯源注释
        }
    return {
        "t": t,
        "p": t.prefix,
        "levels": levels,
        "comp": comp,
        "shadow_color": _shadow_color(t),
        "shape_note": _SHAPE_NOTE[t.shape.strategy],
        "elev_note": _ELEV_NOTE[t.elevation.type],
        "focus_note": _FOCUS_NOTE[t.line.focus_style],
        "hover_cn": _HOVER_CN[t.motion.hover],
        "active_cn": _ACTIVE_CN[t.motion.active],
    }


def render_base_css(tokens: StyleTokens) -> str:
    return _ENV.get_template("base.css.j2").render(**_context(tokens))


def render_style_css(tokens: StyleTokens) -> str:
    return _ENV.get_template("style.css.j2").render(**_context(tokens))


def render_combined_css(tokens: StyleTokens) -> str:
    """base + style 合并输出（预览 iframe 单文件注入用）。"""
    return render_base_css(tokens) + "\n\n" + render_style_css(tokens)
