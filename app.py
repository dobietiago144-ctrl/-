"""政策文件依据有效性审查程序 — 主入口（v7.0.3 界面修复）"""

import os
import streamlit as st
from version import APP_VERSION, APP_UPDATE_DATE
from config import ASSETS_DIR

st.set_page_config(
    page_title="政策文件依据有效性审查程序",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════ 全局品牌样式注入 ═══════════
from utils.theme import inject_global_styles
inject_global_styles()

# ═══════════ 防浏览器自动翻译 ═══════════
st.markdown(
    '''<meta name="google" content="notranslate">
    <html lang="zh-CN" class="notranslate">
    <style>
      body { translate: no; }
      .notranslate { translate: no; }
    </style>''',
    unsafe_allow_html=True,
)

# ═══════════ 侧边栏优化 ═══════════
from utils.ui import get_sidebar_logo_html

# 侧边栏顶部 — 品牌标识（竖版彩色 logo）
sidebar_logo_html = get_sidebar_logo_html(130)
st.sidebar.markdown(
    f'<div style="padding:6px 8px 2px 8px;text-align:center;">{sidebar_logo_html}</div>',
    unsafe_allow_html=True,
)

st.sidebar.markdown(
    '<div style="height:2px;background:linear-gradient(90deg,#0A4A84,#F39A1E);'
    'border-radius:1px;margin:4px 8px 12px 8px;"></div>',
    unsafe_allow_html=True,
)

# ═══════════ 运行模式检测 ═══════════
_run_mode = os.environ.get("POLICY_REVIEWER_MODE", "")
if _run_mode == "lan":
    st.session_state["run_mode"] = "lan"
    st.session_state["run_mode_label"] = "局域网共享模式"
    _lan_ips_raw = os.environ.get("POLICY_REVIEWER_LAN_IPS", "")
    st.session_state["lan_ips"] = [ip.strip() for ip in _lan_ips_raw.split(",") if ip.strip()]
elif _run_mode == "local":
    st.session_state["run_mode"] = "local"
    st.session_state["run_mode_label"] = "单机模式"
else:
    st.session_state["run_mode"] = "unknown"
    st.session_state["run_mode_label"] = "未知（直接运行 streamlit run）"

# ═══════════ 数据库初始化 ═══════════
from database.db import init_db, migrate_database, clean_document_statuses
init_db()
migrate_database()
clean_document_statuses()

# ═══════════ 页面导航定义 ═══════════
home_page = st.Page("pages/0_home.py", title="首页", icon="🏠")
query_page = st.Page("pages/1_document_query.py", title="政策文件查询", icon="🔍")
import_page = st.Page("pages/2_document_import.py", title="政策文件录入", icon="📤")
relations_page = st.Page("pages/4_relations.py", title="新旧关系", icon="🔗")
review_page = st.Page("pages/5_review.py", title="文档审查", icon="📋")
history_page = st.Page("pages/6_review_history.py", title="审查历史", icon="📝")
monitor_page = st.Page("pages/7_policy_monitor.py", title="废止/失效依据库", icon="📚")

pg = st.navigation([
    home_page, query_page, import_page, relations_page, review_page, history_page, monitor_page
])

# ═══════════ 侧边栏底部 — 版本信息 ═══════════
st.sidebar.markdown("---")
st.sidebar.markdown(
    f'<div style="padding:4px 8px;font-size:0.75rem;color:#6B7280;">'
    f'当前版本：<b style="color:#0A4A84;">{APP_VERSION}</b><br>'
    f'更新日期：{APP_UPDATE_DATE}</div>',
    unsafe_allow_html=True,
)

pg.run()
