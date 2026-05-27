"""新旧关系管理页面"""

import streamlit as st
import database.db as db
from config import RELATION_TYPE_OPTIONS, RELATION_CONFIDENCE_OPTIONS
from modules.excel_io import export_relations_to_excel


st.title("新旧关系管理")

tab1, tab2, tab3 = st.tabs(["新增关系", "关系列表", "导出关系"])

# --- Tab1: 新增关系 ---
with tab1:
    all_docs = db.search_documents(limit=500)
    if not all_docs:
        st.warning("文件库为空，请先在「政策文件库」页面导入文件，再建立新旧关系")
    else:
        with st.form("add_relation_form"):
            doc_options = {f"[{d['id']}] 《{d['title']}》" + (f" ({d['document_no']})" if d.get('document_no') else ""): d["id"] for d in all_docs}
            option_labels = list(doc_options.keys())

            col1, col2 = st.columns(2)
            with col1:
                old_label = st.selectbox("旧文件（被替代/废止方）", option_labels, key="old_doc", index=None, placeholder="请选择旧文件...")
            with col2:
                new_label = st.selectbox("新文件（替代/废止方）", option_labels, key="new_doc", index=None, placeholder="请选择新文件...")

            if old_label is None or new_label is None:
                st.info("请分别选择旧文件和新文件")
            elif doc_options[old_label] == doc_options[new_label]:
                st.error("新旧文件不能相同")
            else:
                col_a, col_b = st.columns(2)
                with col_a:
                    relation_type = st.selectbox("关系类型", RELATION_TYPE_OPTIONS)
                    relation_date = st.text_input("关系生效日期 (YYYY-MM-DD)")
                with col_b:
                    confidence = st.selectbox("确认程度", RELATION_CONFIDENCE_OPTIONS)
                    affected_scope = st.text_input("影响范围（如：全文/第X条）")

                relation_basis = st.text_area("关系依据（如废止条款原文）", height=80)
                notes = st.text_area("备注", height=60)

                if st.form_submit_button("确认新增"):
                    data = {
                        "old_document_id": doc_options[old_label],
                        "new_document_id": doc_options[new_label],
                        "relation_type": relation_type,
                        "relation_basis": relation_basis.strip(),
                        "relation_date": relation_date.strip(),
                        "affected_scope": affected_scope.strip(),
                        "confidence": confidence,
                        "notes": notes.strip(),
                    }
                    db.create_relation(data)
                    st.success("新增关系成功")
                    st.rerun()

# --- Tab2: 关系列表 ---
with tab2:
    relations = db.get_all_relations()
    st.caption(f"共 {len(relations)} 条关系记录")

    for rel in relations:
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 1, 3, 1])
            with col1:
                st.markdown(f"《{rel['old_title']}》")
                st.caption(rel.get("old_document_no", ""))
            with col2:
                st.markdown(f"**→ {rel['relation_type']} →**")
            with col3:
                st.markdown(f"《{rel['new_title']}》")
                st.caption(rel.get("new_document_no", ""))
            with col4:
                if st.button("删除", key=f"del_rel_{rel['id']}"):
                    db.delete_relation(rel["id"])
                    st.rerun()
            if rel.get("relation_basis"):
                st.caption(f"依据: {rel['relation_basis']}")
        st.markdown("---")

# --- Tab3: 导出关系 ---
with tab3:
    relations = db.get_all_relations()
    if relations:
        excel_bytes = export_relations_to_excel(relations)
        st.download_button(
            "下载新旧关系表",
            data=excel_bytes,
            file_name="新旧关系表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.success(f"共 {len(relations)} 条关系")
    else:
        st.info("暂无关系记录")
