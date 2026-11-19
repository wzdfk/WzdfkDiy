"""tokens → STYLE_PROMPT.md（风格复原提示词）。

人话版风格描述 + 扩展规范，喂给任意 AI 可复刻出同款风格。
"""
from __future__ import annotations

from .css_gen import _ACTIVE_CN, _ELEV_NOTE, _FOCUS_NOTE, _HOVER_CN, _SHAPE_NOTE, _ENV
from .tokens import StyleTokens


def _signature_rules(t: StyleTokens) -> list[str]:
    rules: list[str] = []
    if t.shape.strategy == "fold":
        rules.append(f"**折角圆角**——三圆一利（{t.shape.radius.sm}），像纸折了一角，全局贯穿，不许出现四角全圆")
    elif t.shape.strategy == "uniform":
        rules.append("**统一圆角**——四角相同，工整克制")
    else:
        rules.append("**不对称圆角**——四角刻意不等，打破呆板")

    if t.elevation.type == "offset-solid":
        rules.append("**偏移实心投影**——投影是实色块（e1/e2/e3 三级），不用模糊阴影，印刷感")
    elif t.elevation.type == "soft-blur":
        rules.append("**柔和模糊投影**——低透明度弥散阴影，轻盈通透")
    else:
        rules.append("**分层投影**——多层阴影叠加，层次细腻")

    rules.append(f"**硬边细线**——{t.line.border_width:g}px {t.line.border_style} 描边是骨架，所有组件带边框")

    focus_map = {
        "dashed": "键盘焦点用**虚线框**（打印标记感）",
        "solid": "键盘焦点用**实线框**",
        "glow": "焦点用**柔和光圈**",
    }
    rules.append(f"**焦点规则**——{focus_map[t.line.focus_style]}")

    hover_map = {
        "lift": "hover 元素**抬起**（反向位移+投影升级）",
        "press": "hover **收拢**",
        "tilt": "hover **微倾斜**，俏皮",
        "none": "hover 无位移",
    }
    active_map = {"press": "active **按下压扁**（正向位移+投影缩到 1px）", "none": "active 无反馈"}
    rules.append(f"**物理交互**——{hover_map[t.motion.hover]}，{active_map[t.motion.active]}")

    rules.append(f"**统一动效节奏**——{t.motion.duration}ms、回弹曲线 {t.motion.easing_pop}，全站一个节奏")
    return rules


def _one_liner(t: StyleTokens) -> str:
    elev = {"offset-solid": "偏移实心投影", "soft-blur": "柔和模糊投影", "layered": "分层投影"}[t.elevation.type]
    shape = {"fold": "折角圆角", "uniform": "统一圆角", "asymmetric": "不对称圆角"}[t.shape.strategy]
    return (
        f"以 {t.color.accent.s500} 为主色的低饱和 UI：{t.color.paper} 底 + 白面板，"
        f"{shape}，{t.line.border_width:g}px 硬边细线描边，{elev}，"
        f"{t.motion.duration}ms 回弹微动效，{t.type.display_weight} 字重标题。"
    )


def render_style_prompt(tokens: StyleTokens) -> str:
    tpl = _ENV.get_template("prompt.md.j2")
    return tpl.render(
        t=tokens,
        one_liner=_one_liner(tokens),
        signature_rules=_signature_rules(tokens),
        shape_note=_SHAPE_NOTE[tokens.shape.strategy],
        elev_note=_ELEV_NOTE[tokens.elevation.type],
        focus_note=_FOCUS_NOTE[tokens.line.focus_style],
        hover_cn=_HOVER_CN[tokens.motion.hover],
        active_cn=_ACTIVE_CN[tokens.motion.active],
    )
