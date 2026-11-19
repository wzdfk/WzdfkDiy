"""UIDiy · 风格 Tokens Schema（唯一事实来源）

所有产物（base.css / style.css / STYLE_PROMPT.md / 预览）都从这份 tokens 派生。
维度有限且可枚举 —— 这是风格词典（dict_style）能做定向 diff 的前提。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# ---------- meta ----------
class Meta(BaseModel):
    name: str = "未命名风格"
    version: str = "1.0"
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""


# ---------- 色彩 ----------
class AccentScale(BaseModel):
    """主色 8 级色阶。500 为主色。"""
    s50: str = "#f2f8fb"
    s100: str = "#e1eff6"
    s200: str = "#c3dfec"
    s300: str = "#9cc9df"
    s400: str = "#6aadd0"
    s500: str = "#4a92bd"
    s600: str = "#3a789c"
    s700: str = "#2f5f7d"


class InkScale(BaseModel):
    """墨色阶：文字与描边。"""
    ink900: str = "#23282f"
    ink600: str = "#56606a"
    ink400: str = "#98a2ad"


class StatusColors(BaseModel):
    ok: str = "#4faf78"
    warn: str = "#dfa03c"
    danger: str = "#d96060"
    info: str = "#8a7fd6"


class ColorTokens(BaseModel):
    accent: AccentScale = AccentScale()
    ink: InkScale = InkScale()
    paper: str = "#f5f4ee"      # 页面底色
    surface: str = "#ffffff"    # 卡片面
    shadow: str | None = None   # 投影色；None = 按墨色+主色自动混合
    status: StatusColors = StatusColors()


# ---------- 形状 ----------
class Radius(BaseModel):
    """四角圆角，支持 "16px 16px 16px 3px"（三圆一利）或 "16px"（全圆）。"""
    lg: str = "16px 16px 16px 3px"   # 卡片 / 浮层
    md: str = "12px 12px 12px 3px"   # 下拉 / 中型容器
    sm: str = "8px 8px 8px 2px"      # 按钮 / 输入框 / 标签


class ShapeTokens(BaseModel):
    strategy: Literal["fold", "uniform", "asymmetric"] = "fold"
    radius: Radius = Radius()


# ---------- 线 ----------
class LineTokens(BaseModel):
    border_width: float = 1.5
    border_style: Literal["solid", "dashed"] = "solid"
    focus_style: Literal["dashed", "solid", "glow"] = "dashed"


# ---------- 投影 ----------
class ElevationTokens(BaseModel):
    type: Literal["offset-solid", "soft-blur", "layered"] = "offset-solid"
    levels: dict[str, str] = Field(
        default_factory=lambda: {
            "e1": "3px 3px 0 var(--s-shadow)",
            "e2": "5px 5px 0 var(--s-shadow)",
            "e3": "8px 8px 0 var(--s-shadow)",
        }
    )
    shadow_color: str | None = None  # None = css_gen 按类型推导


# ---------- 动效 ----------
class MotionTokens(BaseModel):
    duration: int = 180            # ms，标准交互
    duration_slow: int = 320       # ms，强调交互（链接下划线等）
    easing_pop: str = "cubic-bezier(.34, 1.56, .64, 1)"   # 回弹（签名节奏）
    easing_out: str = "cubic-bezier(.22, .61, .36, 1)"    # 舒出
    hover: Literal["lift", "press", "tilt", "none"] = "lift"
    active: Literal["press", "none"] = "press"


# ---------- 字体 ----------
class TypeTokens(BaseModel):
    font_stack: str = '"PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif'
    display_size: str = "28px"
    display_weight: int = 800
    display_tracking: str = "-.02em"
    title_size: str = "18px"
    title_weight: int = 700
    body_size: str = "14px"
    body_line_height: float = 1.65
    label_size: str = "11px"
    label_weight: int = 600
    label_tracking: str = ".14em"


# ---------- 间距 ----------
class SpacingTokens(BaseModel):
    unit: int = 4   # 4pt 网格
    steps: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 6, 8, 12])


# ---------- 组件盒模型（详情面板可调项，全部字段化 → 产物可追溯） ----------
class ControlBox(BaseModel):
    """单个控件的盒模型字段。所有值都进 style.json 与生成的 CSS（带 @token 注释）。"""
    padding_x: str = "16px"
    padding_y: str = "10px"
    font_size: str = ""            # 空 = 跟随 body_size
    font_weight: int = 600
    radius_ref: Literal["sm", "md", "lg"] = "sm"       # 引用形状档位
    shadow_ref: Literal["none", "e1", "e2", "e3"] = "e1"  # 引用投影档位
    custom_shadow: str | None = None   # 完整 box-shadow 覆盖（优先于 shadow_ref）
    margin_bottom: str = "0px"


class ComponentTokens(BaseModel):
    """五组件 + 菜单的盒模型字段 —— 未来控件详情面板直接读写这里。"""
    button: ControlBox = ControlBox(padding_x="22px", padding_y="10px", font_weight=600, shadow_ref="e1")
    card: ControlBox = ControlBox(padding_x="20px", padding_y="20px", font_size="", font_weight=700,
                                  radius_ref="lg", shadow_ref="e2")
    input: ControlBox = ControlBox(padding_x="14px", padding_y="10px", font_weight=400,
                                   shadow_ref="none")
    badge: ControlBox = ControlBox(padding_x="12px", padding_y="3px", font_size="12px",
                                   shadow_ref="none", custom_shadow="2px 2px 0 var(--{p}-shadow)")
    toast: ControlBox = ControlBox(padding_x="16px", padding_y="12px", font_size="13px", font_weight=400,
                                   radius_ref="md", shadow_ref="e2")
    menu: ControlBox = ControlBox(padding_x="6px", padding_y="6px", font_weight=400,
                                  radius_ref="md", shadow_ref="e2")


class ClassPrefix:
    """CSS 类名前缀，默认 fd（FOLD）。"""
    value: str = "fd"


class StyleTokens(BaseModel):
    """风格档案根对象 —— 导出 style.json 的内容。"""
    schemaVersion: str = "1.0"
    prefix: str = "fd"
    meta: Meta = Meta()
    color: ColorTokens = ColorTokens()
    shape: ShapeTokens = ShapeTokens()
    line: LineTokens = LineTokens()
    elevation: ElevationTokens = ElevationTokens()
    motion: MotionTokens = MotionTokens()
    type: TypeTokens = TypeTokens()
    spacing: SpacingTokens = SpacingTokens()
    components: ComponentTokens = ComponentTokens()


# ---------- 系统默认风格（原 FOLD 折角设计系统 v1.0，作验收基准） ----------
def fold_default() -> StyleTokens:
    """系统默认风格 —— 与 fold-design-system.css 等同的 tokens。"""
    return StyleTokens(
        meta=Meta(
            name="系统默认风格",
            version="1.0",
            note="签名规则：折角圆角(三圆一利) · 偏移实心投影 · 硬边细线+虚线焦点环 · 180ms 回弹动效 · 暖纸色底",
        ),
        color=ColorTokens(
            accent=AccentScale(
                s50="#f2f8fb", s100="#e1eff6", s200="#c3dfec", s300="#9cc9df",
                s400="#6aadd0", s500="#4a92bd", s600="#3a789c", s700="#2f5f7d",
            ),
            ink=InkScale(ink900="#23282f", ink600="#56606a", ink400="#98a2ad"),
            paper="#f5f4ee",
            surface="#ffffff",
            shadow=None,   # 自动混合：ink 88% + accent 12%
            status=StatusColors(ok="#4faf78", warn="#dfa03c", danger="#d96060", info="#8a7fd6"),
        ),
        shape=ShapeTokens(strategy="fold"),
        line=LineTokens(border_width=1.5, border_style="solid", focus_style="dashed"),
        elevation=ElevationTokens(type="offset-solid"),
        motion=MotionTokens(duration=180, duration_slow=320, hover="lift", active="press"),
    )


# ---------- 空模板：无签名风格，朴素浏览器/naive-ui 基线 ----------
def blank_default() -> StyleTokens:
    """零装饰基线：无圆角、无投影、中性灰、实线焦点、无 hover/active 位移。"""
    neutral = AccentScale(
        s50="#f9fafb", s100="#f3f4f6", s200="#e5e7eb", s300="#d1d5db",
        s400="#9ca3af", s500="#6b7280", s600="#4b5563", s700="#374151",
    )
    plain_box = dict(font_weight=400, shadow_ref="none",
                     custom_shadow=None, margin_bottom="0px")
    return StyleTokens(
        meta=Meta(
            name="空模板",
            version="1.0",
            note="零装饰基线：无圆角/无投影/中性灰/实线焦点，适合从这里打造个人风格。",
        ),
        color=ColorTokens(
            accent=neutral,
            ink=InkScale(ink900="#111827", ink600="#4b5563", ink400="#9ca3af"),
            paper="#ffffff",
            surface="#ffffff",
            shadow=None,
        ),
        shape=ShapeTokens(
            strategy="uniform",
            radius=Radius(lg="0px", md="0px", sm="0px"),
        ),
        line=LineTokens(border_width=1, border_style="solid", focus_style="solid"),
        elevation=ElevationTokens(
            type="soft-blur",
            levels={"e1": "none", "e2": "none", "e3": "none"},
        ),
        motion=MotionTokens(
            duration=100,
            duration_slow=100,
            easing_pop="linear",
            easing_out="linear",
            hover="none",
            active="none",
        ),
        type=TypeTokens(
            font_stack='system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
            display_size="24px",
            display_weight=600,
            display_tracking="0",
            title_size="16px",
            title_weight=600,
            body_size="14px",
            body_line_height=1.5,
            label_size="12px",
            label_weight=400,
            label_tracking="0",
        ),
        components=ComponentTokens(
            button=ControlBox(padding_x="16px", padding_y="8px", font_size="", **plain_box),    # type: ignore
            card=ControlBox(padding_x="16px", padding_y="16px", font_size="", radius_ref="lg", **plain_box), # type: ignore
            input=ControlBox(padding_x="12px", padding_y="8px", font_size="", **plain_box), # type: ignore
            badge=ControlBox(padding_x="8px", padding_y="2px", font_size="12px", **plain_box), # type: ignore
            toast=ControlBox(padding_x="12px", padding_y="8px", font_size="13px", **plain_box), # type: ignore
            menu=ControlBox(padding_x="4px", padding_y="4px", font_size="", **plain_box), # type: ignore
        ),
    )
