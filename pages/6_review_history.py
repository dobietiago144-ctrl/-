"""审查历史页面"""

import streamlit as st
import pandas as pd
import database.db as db
from modules.report_generator import generate_review_summary, export_report

st.title("审查历史")

tasks = db.get_all_review_tasks(limit=50)

if not tasks:
    st.info("暂无审查记录")
    st.stop()

st.caption(f"共 {len(tasks)} 条审查记录")

for t in tasks:
    with st.container():
        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
        with col1:
            st.markdown(f"**{t.get('uploaded_file_name', '未命名')}**")
            st.caption(t.get("created_at", ""))
        with col2:
            st.metric("识别", t.get("extracted_count", 0))
        with col3:
            st.metric("🔴 高风险", t.get("risk_high_count", 0))
        with col4:
            st.metric("🟡 中风险", t.get("risk_medium_count", 0))
        with col5:
            st.metric("🟢 正常", t.get("risk_normal_count", 0))
        # 显示严重问题计数（合并到高风险统计中）
        if t.get("risk_high_count", 0) > 0:
            st.caption(f"含严重/高风险")

        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 8])
        with col_btn1:
            if st.button("查看详情", key=f"detail_{t['id']}"):
                st.session_state["view_task_id"] = t["id"]
                st.rerun()
        with col_btn2:
            if st.button("删除", key=f"del_task_{t['id']}"):
                db.delete_review_task(t["id"])
                st.rerun()

    st.markdown("---")

# 查看任务详情
if "view_task_id" in st.session_state and st.session_state["view_task_id"]:
    task_id = st.session_state["view_task_id"]
    st.markdown("---")
    col_title, col_close = st.columns([10, 1])
    with col_title:
        st.subheader("审查详情")
    with col_close:
        if st.button("✕", key="close_detail", help="关闭详情"):
            del st.session_state["view_task_id"]
            st.rerun()

    summary = generate_review_summary(task_id)
    st.markdown(summary)

    results = db.get_review_results(task_id)
    if results:
        table_data = []
        for i, r in enumerate(results, 1):
            table_data.append({
                "序号": i,
                "原文引用": r.get("original_reference", "")[:80],
                "报告引用文号": r.get("recognized_document_no", ""),
                "匹配文件": r.get("matched_title", "未匹配"),
                "文件库正式文号": r.get("official_document_no", ""),
                "匹配方式": r.get("match_method", ""),
                "匹配分数": r.get("match_score", ""),
                "文件状态": r.get("document_status", ""),
                "风险等级": r.get("risk_level", ""),
                "问题类型": r.get("problem_type", ""),
                "判断依据": r.get("judgment_basis", ""),
                "建议替换文件": r.get("suggested_title", ""),
                "修改建议": r.get("suggestion", ""),
            })
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 导出
        excel_bytes = export_report(task_id, "xlsx")
        st.download_button(
            "下载审查结果",
            data=excel_bytes,
            file_name=f"审查结果_{task_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
