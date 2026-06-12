"""政策文件依据有效性审查程序 — 主入口"""

import os
import streamlit as st

st.set_page_config(
    page_title="政策文件依据有效性审查程序",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════ 防浏览器自动翻译 ═══════════
# Chrome 自动翻译会把"编码有效"误译为"现行有效"等，导致状态误判
st.markdown(
    '''<meta name="google" content="notranslate">
    <html lang="zh-CN" class="notranslate">
    <style>
      body { translate: no; }
      .notranslate { translate: no; }
    </style>''',
    unsafe_allow_html=True,
)

# 侧边栏 Logo
logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
if os.path.isfile(logo_path):
    st.sidebar.image(logo_path, use_container_width=True)

# 数据库初始化
from database.db import init_db, migrate_database, clean_document_statuses
init_db()
migrate_database()
# 启动时自动清理一次历史非标准状态（编码有效、待验证、不明白等）
clean_document_statuses()

# 运行模式检测
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
    # 尝试自动检测：如果 server.address 是 0.0.0.0 则为局域网模式
    st.session_state["run_mode"] = "unknown"
    st.session_state["run_mode_label"] = "未知（直接运行 streamlit run）"

# 定义页面
home_page = st.Page("pages/0_home.py", title="首页", icon="🏠")
query_page = st.Page("pages/1_document_query.py", title="政策文件查询", icon="🔍")
import_page = st.Page("pages/2_document_import.py", title="政策文件录入", icon="📤")
relations_page = st.Page("pages/4_relations.py", title="新旧关系", icon="🔗")
review_page = st.Page("pages/5_review.py", title="文档审查", icon="📋")
history_page = st.Page("pages/6_review_history.py", title="审查历史", icon="📝")
monitor_page = st.Page("pages/7_policy_monitor.py", title="政策废止监测", icon="🚫")

pg = st.navigation(
    [home_page, query_page, import_page, relations_page, review_page, history_page, monitor_page]
)
pg.run()
