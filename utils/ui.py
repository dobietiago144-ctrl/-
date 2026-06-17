"""公共 UI 组件 — 品牌统一的页面元素"""

import os
import base64
import streamlit as st
from version import APP_VERSION, APP_UPDATE_DATE
from utils.theme import (
    PRIMARY_BLUE, PRIMARY_HOVER, ACCENT_ORANGE,
    BG_PAGE, BG_CARD, TEXT_PRIMARY, TEXT_SECONDARY,
    BORDER_COLOR, SUCCESS_GREEN, WARNING_YELLOW, ERROR_RED,
    STATUS_COLORS, RISK_COLORS,
)


# ═══════════════════════════════════════════
#  Logo 文件路径与 base64 编码
# ═══════════════════════════════════════════

def _get_assets_dir() -> str:
    """获取 assets 目录绝对路径"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _image_to_base64(filepath: str) -> str:
    """将图片文件编码为 base64 data URI"""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}
        mime = mime_map.get(ext, "image/png")
        with open(filepath, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{data}"
    except Exception:
        return ""


# ═══════════════════════════════════════════
#  各场景 Logo 候选列表
# ═══════════════════════════════════════════

# 首页 Hero 区（深蓝背景）— 横版反白
HERO_LOGO_CANDIDATES = [
    "2023中地顾问横版logo反白.png",
    "2023中地顾问横版logo无定位语反白.png",
]

# 普通页面右上角（浅色背景）— 横版彩色
PAGE_LOGO_CANDIDATES = [
    "2023中地顾问横版logo.png",
    "2023中地顾问横版logo无定位语.png",
]

# 侧边栏 — 竖版彩色
SIDEBAR_LOGO_CANDIDATES = [
    "2023中地顾问竖版logo.png",
    "2023中地顾问竖版logo无定位语.png",
]


def _pick_logo_path(candidates: list) -> str:
    """从候选列表中选出第一个存在的 logo 绝对路径，都不存在则返回空"""
    assets_dir = _get_assets_dir()
    for name in candidates:
        full = os.path.join(assets_dir, name)
        if os.path.isfile(full):
            return full
    return ""


def _logo_img_tag(filepath: str, width: int) -> str:
    """生成 base64 内嵌的 img 标签"""
    b64 = _image_to_base64(filepath)
    if b64:
        return (
            f'<img src="{b64}" alt="中地顾问" '
            f'style="width:{width}px;height:auto;object-fit:contain;">'
        )
    return ""


# ═══════════════════════════════════════════
#  各场景 Logo HTML
# ═══════════════════════════════════════════

def get_hero_logo_html(width: int = 210) -> str:
    """首页 Hero 区反白横版 logo（base64 内嵌）"""
    path = _pick_logo_path(HERO_LOGO_CANDIDATES)
    if path:
        tag = _logo_img_tag(path, width)
        if tag:
            return tag
    # fallback
    return (
        f'<span style="font-size:1.5rem;font-weight:700;color:#FFFFFF;'
        f'letter-spacing:3px;font-family:\'Microsoft YaHei\',sans-serif;">'
        f'中地顾问</span>'
    )


def get_page_logo_html(width: int = 160) -> str:
    """普通页面右上角横版彩色 logo（base64 内嵌）"""
    path = _pick_logo_path(PAGE_LOGO_CANDIDATES)
    if path:
        tag = _logo_img_tag(path, width)
        if tag:
            return tag
    return (
        f'<span style="font-size:1rem;font-weight:700;color:{PRIMARY_BLUE};'
        f'letter-spacing:2px;font-family:\'Microsoft YaHei\',sans-serif;">'
        f'中地顾问</span>'
    )


def get_sidebar_logo_html(width: int = 130) -> str:
    """侧边栏竖版彩色 logo（base64 内嵌）"""
    path = _pick_logo_path(SIDEBAR_LOGO_CANDIDATES)
    if path:
        tag = _logo_img_tag(path, width)
        if tag:
            return tag
    return (
        f'<span style="font-size:0.95rem;font-weight:700;color:{PRIMARY_BLUE};'
        f'letter-spacing:2px;font-family:\'Microsoft YaHei\',sans-serif;">'
        f'🏛 中地顾问</span>'
    )


def get_footer_logo_html(width: int = 150) -> str:
    """页脚深蓝区反白横版 logo"""
    return get_hero_logo_html(width)


# ═══════════════════════════════════════════
#  兼容旧接口
# ═══════════════════════════════════════════

def get_logo_html(height: int = 48, white_version: bool = False) -> str:
    """[已废弃] 保留旧接口兼容"""
    if white_version:
        return get_hero_logo_html(160)
    return get_page_logo_html(140)


# ═══════════════════════════════════════════
#  统一页面头部
# ═══════════════════════════════════════════

def render_app_header(title: str, subtitle: str = None, show_logo: bool = True):
    """每页统一顶部页头：左标题 + 右 logo + 橙色装饰线"""
    logo_html = get_page_logo_html(160)

    st.markdown(
        f"""
        <div style="display:flex;align-items:flex-start;justify-content:space-between;
        gap:16px;margin-bottom:12px;">
            <div style="flex:1;min-width:0;">
                <h2 style="margin:0;color:{TEXT_PRIMARY};font-weight:700;font-size:1.35rem;">
                    {title}
                </h2>
                {f'<p style="color:{TEXT_SECONDARY};font-size:0.82rem;margin:3px 0 0 0;">{subtitle}</p>' if subtitle else ''}
                <div class="orange-accent" style="margin-top:4px;"></div>
            </div>
            <div style="flex-shrink:0;padding-top:2px;">
                {logo_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
#  首页 Hero 品牌区
# ═══════════════════════════════════════════

def render_home_hero():
    """首页顶部品牌区：深蓝渐变 + 反白透明底 logo（base64 内嵌）"""
    logo_html = get_hero_logo_html(210)

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {PRIMARY_BLUE} 0%, {PRIMARY_HOVER} 100%);
            border-radius: 16px;
            padding: 32px 36px;
            margin-bottom: 28px;
            position: relative;
            overflow: hidden;
        ">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:20px;">
                <div style="flex:1;min-width:0;">
                    <h1 style="color:#FFFFFF;font-size:1.7rem;font-weight:700;margin:0;line-height:1.3;">
                        政策文件依据有效性审查程序
                    </h1>
                    <p style="color:rgba(255,255,255,0.8);font-size:0.9rem;margin:6px 0 14px 0;">
                        政策文件录入、有效性审查、替代文件管理一体化工具
                    </p>
                    <div style="height:3px;width:60px;background:{ACCENT_ORANGE};border-radius:2px;margin-bottom:12px;"></div>
                    <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;">
                        <span style="color:rgba(255,255,255,0.85);font-size:0.8rem;
                            background:rgba(255,255,255,0.12);padding:3px 12px;border-radius:16px;">
                            {APP_VERSION}
                        </span>
                        <span style="color:rgba(255,255,255,0.6);font-size:0.75rem;">
                            更新日期：{APP_UPDATE_DATE}
                        </span>
                    </div>
                </div>
                <div style="flex-shrink:0;">
                    {logo_html}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
#  首页功能入口卡片
# ═══════════════════════════════════════════

def render_feature_card(title: str, desc: str, icon: str, target_page: str = None):
    """首页功能入口卡片"""
    st.markdown(
        f"""
        <div style="
            background:{BG_CARD};
            border-radius:14px;
            padding:26px 24px;
            box-shadow:0 1px 3px rgba(0,0,0,0.06),0 1px 2px rgba(0,0,0,0.04);
            border:1px solid {BORDER_COLOR};
            height:100%;
        ">
            <div style="font-size:2rem;margin-bottom:10px;">{icon}</div>
            <h4 style="color:{TEXT_PRIMARY};font-weight:700;margin:0 0 6px 0;">{title}</h4>
            <p style="color:{TEXT_SECONDARY};font-size:0.85rem;margin:0;line-height:1.5;">{desc}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
#  首页数据概览小卡片
# ═══════════════════════════════════════════

def render_metric_card(label: str, value, desc: str = None):
    """首页数据概览小卡片"""
    display_val = str(value) if value is not None else "--"
    st.markdown(
        f"""
        <div style="
            background:{BG_CARD};
            border-radius:12px;
            padding:20px 18px;
            text-align:center;
            box-shadow:0 1px 2px rgba(0,0,0,0.04);
            border:1px solid {BORDER_COLOR};
            height:100%;
        ">
            <div style="font-size:1.8rem;font-weight:700;color:{PRIMARY_BLUE};line-height:1.2;">
                {display_val}
            </div>
            <div style="color:{TEXT_SECONDARY};font-size:0.82rem;margin-top:4px;">{label}</div>
            {f'<div style="color:{TEXT_SECONDARY};font-size:0.72rem;">{desc}</div>' if desc else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
#  统一提示样式
# ═══════════════════════════════════════════

def render_notice(notice_type: str, title: str, body: str = None):
    """统一提示组件  notice_type: 'success' | 'warning' | 'error' | 'info'"""
    colors = {
        "success": (SUCCESS_GREEN, "#F0FDF4", "✅"),
        "warning": (WARNING_YELLOW, "#FFF7ED", "⚠️"),
        "error": (ERROR_RED, "#FEF2F2", "❌"),
        "info": (PRIMARY_BLUE, "#EFF6FF", "ℹ️"),
    }
    border, bg, icon = colors.get(notice_type, colors["info"])
    body_html = f'<p style="margin:6px 0 0 0;color:{TEXT_SECONDARY};font-size:0.88rem;">{body}</p>' if body else ""
    st.markdown(
        f"""
        <div style="
            border-left:4px solid {border};
            background:{bg};
            border-radius:8px;
            padding:14px 18px;
            margin-bottom:16px;
        ">
            <strong style="color:{TEXT_PRIMARY};">{icon} {title}</strong>
            {body_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
#  统一页脚品牌条
# ═══════════════════════════════════════════

def render_footer():
    """页脚品牌条 — 深蓝底 + 企业愿景 + logo"""
    logo_html = get_footer_logo_html(150)
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {PRIMARY_BLUE} 0%, {PRIMARY_HOVER} 100%);
            border-radius:14px;
            padding:22px 28px;
            margin-top:36px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            flex-wrap:wrap;
            gap:14px;
        ">
            <div style="flex:1;min-width:180px;">
                <p style="color:rgba(255,255,255,0.9);font-size:0.82rem;margin:0;line-height:1.6;">
                    成为中国自然资源咨询服务的行业标杆<br>
                    成为受人尊敬的百年幸福品牌企业
                </p>
            </div>
            <div style="display:flex;align-items:center;gap:14px;">
                <span style="color:rgba(255,255,255,0.55);font-size:0.72rem;">{APP_VERSION}</span>
                {logo_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
#  状态/风险标签
# ═══════════════════════════════════════════

def render_status_tag(status: str):
    """渲染带颜色的文件状态标签"""
    color, bg = STATUS_COLORS.get(status, ("#6B7280", "#F9FAFB"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{color};'
        f'padding:2px 10px;border-radius:12px;font-size:0.78rem;font-weight:500;'
        f'border:1px solid {color}20;">{status}</span>'
    )


def render_risk_tag(risk_level: str):
    """渲染带颜色的风险等级标签"""
    color, bg = RISK_COLORS.get(risk_level, ("#6B7280", "#F9FAFB"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{color};'
        f'padding:2px 10px;border-radius:12px;font-size:0.78rem;font-weight:600;'
        f'border:1px solid {color}30;">{risk_level}</span>'
    )


# ═══════════════════════════════════════════
#  审查流程步骤条
# ═══════════════════════════════════════════

def render_process_steps(current_step: int = 0):
    """审查页面流程步骤条  current_step: 0=上传, 1=识别, 2=匹配, 3=输出"""
    steps = [
        ("上传待审查文档", "📤"),
        ("识别引用依据", "🔍"),
        ("匹配政策文件库", "🔗"),
        ("输出审查结果", "📋"),
    ]
    parts = ['<div style="display:flex;align-items:flex-start;gap:0;margin:16px 0 24px 0;">']
    for i, (label, icon) in enumerate(steps):
        active = i <= current_step
        cur = i == current_step
        bg = PRIMARY_BLUE if active else "#E5E7EB"
        icon_bg = ACCENT_ORANGE if cur else ("rgba(255,255,255,0.3)" if active else "#D1D5DB")
        parts.append(f"""
        <div style="flex:1;text-align:center;position:relative;">
            <div style="width:36px;height:36px;border-radius:50%;background:{icon_bg};
                display:inline-flex;align-items:center;justify-content:center;font-size:1rem;
                margin-bottom:6px;">{icon}</div>
            <div style="height:3px;background:{bg};border-radius:2px;
                position:absolute;top:18px;left:50%;right:-50%;z-index:-1;"></div>
            <div style="font-size:0.72rem;color:{TEXT_PRIMARY if active else TEXT_SECONDARY};
                font-weight:{'600' if active else '400'};">{label}</div>
        </div>""")
    parts.append('</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


# ═══════════════════════════════════════════
#  卡片容器
# ═══════════════════════════════════════════

def card_container():
    """返回一个卡片风格的容器上下文管理器"""
    return st.container(border=True)


def card_header(title: str, description: str = None):
    """在卡片内渲染标题"""
    st.markdown(
        f'<h4 style="color:{TEXT_PRIMARY};margin-bottom:4px;">{title}</h4>',
        unsafe_allow_html=True,
    )
    if description:
        st.markdown(
            f'<p style="color:{TEXT_SECONDARY};font-size:0.82rem;margin-top:0;">{description}</p>',
            unsafe_allow_html=True,
        )
