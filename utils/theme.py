"""品牌主题 — 颜色常量与全局 CSS 注入"""

import streamlit as st

# ═══════════════════════════════════════════
#  品牌色规范
# ═══════════════════════════════════════════
PRIMARY_BLUE = "#0A4A84"
PRIMARY_HOVER = "#083B69"
ACCENT_ORANGE = "#F39A1E"
BG_PAGE = "#F5F7FA"
BG_CARD = "#FFFFFF"
TEXT_PRIMARY = "#1F2937"
TEXT_SECONDARY = "#6B7280"
BORDER_COLOR = "#E5E7EB"
SUCCESS_GREEN = "#16A34A"
WARNING_YELLOW = "#F59E0B"
ERROR_RED = "#DC2626"
INFO_BLUE = "#2563EB"

# 状态标签颜色
STATUS_COLORS = {
    "现行有效": ("#16A34A", "#F0FDF4"),
    "已废止": ("#DC2626", "#FEF2F2"),
    "已失效": ("#6B7280", "#F9FAFB"),
    "被替代": ("#7C3AED", "#F5F3FF"),
    "部分废止": ("#F39A1E", "#FFF7ED"),
    "即将失效": ("#F39A1E", "#FFF7ED"),
    "待核实": ("#F39A1E", "#FFF7ED"),
    "不明": ("#6B7280", "#F9FAFB"),
}

# 风险等级颜色（审查页使用）
RISK_COLORS = {
    "严重问题": ("#DC2626", "#FEF2F2"),
    "高风险": ("#EF4444", "#FEF2F2"),
    "中风险": ("#F39A1E", "#FFF7ED"),
    "低风险": ("#2563EB", "#EFF6FF"),
    "提醒": ("#6B7280", "#F9FAFB"),
    "正常": ("#16A34A", "#F0FDF4"),
}


def inject_global_styles():
    """注入全局 CSS — 统一字体、背景、按钮、卡片、表单等样式"""

    st.markdown(
        f"""
        <style>
        /* ═══════ 基础变量与页面背景 ═══════ */
        .stApp {{
            background-color: {BG_PAGE};
        }}
        .main .block-container {{
            max-width: 1280px;
            padding-top: 2rem;
            padding-bottom: 2rem;
        }}

        /* ═══════ 卡片通用样式 ═══════ */
        .brand-card {{
            background: {BG_CARD};
            border-radius: 14px;
            padding: 24px 28px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
            border: 1px solid {BORDER_COLOR};
        }}

        /* ═══════ 主按钮样式 ═══════ */
        .stButton > button {{
            border-radius: 8px;
            font-weight: 500;
            transition: all 0.15s ease;
        }}
        .stButton > button[kind="primary"] {{
            background-color: {PRIMARY_BLUE};
            border-color: {PRIMARY_BLUE};
            color: white;
        }}
        .stButton > button[kind="primary"]:hover {{
            background-color: {PRIMARY_HOVER};
            border-color: {PRIMARY_HOVER};
            color: white;
        }}
        .stButton > button[kind="secondary"] {{
            background-color: white;
            border: 1px solid {PRIMARY_BLUE};
            color: {PRIMARY_BLUE};
        }}
        .stButton > button[kind="secondary"]:hover {{
            background-color: #F0F5FA;
            border-color: {PRIMARY_HOVER};
            color: {PRIMARY_HOVER};
        }}

        /* ═══════ 输入框 / 下拉框 / 文本域 ═══════ */
        .stTextInput input, .stSelectbox select, .stTextArea textarea,
        .stNumberInput input, .stDateInput input {{
            border-radius: 8px !important;
            border-color: {BORDER_COLOR} !important;
        }}
        .stTextInput input:focus, .stSelectbox select:focus,
        .stTextArea textarea:focus, .stNumberInput input:focus {{
            border-color: {PRIMARY_BLUE} !important;
            box-shadow: 0 0 0 2px rgba(10,74,132,0.1) !important;
        }}

        /* ═══════ Expander 简洁化 ═══════ */
        .streamlit-expanderHeader {{
            border-radius: 10px !important;
            border: 1px solid {BORDER_COLOR} !important;
            background: {BG_CARD} !important;
            font-weight: 500;
        }}
        .streamlit-expanderContent {{
            border: 1px solid {BORDER_COLOR} !important;
            border-top: none !important;
            border-radius: 0 0 10px 10px !important;
            background: {BG_CARD} !important;
        }}

        /* ═══════ Alert 统一圆角 ═══════ */
        .stAlert {{
            border-radius: 10px !important;
            border: none !important;
        }}

        /* ═══════ 表格/DataFrame ═══════ */
        .stDataFrame {{
            border-radius: 10px;
            overflow: hidden;
        }}

        /* ═══════ 隐藏 Streamlit 默认元素 ═══════ */
        header[data-testid="stHeader"] {{
            background: transparent;
        }}
        #MainMenu {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}
        .stApp [data-testid="stDecoration"] {{ display: none; }}

        /* Deploy 按钮 */
        .stDeployButton {{ display: none !important; }}

        /* ═══════ Sidebar ═══════ */
        section[data-testid="stSidebar"] {{
            background-color: #FAFBFC;
            width: 205px !important;
        }}
        section[data-testid="stSidebar"] .stMarkdown {{
            font-size: 12px;
        }}
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
        section[data-testid="stSidebar"] [data-testid="stPageLink"] a,
        section[data-testid="stSidebar"] a {{
            font-size: 12px !important;
            line-height: 1.15 !important;
            padding-top: 4px !important;
            padding-bottom: 4px !important;
        }}
        section[data-testid="stSidebar"] img {{
            image-rendering: auto;
        }}

        /* ═══════ 文件上传区 ═══════ */
        .stFileUploader {{
            border-radius: 12px !important;
            border: 2px dashed {BORDER_COLOR} !important;
            background: #FAFBFC !important;
            padding: 8px !important;
        }}
        .stFileUploader:hover {{
            border-color: {PRIMARY_BLUE} !important;
            background: #F0F5FA !important;
        }}

        /* ═══════ Tabs ═══════ */
        .stTabs [data-baseweb="tab"] {{
            font-weight: 500;
            color: {TEXT_SECONDARY};
        }}
        .stTabs [data-baseweb="tab"][aria-selected="true"] {{
            color: {PRIMARY_BLUE};
        }}

        /* ═══════ Metric 卡片 ═══════ */
        [data-testid="stMetric"] {{
            background: {BG_CARD};
            border-radius: 12px;
            padding: 16px 20px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            border: 1px solid {BORDER_COLOR};
        }}

        /* ═══════ Radio / Checkbox ═══════ */
        .stRadio label, .stCheckbox label {{
            font-weight: 400;
        }}

        /* ═══════ 分割线 ═══════ */
        hr {{
            border-color: {BORDER_COLOR} !important;
            margin: 1.2rem 0 !important;
        }}

        /* ═══════ 页面标题暗纹水印 ═══════ */
        .brand-watermark {{
            position: fixed;
            left: 40px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 120px;
            color: rgba(10, 74, 132, 0.03);
            pointer-events: none;
            z-index: -1;
            font-weight: 900;
            white-space: nowrap;
            user-select: none;
        }}

        /* ═══════ 橙色装饰线 ═══════ */
        .orange-accent {{
            height: 3px;
            width: 60px;
            background: {ACCENT_ORANGE};
            border-radius: 2px;
            margin: 6px 0 18px 0;
        }}


        /* ═══════ 统一页面页头 ═══════ */
        .zd-page-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 24px;
            margin: 4px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 1px solid {BORDER_COLOR};
        }}
        .zd-page-title-wrap {{
            flex: 1 1 auto;
            min-width: 0;
        }}
        .zd-page-title-wrap h2 {{
            margin: 0;
            color: {TEXT_PRIMARY};
            font-weight: 800;
            line-height: 1.25;
        }}
        .zd-page-title-wrap p {{
            color: {TEXT_SECONDARY};
            font-size: 0.9rem;
            margin: 6px 0 0 0;
        }}
        .zd-page-logo {{
            flex: 0 0 auto;
            display: flex;
            align-items: flex-start;
            justify-content: flex-end;
            min-width: 120px;
            padding-top: 2px;
        }}
        .zd-page-logo img {{
            height: 46px !important;
            width: auto !important;
            max-width: 170px !important;
            object-fit: contain !important;
        }}
        .zd-page-header {{
            padding-top: 0 !important;
        }}
        .zd-page-title-wrap h2 {{
            font-size: 1.65rem !important;
        }}

        /* 进一步隐藏右上角 Deploy / 菜单类按钮，不影响本地功能 */
        [data-testid="stDeployButton"],
        [data-testid="stToolbar"] [kind="header"],
        button[title="Deploy"],
        a[title="Deploy"] {{
            display: none !important;
            visibility: hidden !important;
        }}

        </style>
        """,
        unsafe_allow_html=True,
    )
