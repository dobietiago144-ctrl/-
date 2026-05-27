"""文档审查页面 — 上传待审查文档，执行审查，展示结果"""

import os
import streamlit as st
import pandas as pd

import database.db as db
from config import REVIEW_DOCS_DIR
from modules.document_parser import parse_file
from modules.reference_extractor import extract_all_references
from modules.matcher import match_all_references
from modules.reviewer import review_all
from modules.report_generator import generate_review_summary, export_report


st.title("文档审查")

# 初始化 session_state
if "review_extracted_text" not in st.session_state:
    st.session_state["review_extracted_text"] = ""
if "review_file_name" not in st.session_state:
    st.session_state["review_file_name"] = ""
if "review_file_path" not in st.session_state:
    st.session_state["review_file_path"] = ""

# 输入方式选择
input_method = st.radio("选择输入方式", ["上传文件", "粘贴文本"], horizontal=True)

if input_method == "上传文件":
    uploaded_file = st.file_uploader(
        "上传待审查文档（支持 .docx / .pdf / .txt / .xlsx）",
        type=["docx", "pdf", "txt", "xlsx"],
        key="review_file_uploader",
    )
    if uploaded_file:
        file_path = os.path.join(REVIEW_DOCS_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.read())
        try:
            text = parse_file(file_path)
            st.session_state["review_extracted_text"] = text
            st.session_state["review_file_name"] = uploaded_file.name
            st.session_state["review_file_path"] = file_path
        except Exception as e:
            st.error(f"文档解析失败: {e}")

    if st.session_state["review_extracted_text"]:
        st.text_area(
            "解析出的文本（前3000字）",
            st.session_state["review_extracted_text"][:3000],
            height=200, disabled=True, label_visibility="visible",
        )
else:
    pasted = st.text_area(
        "请粘贴待审查文本内容", height=300,
        placeholder="在此粘贴文档全文...",
        key="paste_area",
    )
    if pasted:
        st.session_state["review_extracted_text"] = pasted
        st.session_state["review_file_name"] = "手动粘贴文本"
        st.session_state["review_file_path"] = ""
        st.caption(f"已输入 {len(pasted)} 个字符")

# 审查按钮
st.markdown("---")
col1, col2, col3 = st.columns([1, 1, 6])
with col1:
    start_review = st.button(
        "开始审查", type="primary",
        disabled=not st.session_state["review_extracted_text"],
    )

if start_review and st.session_state["review_extracted_text"]:
    with st.spinner("正在审查中..."):
        text = st.session_state["review_extracted_text"]

        # Step 1: 提取引用依据
        refs = extract_all_references(text)

        if not refs:
            st.warning("未从文档中识别到政策依据引用，请检查文档内容或尝试粘贴文本")
        else:
            # Step 2: 匹配文件库
            matched = match_all_references(refs)

            # Step 3: 审查评估
            results = review_all(matched)

            # Step 4: 保存审查任务
            risk_counts = {"高风险": 0, "中风险": 0, "低风险": 0, "正常": 0, "提醒": 0}
            for r in results:
                rl = r.get("risk_level", "提醒")
                risk_counts[rl] = risk_counts.get(rl, 0) + 1

            task_data = {
                "task_name": f"审查_{st.session_state['review_file_name']}",
                "uploaded_file_name": st.session_state["review_file_name"],
                "uploaded_file_path": st.session_state["review_file_path"],
                "extracted_text": text,
                "extracted_count": len(results),
                "risk_high_count": risk_counts.get("高风险", 0),
                "risk_medium_count": risk_counts.get("中风险", 0),
                "risk_low_count": risk_counts.get("低风险", 0),
                "risk_normal_count": risk_counts.get("正常", 0),
            }
            task_id = db.create_review_task(task_data)

            # Step 5: 保存审查结果
            for r in results:
                r["task_id"] = task_id
                db.create_review_result(r)

            # 存入 session_state 以便页面刷新后仍可查看
            st.session_state["review_task_id"] = task_id
            st.session_state["review_results"] = results

            st.success(f"审查完成！共识别 {len(results)} 项引用依据")

# 展示审查结果（如果 session_state 中有）
if st.session_state.get("review_results"):
    results = st.session_state["review_results"]
    task_id = st.session_state.get("review_task_id")

    # 审查摘要
    st.markdown("---")
    st.subheader("审查摘要")
    summary = generate_review_summary(task_id)
    st.markdown(summary)

    # 详细结果
    st.markdown("---")
    st.subheader("详细审查结果")

    risk_filter = st.multiselect(
        "筛选风险等级",
        ["高风险", "中风险", "低风险", "提醒", "正常"],
        default=["高风险", "中风险"],
    )

    filtered = [r for r in results if r.get("risk_level") in risk_filter]

    if filtered:
        table_data = []
        for i, r in enumerate(filtered, 1):
            risk = r.get("risk_level", "")
            table_data.append({
                "序号": i,
                "原文引用": r.get("original_reference", "")[:80],
                "匹配文件": r.get("matched_title", "未匹配"),
                "文号": r.get("matched_document_no", ""),
                "匹配方式": r.get("match_method", ""),
                "匹配分数": r.get("match_score", ""),
                "文件状态": r.get("document_status", ""),
                "风险等级": risk,
                "判断依据": r.get("judgment_basis", ""),
                "建议替换文件": r.get("suggested_title", ""),
                "修改建议": r.get("suggestion", ""),
                "需人工确认": "是" if r.get("need_manual_confirm") else "否",
            })

        df = pd.DataFrame(table_data)

        def highlight_risk(val):
            if val == "高风险":
                return "background-color: #FF6B6B; color: white"
            elif val == "中风险":
                return "background-color: #FFD93D"
            elif val == "低风险":
                return "background-color: #A8D8EA"
            return ""

        styled = df.style.map(highlight_risk, subset=["风险等级"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # 导出按钮
    st.markdown("---")
    st.subheader("导出审查结果")
    task_id = st.session_state["review_task_id"]
    file_name = st.session_state["review_file_name"]
    excel_bytes = export_report(task_id, "xlsx")
    st.download_button(
        "下载审查结果 Excel",
        data=excel_bytes,
        file_name=f"审查结果_{file_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # 清除按钮
    if st.button("开始新一轮审查"):
        for k in ["review_extracted_text", "review_file_name", "review_file_path",
                   "review_task_id", "review_results"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()
