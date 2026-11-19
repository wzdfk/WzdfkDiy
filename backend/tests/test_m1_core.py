"""M1 验收测试：FOLD tokens → 三件套产物。

跑法（backend/ 目录下，conda activate diy 后）：
    python -m pytest tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import dict_style, llm
from app.core.css_gen import render_base_css, render_combined_css, render_style_css
from app.core.prompt_gen import render_style_prompt
from app.core.tokens import fold_default


def test_fold_base_css_tokens():
    css = render_base_css(fold_default())
    assert "--fd-accent-500: #4a92bd" in css
    assert "#f5f4ee" in css and "--fd-paper:" in css
    assert "16px 16px 16px 3px" in css                    # 折角签名
    assert "--fd-e1: 3px 3px 0 var(--fd-shadow)" in css   # 实心投影签名
    assert "--fd-dur:      180ms" in css
    assert "color-mix(in srgb, #23282f 88%, #4a92bd)" in css  # 投影色推导
    assert "@token color.paper" in css                    # 溯源注释


def test_fold_style_css_components():
    css = render_style_css(fold_default())
    for cls in [".fd-btn", ".fd-card", ".fd-input", ".fd-badge", ".fd-toast", ".fd-menu", ".fd-link"]:
        assert cls in css
    assert "2px dashed var(--fd-accent-500)" in css      # 虚线焦点环签名
    assert "translate(-2px, -2px)" in css                # hover 抬起签名
    assert "@keyframes fd-toast-in" in css
    assert "@token components.button" in css             # 组件盒模型溯源
    assert "padding: 10px 22px" in css                   # button padding 字段化


def test_components_traceable():
    """组件盒模型全部字段化：改字段 → 产物跟着变，可追溯。"""
    t = fold_default()
    t.components.button.padding_x = "30px"
    t.components.card.shadow_ref = "e3"
    t.components.badge.custom_shadow = None
    css = render_style_css(t)
    assert "padding: 10px 30px" in css                   # button.padding_x 生效
    assert ".fd-card {" in css
    card_block = css.split(".fd-card {")[1].split("}")[0]
    assert "var(--fd-e3)" in card_block                  # card.shadow_ref 生效
    badge_block = css.split(".fd-badge {")[1].split("}")[0]
    assert "box-shadow: none" in badge_block             # custom_shadow=None → 走 shadow_ref


def test_fold_prompt_md():
    md = render_style_prompt(fold_default())
    assert "折角设计系统" in md
    assert "折角圆角" in md
    assert "偏移实心投影" in md
    assert "如何扩展新组件" in md
    assert "禁止写死色值" in md


def test_dict_softer():
    tokens, diff, reply = dict_style.apply_message(fold_default(), "再柔和一点")
    assert tokens.elevation.type == "soft-blur"
    assert tokens.line.border_width == 1.0
    assert any(d["path"] == "elevation.type" for d in diff)
    assert "柔和" in reply


def test_dict_sharper_then_calmer():
    tokens, diff1, _ = dict_style.apply_message(fold_default(), "硬朗一些")
    assert tokens.elevation.type == "offset-solid"
    assert tokens.line.border_width == 2.0

    tokens2, diff2, _ = dict_style.apply_message(tokens, "俏皮一点")
    assert tokens2.motion.hover == "tilt"

    tokens3, diff3, _ = dict_style.apply_message(tokens2, "从容一点")
    assert tokens3.motion.hover == "lift"
    assert tokens3.motion.duration == 240


def test_dict_no_match():
    _, diff, reply = dict_style.apply_message(fold_default(), "你好呀")
    assert diff == []
    assert "试试这些说法" in reply


def test_llm_parse_prompt(monkeypatch):
    """stub 兜底路径测试：强制禁用 LLM（不依赖外部服务）。"""
    monkeypatch.setattr(llm, "enabled", lambda: False)
    tokens = llm.parse_prompt("一个天青色 #3aa0c8 主题的柔和风格 UI")
    assert tokens.color.accent.s500 == "#3aa0c8"
    assert tokens.elevation.type == "soft-blur"


def test_llm_scale_derivation():
    """主色 → 整套色阶自动推导：单调、同色系。"""
    scale = llm._derive_scale("#b76e79")
    assert scale["s500"] == "#b76e79"
    assert scale["s50"] != scale["s500"] and scale["s700"] != scale["s500"]
    # 由浅到深：亮度递减
    lums = [int(c[1:3], 16) + int(c[3:5], 16) + int(c[5:7], 16) for c in scale.values()]
    assert lums == sorted(lums, reverse=True)


def test_combined_css_nonempty():
    css = render_combined_css(fold_default())
    assert ":root" in css and ".fd-btn" in css
