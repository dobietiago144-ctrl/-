"""政策文件依据有效性审查程序 — 主入口"""

import streamlit as st

st.set_page_config(
    page_title="政策文件依据有效性审查程序",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 数据库初始化
from database.db import init_db
init_db()

# 定义页面
home_page = st.Page("pages/0_home.py", title="首页", icon="🏠")
library_page = st.Page("pages/1_document_library.py", title="政策文件库", icon="📚")
relations_page = st.Page("pages/3_relations.py", title="传承关系", icon="🔗")
review_page = st.Page("pages/4_review.py", title="文档审查", icon="🔍")
history_page = st.Page("pages/5_review_history.py", title="审查历史", icon="📝")

pg = st.navigation(
    [home_page, library_page, relations_page, review_page, history_page]
)
pg.run()
