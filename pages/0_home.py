"""首页 — 系统概览"""

import streamlit as st
import database.db as db

st.title("政策文件依据有效性审查程序")

st.markdown("---")

# 统计数据
stats = db.get_stats()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("文件库总数", stats["total"])
with col2:
    st.metric("现行有效", stats["valid"])
with col3:
    st.metric("已废止/失效", stats["abolished"])
with col4:
    st.metric("待确认", stats["unconfirmed"])
with col5:
    st.metric("审查次数", stats["review_count"])

st.markdown("---")

# 最近审查记录
st.subheader("最近审查记录")
tasks = db.get_all_review_tasks(limit=10)
if tasks:
    for t in tasks:
        col1, col2, col3 = st.columns([3, 2, 2])
        with col1:
            st.write(f"**{t.get('uploaded_file_name', '未命名')}**")
        with col2:
            st.caption(f"识别 {t.get('extracted_count', 0)} 项依据")
        with col3:
            risk_parts = []
            if t.get("risk_high_count"):
                risk_parts.append(f"🔴 {t['risk_high_count']}")
            if t.get("risk_medium_count"):
                risk_parts.append(f"🟡 {t['risk_medium_count']}")
            if t.get("risk_normal_count"):
                risk_parts.append(f"🟢 {t['risk_normal_count']}")
            st.caption(" | ".join(risk_parts) if risk_parts else "暂无风险标记")
        st.caption(t.get("created_at", ""))
        st.markdown("---")
else:
    st.info("暂无审查记录，请先上传待审查文档进行审查")

# 操作指引
with st.expander("操作指引"):
    st.markdown("""
    1. **上传政策文件建库**：在「政策文件库」页面上传政策文件，或通过 Excel 批量导入
    2. **维护文件状态**：确认每个文件的状态（现行有效、已废止等）
    3. **维护传承关系**：在「传承关系」页面建立新旧文件的替代/废止关系
    4. **文档审查**：在「文档审查」页面上传待审查文档，系统自动进行比对
    5. **查看结果**：审查完成后，查看结果并导出 Excel 报告
    """)
