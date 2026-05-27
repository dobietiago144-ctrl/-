"""文件详情页面"""

import streamlit as st
import database.db as db
from config import DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS, REGION_OPTIONS
from modules.metadata_extractor import extract_all_metadata
from modules.document_parser import analyze_document

doc_id = st.session_state.get("view_doc_id", None)
if not doc_id:
    st.warning("请从文件库页面选择要查看的文件")
    st.stop()

doc = db.get_document(doc_id)
if not doc:
    st.error("文件不存在")
    st.stop()

st.title(f"《{doc['title']}》")

# 返回按钮
if st.button("← 返回文件库", key="back_to_library"):
    st.switch_page("pages/1_document_library.py")

# 编辑模式
if "edit_mode" not in st.session_state:
    st.session_state["edit_mode"] = False
if "analyze_result" not in st.session_state:
    st.session_state["analyze_result"] = None

col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 8])
with col_btn1:
    if st.button("编辑" if not st.session_state["edit_mode"] else "取消编辑"):
        st.session_state["edit_mode"] = not st.session_state["edit_mode"]
        st.rerun()
with col_btn2:
    full_text = doc.get("full_text", "")
    analyze_label = "分析提炼要点" if not st.session_state.get("analyze_result") else "重新分析"
    btn_disabled = not (full_text and len(full_text) >= 50)
    if st.button(analyze_label, type="secondary", disabled=btn_disabled):
        with st.spinner("正在分析..."):
            st.session_state["analyze_result"] = analyze_document(full_text)
        st.rerun()
    if btn_disabled:
        st.caption("*需要正文内容（≥50字）")

# 显示分析结果
analysis = st.session_state.get("analyze_result")
if analysis:
    with st.container(border=True):
        st.markdown("### 分析提炼结果")
        st.markdown(f"**摘要**: {analysis['summary']}")

        if analysis.get("scope"):
            st.markdown(f"**适用范围**: {analysis['scope']}")

        if analysis.get("key_points"):
            st.markdown("**关键条款 / 义务性规定**:")
            for i, kp in enumerate(analysis["key_points"], 1):
                st.markdown(f"{i}. {kp}")

        if analysis.get("deadlines"):
            st.markdown("**时限要求**:")
            for i, dl in enumerate(analysis["deadlines"], 1):
                st.markdown(f"{i}. {dl}")

        if st.button("清除分析结果"):
            st.session_state["analyze_result"] = None
            st.rerun()

    st.markdown("---")

if st.session_state["edit_mode"]:
    # --- 编辑表单 ---
    with st.form("edit_document_form"):
        title = st.text_input("文件名称 *", value=doc["title"])
        col_a, col_b = st.columns(2)
        with col_a:
            document_no = st.text_input("文号", value=doc.get("document_no", ""))
            issuing_authority = st.text_input("发文单位", value=doc.get("issuing_authority", ""))
            publish_date = st.text_input("发布日期", value=doc.get("publish_date", ""))
            effective_date = st.text_input("实施日期", value=doc.get("effective_date", ""))
            expiry_date = st.text_input("失效日期", value=doc.get("expiry_date", ""))
        with col_b:
            current_status = doc.get("status", "待核实")
            status_idx = DOC_STATUS_OPTIONS.index(current_status) if current_status in DOC_STATUS_OPTIONS else 0
            status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=status_idx)

            region = st.selectbox(
                "适用地区", REGION_OPTIONS,
                index=REGION_OPTIONS.index(doc.get("region", "全国")) if doc.get("region") in REGION_OPTIONS else 0,
            )
            category = st.selectbox(
                "文件类别", DOC_CATEGORY_OPTIONS,
                index=DOC_CATEGORY_OPTIONS.index(doc.get("category", "其他")) if doc.get("category") in DOC_CATEGORY_OPTIONS else 0,
            )
            source_url = st.text_input("原文链接", value=doc.get("source_url", ""))
        keywords = st.text_input("关键词", value=doc.get("keywords", ""))
        summary = st.text_area("摘要", value=doc.get("summary", ""), height=60)
        full_text = st.text_area("正文全文", value=doc.get("full_text", ""), height=200)
        notes = st.text_area("备注", value=doc.get("notes", ""), height=60)
        confirmed = st.checkbox("已人工确认", value=bool(doc.get("confirmed", 0)))

        if st.form_submit_button("保存修改"):
            data = {
                "title": title.strip(),
                "document_no": document_no.strip() if document_no else "",
                "issuing_authority": issuing_authority.strip() if issuing_authority else "",
                "publish_date": publish_date.strip() if publish_date else "",
                "effective_date": effective_date.strip() if effective_date else "",
                "expiry_date": expiry_date.strip() if expiry_date else "",
                "status": status,
                "region": region,
                "category": category,
                "keywords": keywords.strip() if keywords else "",
                "summary": summary.strip() if summary else "",
                "full_text": full_text.strip() if full_text else "",
                "source_url": source_url.strip() if source_url else "",
                "confirmed": 1 if confirmed else 0,
                "notes": notes.strip() if notes else "",
            }
            db.update_document(doc_id, data)
            st.success("保存成功")
            st.session_state["edit_mode"] = False
            st.rerun()
else:
    # --- 查看模式 ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**文号：** {doc.get('document_no', '未填写')}")
        st.markdown(f"**发文单位：** {doc.get('issuing_authority', '未填写')}")
        st.markdown(f"**发布日期：** {doc.get('publish_date', '未填写')}")
        st.markdown(f"**实施日期：** {doc.get('effective_date', '未填写')}")
        st.markdown(f"**失效日期：** {doc.get('expiry_date', '未填写')}")
    with col2:
        st.markdown(f"**文件状态：** {doc.get('status', '')}")
        st.markdown(f"**适用地区：** {doc.get('region', '未填写')}")
        st.markdown(f"**文件类别：** {doc.get('category', '未填写')}")
        st.markdown(f"**关键词：** {doc.get('keywords', '未填写')}")
        st.markdown(f"**来源类型：** {doc.get('source_type', '')}")
        st.markdown(f"**人工确认：** {'是' if doc.get('confirmed') else '否'}")

    source_url = doc.get("source_url", "")
    if source_url:
        st.markdown(f"**原文链接：** [{source_url}]({source_url})")
    if doc.get("summary"):
        st.caption("**摘要：**")
        st.markdown(doc["summary"])
    if doc.get("notes"):
        st.caption("**备注：**")
        st.markdown(doc["notes"])
    if doc.get("file_path"):
        st.caption(f"附件路径: {doc['file_path']}")

    # 正文
    if doc.get("full_text"):
        with st.expander("文件正文"):
            st.text_area("", doc["full_text"], height=300, disabled=True, label_visibility="collapsed")

    # 传承关系
    st.markdown("---")
    st.subheader("传承关系")
    relations = db.get_relations_for_document(doc_id)

    if relations["downstream"]:
        st.markdown("**本文件被以下文件替代/废止：**")
        for r in relations["downstream"]:
            st.markdown(
                f"- 【{r['relation_type']}】→ 《{r['new_title']}》"
                f"（{r.get('new_document_no', '无文号')}）"
            )
            if r.get("relation_basis"):
                st.caption(f"  依据: {r['relation_basis']}")

    if relations["upstream"]:
        st.markdown("**本文件替代/废止了以下文件：**")
        for r in relations["upstream"]:
            st.markdown(
                f"- 【{r['relation_type']}】← 《{r['old_title']}》"
                f"（{r.get('old_document_no', '无文号')}）"
            )
