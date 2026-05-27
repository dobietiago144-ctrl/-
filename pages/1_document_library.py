"""政策文件库管理页面"""

import os
import tempfile

import streamlit as st

import database.db as db
from config import (
    DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS,
    REGION_OPTIONS, SOURCE_TYPE_OPTIONS, UPLOADS_DIR,
)
from modules.document_parser import parse_file, get_supported_types, fetch_from_url, analyze_document
from modules.metadata_extractor import extract_all_metadata, classify_document
from modules.excel_io import (
    generate_import_template, parse_import_excel,
    export_documents_to_excel,
)
from modules.web_search import search_policy_online

# ═══════════ 内联详情视图 ═══════════
view_doc_id = st.session_state.get("view_doc_id", None)
if view_doc_id:
    doc = db.get_document(view_doc_id)
    if not doc:
        st.error("文件不存在")
        if st.button("返回列表"):
            del st.session_state["view_doc_id"]
            st.rerun()
        st.stop()

    if st.button("← 返回文件列表", key="back_to_list"):
        del st.session_state["view_doc_id"]
        st.session_state.pop("analyze_result", None)
        st.rerun()

    st.title(f"《{doc['title']}》")

    # 编辑模式
    if "edit_mode" not in st.session_state:
        st.session_state["edit_mode"] = False
    if "analyze_result_detail" not in st.session_state:
        st.session_state["analyze_result_detail"] = None

    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 8])
    with col_btn1:
        if st.button("编辑" if not st.session_state["edit_mode"] else "取消编辑", key="edit_detail"):
            st.session_state["edit_mode"] = not st.session_state["edit_mode"]
            st.rerun()
    with col_btn2:
        ft = doc.get("full_text", "")
        src_url = doc.get("source_url", "")
        has_text = bool(ft and len(ft) >= 50)
        has_url = bool(src_url)
        btn_label = "分析提炼要点" if not st.session_state.get("analyze_result_detail") else "重新分析"
        btn_disabled = not has_text and not has_url
        if st.button(btn_label, type="secondary", disabled=btn_disabled, key="analyze_btn"):
            if not has_text and has_url:
                with st.spinner("正在从原文链接获取内容..."):
                    try:
                        fetch_result = fetch_from_url(src_url)
                        if fetch_result["text"]:
                            ft = fetch_result["text"]
                        else:
                            st.error("获取原文失败")
                            ft = ""
                    except Exception as e:
                        st.error(f"获取原文失败: {e}")
                        ft = ""
            if ft and len(ft) >= 50:
                with st.spinner("正在分析..."):
                    st.session_state["analyze_result_detail"] = analyze_document(ft)
                st.rerun()
        if btn_disabled:
            st.caption("*无正文或原文链接")

    # 分析结果
    analysis = st.session_state.get("analyze_result_detail")
    if analysis:
        with st.container(border=True):
            st.markdown("### 分析提炼结果")
            st.markdown(f"**摘要**: {analysis['summary']}")
            if analysis.get("scope"):
                st.markdown(f"**适用范围**: {analysis['scope']}")
            if analysis.get("key_points"):
                st.markdown("**关键条款**:")
                for i, kp in enumerate(analysis["key_points"], 1):
                    st.markdown(f"{i}. {kp}")
            if analysis.get("deadlines"):
                st.markdown("**时限要求**:")
                for i, dl in enumerate(analysis["deadlines"], 1):
                    st.markdown(f"{i}. {dl}")
            if st.button("清除分析结果", key="clear_analysis"):
                st.session_state["analyze_result_detail"] = None
                st.rerun()
        st.markdown("---")

    if st.session_state["edit_mode"]:
        with st.form("edit_doc_inline"):
            title = st.text_input("文件名称 *", value=doc["title"])
            c1, c2 = st.columns(2)
            with c1:
                document_no = st.text_input("文号", value=doc.get("document_no", ""))
                issuing_authority = st.text_input("发文单位", value=doc.get("issuing_authority", ""))
                publish_date = st.text_input("发布日期", value=doc.get("publish_date", ""))
                effective_date = st.text_input("实施日期", value=doc.get("effective_date", ""))
                expiry_date = st.text_input("失效日期", value=doc.get("expiry_date", ""))
            with c2:
                cur_st = doc.get("status", "待核实")
                st_idx = DOC_STATUS_OPTIONS.index(cur_st) if cur_st in DOC_STATUS_OPTIONS else 0
                status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=st_idx)
                region = st.selectbox("适用地区", REGION_OPTIONS,
                    index=REGION_OPTIONS.index(doc.get("region", "全国")) if doc.get("region") in REGION_OPTIONS else 0)
                category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS,
                    index=DOC_CATEGORY_OPTIONS.index(doc.get("category", "其他")) if doc.get("category") in DOC_CATEGORY_OPTIONS else 0)
                source_url = st.text_input("原文链接", value=doc.get("source_url", ""))
            keywords = st.text_input("关键词", value=doc.get("keywords", ""))
            summary = st.text_area("摘要", value=doc.get("summary", ""), height=60)
            full_text = st.text_area("正文全文", value=doc.get("full_text", ""), height=200)
            notes = st.text_area("备注", value=doc.get("notes", ""), height=60)

            if st.form_submit_button("保存修改"):
                data = {
                    "title": title.strip(),
                    "document_no": document_no.strip() if document_no else "",
                    "issuing_authority": issuing_authority.strip() if issuing_authority else "",
                    "publish_date": publish_date.strip() if publish_date else "",
                    "effective_date": effective_date.strip() if effective_date else "",
                    "expiry_date": expiry_date.strip() if expiry_date else "",
                    "status": status, "region": region, "category": category,
                    "keywords": keywords.strip() if keywords else "",
                    "summary": summary.strip() if summary else "",
                    "full_text": full_text.strip() if full_text else "",
                    "source_url": source_url.strip() if source_url else "",
                    "notes": notes.strip() if notes else "",
                }
                db.update_document(view_doc_id, data)
                st.success("保存成功")
                st.session_state["edit_mode"] = False
                st.rerun()
    else:
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

        source_url = doc.get("source_url", "")
        if source_url:
            st.markdown(f"**原文链接：** [{source_url}]({source_url})")
        if doc.get("summary"):
            st.caption("**摘要：**")
            st.markdown(doc["summary"])
        if doc.get("notes"):
            st.caption("**备注：**")
            st.markdown(doc["notes"])

        if doc.get("full_text"):
            with st.expander("文件正文"):
                st.text_area("", doc["full_text"], height=300, disabled=True, label_visibility="collapsed")

        st.markdown("---")
        st.subheader("传承关系")
        relations = db.get_relations_for_document(view_doc_id)
        if relations["downstream"]:
            st.markdown("**本文件被以下文件替代/废止：**")
            for r in relations["downstream"]:
                st.markdown(f"- 【{r['relation_type']}】→ 《{r['new_title']}》（{r.get('new_document_no', '无文号')}）")
                if r.get("relation_basis"):
                    st.caption(f"  依据: {r['relation_basis']}")
        if relations["upstream"]:
            st.markdown("**本文件替代/废止了以下文件：**")
            for r in relations["upstream"]:
                st.markdown(f"- 【{r['relation_type']}】← 《{r['old_title']}》（{r.get('old_document_no', '无文号')}）")

    st.stop()

# ═══════════ 政策文件库主页 ═══════════
st.title("政策文件库")

# ═══════════ 搜索和筛选栏 ═══════════
col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
with col1:
    keyword = st.text_input("搜索", placeholder="文件名称/文号/发文单位/关键词")
with col2:
    status_filter = st.selectbox("文件状态", ["全部"] + DOC_STATUS_OPTIONS)
with col3:
    region_filter = st.selectbox("适用地区", ["全部"] + REGION_OPTIONS)
with col4:
    category_filter = st.selectbox("文件类别", ["全部"] + DOC_CATEGORY_OPTIONS)

# ═══════════ 操作按钮栏 ═══════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["导入链接", "上传文件", "新增文件", "导入 Excel", "导出 Excel", "网络搜索"])

# --- Tab1: 导入链接（默认） ---
with tab1:
    st.caption("粘贴政策文件的网页链接，系统自动抓取正文并提取元数据")
    url_input = st.text_input("文件链接", placeholder="https://...", label_visibility="collapsed", key="import_url")
    if st.button("抓取", key="fetch_btn"):
        if not url_input.strip():
            st.error("请输入链接")
        else:
            with st.spinner("正在抓取文件..."):
                result = fetch_from_url(url_input.strip())
            if result["error"]:
                st.error(f"抓取失败: {result['error']}")
            elif not result["text"].strip():
                st.warning("未能提取到有效文本内容")
            else:
                st.session_state["fetched_data"] = result
                st.session_state["fetch_url"] = url_input.strip()
                st.rerun()

    # 显示抓取结果，确认入库
    fetched = st.session_state.get("fetched_data", None)
    if fetched:
        text = fetched["text"]
        meta = extract_all_metadata(text)
        st.success(f"抓取成功，共 {len(text)} 字符")
        st.markdown(f"**来源**: {st.session_state.get('fetch_url', '')}")
        st.markdown(f"**文件名**: {fetched.get('file_name', '未知')}")

        with st.container(border=True):
            st.markdown("**识别结果：**")
            cols = st.columns(4)
            with cols[0]:
                st.metric("标题", meta.get("title", "未识别")[:20] or "未识别")
            with cols[1]:
                st.metric("文号", meta.get("document_no", "未识别") or "未识别")
            with cols[2]:
                st.metric("发文单位", meta.get("issuing_authority", "未识别") or "未识别")
            with cols[3]:
                st.metric("发布日期", meta.get("publish_date", "未识别") or "未识别")

        with st.expander("查看正文 / 修改信息并入库"):
            st.text_area("正文预览", text[:5000], height=200, disabled=True, label_visibility="collapsed")
            with st.form("url_import_form"):
                title = st.text_input("文件名称 *", value=meta.get("title", ""))
                c1, c2 = st.columns(2)
                with c1:
                    doc_no = st.text_input("文号", value=meta.get("document_no", "") or "")
                    authority = st.text_input("发文单位", value=meta.get("issuing_authority", "") or "")
                    pub_date = st.text_input("发布日期", value=meta.get("publish_date", "") or "")
                with c2:
                    eff_date = st.text_input("实施日期", value=meta.get("effective_date", "") or "")
                    exp_date = st.text_input("失效日期", value=meta.get("expiry_date", "") or "")
                    s = meta.get("status", "待核实")
                    st_idx = DOC_STATUS_OPTIONS.index(s) if s in DOC_STATUS_OPTIONS else DOC_STATUS_OPTIONS.index("待核实")
                    status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=st_idx)
                region = st.selectbox("适用地区", REGION_OPTIONS)
                suggested_cat = classify_document(meta.get("title", ""), meta.get("document_no", ""), text)
                cat_idx = DOC_CATEGORY_OPTIONS.index(suggested_cat) if suggested_cat in DOC_CATEGORY_OPTIONS else DOC_CATEGORY_OPTIONS.index("其他")
                category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS, index=cat_idx)
                keywords = st.text_input("关键词")
                notes = st.text_input("备注")

                cfb, cfb2 = st.columns([1, 4])
                with cfb:
                    confirmed = st.form_submit_button("确认入库")
                with cfb2:
                    cancel = st.form_submit_button("取消")

                if confirmed:
                    if not title.strip():
                        st.error("文件名称不能为空")
                    else:
                        data = {
                            "title": title.strip(),
                            "document_no": doc_no.strip() if doc_no else "",
                            "issuing_authority": authority.strip() if authority else "",
                            "publish_date": pub_date.strip() if pub_date else "",
                            "effective_date": eff_date.strip() if eff_date else "",
                            "expiry_date": exp_date.strip() if exp_date else "",
                            "status": status,
                            "region": region,
                            "category": category,
                            "keywords": keywords.strip() if keywords else "",
                            "source_type": fetched.get("source_type", "网络检索"),
                            "source_url": st.session_state.get("fetch_url", ""),
                            "confirmed": 1,
                            "notes": notes.strip() if notes else "",
                        }
                        doc_id = db.create_document(data)
                        st.success(f"《{title.strip()}》入库成功！ID: {doc_id}")
                        del st.session_state["fetched_data"]
                        if "fetch_url" in st.session_state:
                            del st.session_state["fetch_url"]
                        st.rerun()

                if cancel:
                    del st.session_state["fetched_data"]
                    if "fetch_url" in st.session_state:
                        del st.session_state["fetch_url"]
                    st.rerun()

# --- Tab2: 上传文件 ---
with tab2:
    supported_types = get_supported_types()
    st.caption(f"支持格式：{', '.join(supported_types)}")

    uploaded_files = st.file_uploader(
        "选择政策文件（可一次选择多个）",
        type=supported_types,
        accept_multiple_files=True,
        key="policy_file_uploader",
        label_visibility="collapsed",
    )

    if uploaded_files:
        st.info(f"已选择 {len(uploaded_files)} 个文件，正在解析...")
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def process_one(uf):
            file_path = os.path.join(UPLOADS_DIR, uf.name)
            with open(file_path, "wb") as f:
                f.write(uf.read())
            try:
                text = parse_file(file_path, pdf_max_pages=15)
                meta = extract_all_metadata(text)
                return {"name": uf.name, "path": file_path, "text": text, "meta": meta, "error": None}
            except Exception as e:
                return {"name": uf.name, "path": file_path, "text": "", "meta": {}, "error": str(e)}

        pending = []
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(process_one, uf): uf for uf in uploaded_files}
            for fut in as_completed(futures):
                pending.append(fut.result())

        st.session_state["upload_batch"] = pending

    # 显示解析结果，逐一确认入库
    batch = st.session_state.get("upload_batch", [])
    if batch:
        st.markdown("---")
        st.subheader(f"解析结果（共 {len(batch)} 个文件）")

        for i, item in enumerate(batch):
            with st.container():
                if item["error"]:
                    st.error(f"  {item['name']} — 解析失败: {item['error']}")
                else:
                    meta = item["meta"]
                    text = item["text"]

                    st.markdown(
                        f"**文件 {i+1}：{item['name']}**"
                        f"（{len(text)} 字）"
                    )

                    cols = st.columns(4)
                    with cols[0]:
                        st.metric("识别标题", meta.get("title", "未识别")[:20] or "未识别")
                    with cols[1]:
                        st.metric("识别文号", meta.get("document_no", "未识别") or "未识别")
                    with cols[2]:
                        st.metric("发文单位", meta.get("issuing_authority", "未识别") or "未识别")
                    with cols[3]:
                        st.metric("发布日期", meta.get("publish_date", "未识别") or "未识别")

                    with st.expander("查看正文 / 修改元数据并入库"):
                        st.text_area("", text[:3000], height=150, disabled=True, label_visibility="collapsed")

                        form_key = f"cfm_{i}"
                        with st.form(form_key):
                            title = st.text_input("文件名称 *", value=meta.get("title", ""), key=f"t_{i}")
                            c1, c2 = st.columns(2)
                            with c1:
                                doc_no = st.text_input("文号", value=meta.get("document_no", "") or "", key=f"dn_{i}")
                                authority = st.text_input("发文单位", value=meta.get("issuing_authority", "") or "", key=f"au_{i}")
                                pub_date = st.text_input("发布日期", value=meta.get("publish_date", "") or "", key=f"pd_{i}")
                            with c2:
                                eff_date = st.text_input("实施日期", value=meta.get("effective_date", "") or "", key=f"ed_{i}")
                                exp_date = st.text_input("失效日期", value=meta.get("expiry_date", "") or "", key=f"xd_{i}")
                                s = meta.get("status", "待核实")
                                st_idx = DOC_STATUS_OPTIONS.index(s) if s in DOC_STATUS_OPTIONS else DOC_STATUS_OPTIONS.index("待核实")
                                status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=st_idx, key=f"st_{i}")
                            region = st.selectbox("适用地区", REGION_OPTIONS, key=f"rg_{i}")
                            suggested_cat = classify_document(meta.get("title", ""), meta.get("document_no", ""), text)
                            cat_idx = DOC_CATEGORY_OPTIONS.index(suggested_cat) if suggested_cat in DOC_CATEGORY_OPTIONS else DOC_CATEGORY_OPTIONS.index("其他")
                            category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS, index=cat_idx, key=f"cg_{i}")
                            keywords = st.text_input("关键词", key=f"kw_{i}")
                            notes = st.text_input("备注", key=f"nt_{i}")

                            cb1, cb2 = st.columns([1, 6])
                            with cb1:
                                confirm = st.form_submit_button("确认入库")
                            with cb2:
                                skip = st.form_submit_button("跳过")

                            if confirm:
                                if not title.strip():
                                    st.error("文件名称不能为空")
                                else:
                                    data = {
                                        "title": title.strip(),
                                        "document_no": doc_no.strip() if doc_no else "",
                                        "issuing_authority": authority.strip() if authority else "",
                                        "publish_date": pub_date.strip() if pub_date else "",
                                        "effective_date": eff_date.strip() if eff_date else "",
                                        "expiry_date": exp_date.strip() if exp_date else "",
                                        "status": status,
                                        "region": region,
                                        "category": category,
                                        "keywords": keywords.strip() if keywords else "",
                                        "full_text": text,
                                        "source_type": "上传",
                                        "file_path": item["path"],
                                        "confirmed": 1,
                                        "notes": notes.strip() if notes else "",
                                    }
                                    db.create_document(data)
                                    st.session_state["upload_batch"][i] = None
                                    st.success(f"《{title.strip()}》入库成功！")
                                    st.rerun()

                            if skip:
                                st.session_state["upload_batch"][i] = None
                                st.rerun()

            st.markdown("---")

        # 清理已处理的文件
        if batch:
            remaining = [item for item in batch if item is not None]
            if remaining:
                st.session_state["upload_batch"] = remaining
            else:
                if "upload_batch" in st.session_state:
                    del st.session_state["upload_batch"]
                st.success("全部文件处理完毕！")
                st.rerun()

# --- Tab3: 新增文件 ---
with tab3:
    with st.form("add_document_form"):
        title = st.text_input("文件名称 *", key="add_title")
        col_a, col_b = st.columns(2)
        with col_a:
            document_no = st.text_input("文号")
            issuing_authority = st.text_input("发文单位")
            publish_date = st.text_input("发布日期 (YYYY-MM-DD)")
            effective_date = st.text_input("实施日期 (YYYY-MM-DD)")
            expiry_date = st.text_input("失效日期 (YYYY-MM-DD)")
        with col_b:
            status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=DOC_STATUS_OPTIONS.index("待核实"))
            region = st.selectbox("适用地区", REGION_OPTIONS)
            category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS)
            source_type = st.selectbox("来源类型", SOURCE_TYPE_OPTIONS)
            source_url = st.text_input("原文链接")
        keywords = st.text_input("关键词（逗号分隔）")
        summary = st.text_area("摘要", height=60)
        full_text = st.text_area("正文全文（可粘贴）", height=120)
        notes = st.text_area("备注", height=60)

        submitted = st.form_submit_button("确认新增")
        if submitted:
            if not title.strip():
                st.error("文件名称不能为空")
            else:
                data = {
                    "title": title.strip(),
                    "document_no": document_no.strip(),
                    "issuing_authority": issuing_authority.strip(),
                    "publish_date": publish_date.strip(),
                    "effective_date": effective_date.strip(),
                    "expiry_date": expiry_date.strip(),
                    "status": status,
                    "region": region,
                    "category": category,
                    "keywords": keywords.strip(),
                    "summary": summary.strip(),
                    "full_text": full_text.strip(),
                    "source_type": source_type,
                    "source_url": source_url.strip(),
                    "confirmed": 1,
                    "notes": notes.strip(),
                }
                if document_no.strip():
                    existing = db.get_document_by_no(document_no.strip())
                    if existing:
                        st.error(f"文号「{document_no.strip()}」已存在：《{existing['title']}》")
                    else:
                        doc_id = db.create_document(data)
                        st.success(f"新增成功！ID: {doc_id}")
                        st.rerun()
                else:
                    doc_id = db.create_document(data)
                    st.success(f"新增成功！ID: {doc_id}")
                    st.rerun()

# --- Tab4: 导入 Excel ---
with tab4:
    st.markdown("请按照模板格式填写政策文件清单后上传")

    # 下载模板
    template_bytes = generate_import_template()
    st.download_button(
        "下载导入模板",
        data=template_bytes,
        file_name="政策文件导入模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    import_file = st.file_uploader("上传填写好的 Excel 文件", type=["xlsx"], key="import_xlsx")
    if import_file:
        tmp_path = os.path.join(UPLOADS_DIR, "_import_temp.xlsx")
        with open(tmp_path, "wb") as f:
            f.write(import_file.read())
        result = parse_import_excel(tmp_path)

        st.success(f"导入完成：成功 {len(result['success'])} 条")
        if result["errors"]:
            st.warning(f"失败 {len(result['errors'])} 条：")
            for err in result["errors"]:
                st.caption(f"- {err}")

# --- Tab5: 导出 Excel ---
with tab5:
    export_status = st.selectbox("筛选导出状态", ["全部"] + DOC_STATUS_OPTIONS, key="export_status")
    if st.button("导出政策文件库"):
        docs = db.get_all_documents(status="" if export_status == "全部" else export_status)
        if docs:
            excel_bytes = export_documents_to_excel(docs)
            st.download_button(
                "下载 Excel",
                data=excel_bytes,
                file_name="政策文件库.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.success(f"共 {len(docs)} 条记录")
        else:
            st.info("没有符合条件的记录")

# --- Tab6: 网络搜索入库 ---
with tab6:
    st.caption("输入政策名称，在线搜索并导入文件库")
    col_s1, col_s2 = st.columns([4, 1])
    with col_s1:
        search_query = st.text_input("政策名称", placeholder="输入政策文件名称关键词...", key="web_search_query", label_visibility="collapsed")
    with col_s2:
        do_search = st.button("搜索", key="btn_web_search", type="primary")

    if do_search and search_query.strip():
        with st.spinner(f"正在搜索「{search_query.strip()}」..."):
            st.session_state["web_search_results"] = search_policy_online(search_query.strip(), max_results=10)
        if not st.session_state.get("web_search_results"):
            st.warning("未搜索到结果，请尝试更换关键词")
        st.rerun()

    # 显示搜索结果
    search_results = st.session_state.get("web_search_results", None)
    if search_results:
        st.markdown(f"**搜索到 {len(search_results)} 条结果：**")

        for i, item in enumerate(search_results):
            with st.container():
                st.markdown(f"**{i+1}. [{item['title']}]({item['url']})**")
                st.caption(f"{item['snippet'][:200]}  |  来源: {item['source']}")
                col_fetch, _ = st.columns([1, 5])
                with col_fetch:
                    if st.button("抓取", key=f"ws_fetch_{i}"):
                        st.session_state["web_fetch_url"] = item["url"]
                        st.session_state["web_fetch_title"] = item["title"]
                        st.rerun()
            st.markdown("---")

        if st.button("清除搜索结果", key="clear_web_search"):
            del st.session_state["web_search_results"]
            st.rerun()

    # 抓取选中的结果
    fetch_url = st.session_state.get("web_fetch_url", None)
    if fetch_url:
        st.markdown("---")
        st.info(f"正在抓取：{st.session_state.get('web_fetch_title', '')}")
        with st.spinner("抓取中..."):
            result = fetch_from_url(fetch_url)
        if result["error"]:
            st.error(f"抓取失败: {result['error']}")
            if st.button("返回搜索结果"):
                del st.session_state["web_fetch_url"]
                st.rerun()
        elif not result["text"].strip():
            st.warning("未能提取到有效文本")
            if st.button("返回搜索结果"):
                del st.session_state["web_fetch_url"]
                st.rerun()
        else:
            text = result["text"]
            meta = extract_all_metadata(text)
            st.success(f"抓取成功，共 {len(text)} 字符")

            with st.container(border=True):
                st.markdown("**识别结果：**")
                cols = st.columns(4)
                with cols[0]:
                    st.metric("标题", meta.get("title", "未识别")[:20] or "未识别")
                with cols[1]:
                    st.metric("文号", meta.get("document_no", "未识别") or "未识别")
                with cols[2]:
                    st.metric("发文单位", meta.get("issuing_authority", "未识别") or "未识别")
                with cols[3]:
                    st.metric("发布日期", meta.get("publish_date", "未识别") or "未识别")

            with st.expander("查看正文 / 修改信息并入库"):
                st.text_area("正文预览", text[:5000], height=200, disabled=True, label_visibility="collapsed")
                with st.form("web_import_form"):
                    title = st.text_input("文件名称 *", value=meta.get("title", ""))
                    c1, c2 = st.columns(2)
                    with c1:
                        doc_no = st.text_input("文号", value=meta.get("document_no", "") or "")
                        authority = st.text_input("发文单位", value=meta.get("issuing_authority", "") or "")
                        pub_date = st.text_input("发布日期", value=meta.get("publish_date", "") or "")
                    with c2:
                        eff_date = st.text_input("实施日期", value=meta.get("effective_date", "") or "")
                        exp_date = st.text_input("失效日期", value=meta.get("expiry_date", "") or "")
                        s = meta.get("status", "待核实")
                        st_idx = DOC_STATUS_OPTIONS.index(s) if s in DOC_STATUS_OPTIONS else DOC_STATUS_OPTIONS.index("待核实")
                        status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=st_idx)
                    region = st.selectbox("适用地区", REGION_OPTIONS)
                    suggested_cat = classify_document(meta.get("title", ""), meta.get("document_no", ""), text)
                    cat_idx = DOC_CATEGORY_OPTIONS.index(suggested_cat) if suggested_cat in DOC_CATEGORY_OPTIONS else DOC_CATEGORY_OPTIONS.index("其他")
                    category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS, index=cat_idx)
                    keywords = st.text_input("关键词")
                    notes = st.text_input("备注")

                    cfb, cfb2, cfb3 = st.columns([1, 1, 4])
                    with cfb:
                        confirmed = st.form_submit_button("确认入库")
                    with cfb2:
                        cancel = st.form_submit_button("取消")

                    if confirmed:
                        if not title.strip():
                            st.error("文件名称不能为空")
                        else:
                            data = {
                                "title": title.strip(),
                                "document_no": doc_no.strip() if doc_no else "",
                                "issuing_authority": authority.strip() if authority else "",
                                "publish_date": pub_date.strip() if pub_date else "",
                                "effective_date": eff_date.strip() if eff_date else "",
                                "expiry_date": exp_date.strip() if exp_date else "",
                                "status": status,
                                "region": region,
                                "category": category,
                                "keywords": keywords.strip() if keywords else "",
                                "full_text": text,
                                "source_type": "网络搜索",
                                "source_url": fetch_url,
                                "confirmed": 1,
                                "notes": notes.strip() if notes else "",
                            }
                            doc_id = db.create_document(data)
                            st.success(f"《{title.strip()}》入库成功！ID: {doc_id}")
                            for k in ["web_search_results", "web_fetch_url", "web_fetch_title"]:
                                if k in st.session_state:
                                    del st.session_state[k]
                            st.rerun()

                    if cancel:
                        for k in ["web_search_results", "web_fetch_url", "web_fetch_title"]:
                            if k in st.session_state:
                                del st.session_state[k]
                        st.rerun()

# ═══════════ 文件列表 ═══════════
st.markdown("---")
st.subheader("文件列表")
st.caption(f"共 {db.count_documents(keyword, '' if status_filter == '全部' else status_filter, '' if region_filter == '全部' else region_filter, '' if category_filter == '全部' else category_filter)} 条记录")

docs = db.search_documents(
    keyword=keyword,
    status="" if status_filter == "全部" else status_filter,
    region="" if region_filter == "全部" else region_filter,
    category="" if category_filter == "全部" else category_filter,
)

for doc in docs:
    with st.container():
        col1, col2, col3, col4 = st.columns([4, 2, 1, 1])
        with col1:
            st.markdown(f"**《{doc['title']}》**")
            info_parts = []
            if doc["document_no"]:
                info_parts.append(doc["document_no"])
            if doc["issuing_authority"]:
                info_parts.append(doc["issuing_authority"])
            st.caption(" | ".join(info_parts))
        with col2:
            status_color = {
                "现行有效": "green", "已废止": "red", "已失效": "red",
                "被替代": "orange", "部分废止": "orange", "即将失效": "orange",
            }
            color = status_color.get(doc["status"], "grey")
            st.markdown(f":{color}[{doc['status']}]")
        with col3:
            if st.button("查看", key=f"view_{doc['id']}"):
                st.session_state["view_doc_id"] = doc["id"]
                st.rerun()
        with col4:
            if st.button("删除", key=f"del_{doc['id']}"):
                db.delete_document(doc["id"])
                st.rerun()
    st.markdown("---")
