"""政策文件库管理页面"""

import os
import io
import uuid
import tempfile
import time

import pandas as pd
import streamlit as st

import database.db as db
from config import (
    DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS,
    REGION_OPTIONS, SOURCE_TYPE_OPTIONS, UPLOADS_DIR,
    ENABLE_WEB_IMPORT, SAVE_POLICY_FILE, ALLOW_POLICY_DOWNLOAD,
    POLICY_FILES_DIR, BUSINESS_TYPE_OPTIONS, SENSITIVITY_LEVEL_OPTIONS,
    DEFAULT_LOCAL_IMPORT_DIR, MAX_UPLOAD_SIZE_MB,
)
from modules.document_parser import parse_file, get_supported_types, safe_fetch_from_url, analyze_document, get_pdf_page_info, parse_file_with_structure
from modules.metadata_extractor import extract_all_metadata, classify_document, extract_title, extract_title_with_meta, extract_primary_document_no, is_attachment_or_form_title
from modules.classifier import classify_business_tags
from modules.import_validator import (
    validate_import_candidate, clean_filename_for_title, looks_like_policy_filename,
    is_attachment_title,
)
from modules.status_utils import normalize_document_status
from modules.rule_engine import get_display_title, detect_invalid_title, truncate_text, apply_rules
from modules.excel_io import (
    generate_import_template, parse_import_excel,
    export_documents_to_excel,
)
from utils.ui import render_app_header

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

    # 标题异常检测和提示
    raw_title = doc.get("title", "")
    title_is_invalid = detect_invalid_title(raw_title) if raw_title else True
    if title_is_invalid:
        reason_parts = []
        if not raw_title:
            reason_parts.append("标题为空")
        elif raw_title in ("《》", "未识别", "未识别标题", "无标题", "【未识别标题，请补录】"):
            reason_parts.append(f"标题为系统占位符")
        elif any(h in raw_title for h in ["PDF共", "仅展示前", "仅显示前", "完整内容将"]):
            reason_parts.append("标题包含PDF解析提示信息")
        else:
            from modules.import_validator import is_attachment_title as _is_att_detail
            is_att_detail, att_reason_detail = _is_att_detail(raw_title)
            if is_att_detail:
                reason_parts.append(f"疑似附件/材料清单: {att_reason_detail}")
            else:
                reason_parts.append("标题未能通过规则检测")
        reason_text = "；".join(reason_parts)
        st.warning(f"⚠️ **标题异常**: {reason_text}")
        st.markdown("""
        **建议处理方式：**
        1. 点击「编辑」手工补录标题
        2. 点击「重新解析」重新提取元数据
        3. 删除该记录
        4. 加入非政策文件过滤规则
        """)

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
                        fetch_result = safe_fetch_from_url(src_url)
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
                source_publish_date = st.text_input("网页发布日期", value=doc.get("source_publish_date", ""))
                pass_date = st.text_input("通过日期", value=doc.get("pass_date", ""))
            with c2:
                cur_st = doc.get("status", "待核实")
                st_idx = DOC_STATUS_OPTIONS.index(cur_st) if cur_st in DOC_STATUS_OPTIONS else 0
                status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=st_idx)
                region = st.selectbox("适用地区", REGION_OPTIONS,
                    index=REGION_OPTIONS.index(doc.get("region", "全国")) if doc.get("region") in REGION_OPTIONS else 0)
                category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS,
                    index=DOC_CATEGORY_OPTIONS.index(doc.get("category", "其他")) if doc.get("category") in DOC_CATEGORY_OPTIONS else 0)
                source_url = st.text_input("原文链接", value=doc.get("source_url", ""))
                latest_revision_date = st.text_input("最近修正日期", value=doc.get("latest_revision_date", ""))
                source_name = st.text_input("来源网站", value=doc.get("source_name", ""))
            keywords = st.text_input("关键词", value=doc.get("keywords", ""))
            cur_bt = doc.get("business_tags", "").split(",") if doc.get("business_tags") else []
            bt_selected = st.multiselect("业务类型", BUSINESS_TYPE_OPTIONS,
                default=[t for t in cur_bt if t in BUSINESS_TYPE_OPTIONS])
            cur_sl = doc.get("sensitivity_level", "公开")
            sl_idx = SENSITIVITY_LEVEL_OPTIONS.index(cur_sl) if cur_sl in SENSITIVITY_LEVEL_OPTIONS else 0
            sl = st.selectbox("敏感级别", SENSITIVITY_LEVEL_OPTIONS, index=sl_idx)
            summary = st.text_area("摘要", value=doc.get("summary", ""), height=60)
            revision_history = st.text_area("文件沿革", value=doc.get("revision_history", ""), height=60)
            full_text = st.text_area("正文全文", value=doc.get("full_text", ""), height=200)
            notes = st.text_area("备注", value=doc.get("notes", ""), height=60)

            if st.form_submit_button("保存修改"):
                old_sl = doc.get("sensitivity_level", "")
                data = {
                    "title": title.strip(),
                    "document_no": document_no.strip() if document_no else "",
                    "issuing_authority": issuing_authority.strip() if issuing_authority else "",
                    "publish_date": publish_date.strip() if publish_date else "",
                    "effective_date": effective_date.strip() if effective_date else "",
                    "expiry_date": expiry_date.strip() if expiry_date else "",
                    "source_publish_date": source_publish_date.strip() if source_publish_date else "",
                    "pass_date": pass_date.strip() if pass_date else "",
                    "latest_revision_date": latest_revision_date.strip() if latest_revision_date else "",
                    "revision_history": revision_history.strip() if revision_history else "",
                    "source_name": source_name.strip() if source_name else "",
                    "status": status, "region": region, "category": category,
                    "keywords": keywords.strip() if keywords else "",
                    "business_tags": ",".join(bt_selected),
                    "sensitivity_level": sl,
                    "summary": summary.strip() if summary else "",
                    "full_text": full_text.strip() if full_text else "",
                    "source_url": source_url.strip() if source_url else "",
                    "notes": notes.strip() if notes else "",
                }
                db.update_document(view_doc_id, data)
                if old_sl != sl:
                    db.log_operation({
                        "action": "文件敏感级别修改", "target_type": "document",
                        "target_id": view_doc_id, "file_name": doc.get("title", ""),
                        "sensitivity_level": sl,
                        "notes": f"从 '{old_sl}' 改为 '{sl}'",
                    })
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

        bt = doc.get("business_tags", "")
        if bt:
            bt_tags = [t.strip() for t in bt.split(",") if t.strip()]
            st.markdown(f"**业务类型：** {' / '.join(bt_tags)}")
        sl_label = doc.get("sensitivity_level", "公开")
        st.markdown(f"**敏感级别：** {sl_label}")

        source_url = doc.get("source_url", "")
        if source_url:
            st.markdown(f"**原文链接：** [{source_url}]({source_url})")
        if doc.get("source_publish_date"):
            st.markdown(f"**网页发布日期：** {doc['source_publish_date']}")
        if doc.get("pass_date"):
            st.markdown(f"**通过日期：** {doc['pass_date']}")
        if doc.get("latest_revision_date"):
            st.markdown(f"**最近修正日期：** {doc['latest_revision_date']}")
        if doc.get("source_name"):
            st.markdown(f"**来源网站：** {doc['source_name']}")
        if doc.get("revision_history"):
            st.caption("**文件沿革：**")
            st.markdown(doc["revision_history"][:300])
        if doc.get("summary"):
            st.caption("**摘要：**")
            st.markdown(doc["summary"])
        if doc.get("notes"):
            st.caption("**备注：**")
            st.markdown(doc["notes"])

        if doc.get("full_text"):
            with st.expander("文件正文"):
                st.text_area("", doc["full_text"], height=300, disabled=True, label_visibility="collapsed")

        # 文件下载
        if ALLOW_POLICY_DOWNLOAD and doc.get("file_path"):
            fp = doc["file_path"]
            if os.path.isfile(fp):
                fname = doc.get("file_name", "") or os.path.basename(fp)
                with open(fp, "rb") as f:
                    st.download_button(
                        "下载原文件",
                        data=f.read(),
                        file_name=fname,
                        mime="application/octet-stream",
                        key=f"dl_inline_{view_doc_id}",
                    )
            else:
                st.caption("原文件不存在或已被删除")

        st.markdown("---")
        st.subheader("新旧关系")
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
render_app_header("政策文件查询", "检索、筛选和维护已入库政策文件")

# ═══════════ 搜索和筛选栏 ═══════════
# 文件状态筛选框：仅使用标准枚举，不包含"编码有效"等非标准值
_allowed_statuses = list(DOC_STATUS_OPTIONS)
valid_status_options = ["全部"] + _allowed_statuses

# 强制清理 session_state 中残留的旧状态值（防止下拉框显示历史脏数据）
for _bad_key in ["status_filter", "status_filter_v2", "文件状态"]:
    old_val = st.session_state.get(_bad_key)
    if old_val and old_val not in valid_status_options:
        st.session_state[_bad_key] = "全部"
col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])
with col1:
    keyword = st.text_input("搜索", placeholder="文件名称/文号/发文单位/关键词/业务类型")
with col2:
    status_filter = st.selectbox("文件状态", ["全部"] + _allowed_statuses, key="status_filter_v2")
with col3:
    region_filter = st.selectbox("适用地区", ["全部"] + REGION_OPTIONS)
with col4:
    category_filter = st.selectbox("文件类别", ["全部"] + DOC_CATEGORY_OPTIONS)
with col5:
    bt_filter = st.selectbox("业务类型", ["全部"] + BUSINESS_TYPE_OPTIONS)
with col6:
    title_status_filter = st.selectbox("标题状态", ["全部", "正常标题", "标题异常"])

# ═══════════ 操作按钮栏 ═══════════
if ENABLE_WEB_IMPORT:
    tab1, tab2, tab3, tab4, tab5, tab_folder = st.tabs(
        ["导入链接", "上传文件", "新增文件", "导入 Excel", "导出 Excel", "本地文件夹导入"])
else:
    tab2, tab3, tab4, tab5, tab_folder = st.tabs(
        ["上传文件", "新增文件", "导入 Excel", "导出 Excel", "本地文件夹导入"])
    tab1 = None

# --- Tab1: 导入链接（仅在 ENABLE_WEB_IMPORT=True 时可用） ---
if tab1 is not None:
    with tab1:
        st.caption("粘贴政策文件的网页链接，系统自动抓取正文并提取元数据")

        # 安全提示
        st.warning(
            "本功能仅用于读取公开政策网页信息并录入本地政策文件库。"
            "请勿输入涉密、内部系统、非公开网页或需要登录权限的网址。"
            "本功能不会上传待审查文档内容，也不会在文档审查阶段联网搜索。"
        )

        url_input = st.text_input("文件链接", placeholder="https://...", label_visibility="collapsed", key="import_url")

        # 安全确认勾选框
        safety_confirmed = st.checkbox(
            "我确认该链接为公开政策文件网页，不涉及涉密、内部敏感或非公开信息。",
            key="import_safety_check",
        )

        if st.button("抓取", key="fetch_btn", disabled=not safety_confirmed):
            if not url_input.strip():
                st.error("请输入链接")
            else:
                with st.spinner("正在抓取文件..."):
                    result = safe_fetch_from_url(url_input.strip())
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
            # 优先使用网页结构化元数据，fallback 到文本提取
            wm = fetched.get("webpage_meta", {})
            text_meta = extract_all_metadata(text)

            st.success(f"抓取成功，共 {len(text)} 字符")
            st.markdown(f"**来源URL**: {st.session_state.get('fetch_url', '')}")

            # 识别结果摘要
            with st.container(border=True):
                st.markdown("**识别结果：**")
                cols = st.columns(4)
                with cols[0]:
                    st.metric("标题", (wm.get("title") or text_meta.get("title") or "未识别")[:25] or "未识别")
                with cols[1]:
                    st.metric("文号", wm.get("document_no") or text_meta.get("document_no") or "（空）")
                with cols[2]:
                    cat = wm.get("category") or classify_document(
                        wm.get("title", ""), wm.get("document_no", ""), text)
                    st.metric("文件类别", cat or "未识别")
                with cols[3]:
                    st.metric("适用地区", wm.get("region") or "全国")
                # 第二行：日期信息
                cols2 = st.columns(4)
                with cols2[0]:
                    spd = wm.get("source_publish_date", "")
                    st.metric("网页发布日期", spd or "未识别")
                with cols2[1]:
                    st.metric("通过日期", wm.get("pass_date") or "未识别")
                with cols2[2]:
                    st.metric("最近修正日期", wm.get("latest_revision_date") or "未识别")
                with cols2[3]:
                    st.metric("实施日期", wm.get("effective_date") or text_meta.get("effective_date") or "未识别")

                # 来源网站和沿革
                if wm.get("source_name"):
                    st.caption(f"来源网站: {wm['source_name']}")
                if wm.get("revision_history"):
                    st.caption(f"文件沿革: {wm['revision_history'][:200]}")

            with st.expander("查看正文 / 修改信息并入库"):
                st.text_area("正文预览", text[:5000], height=200, disabled=True, label_visibility="collapsed")
                with st.form("url_import_form"):
                    title = st.text_input("文件名称 *",
                        value=wm.get("title") or text_meta.get("title", ""))
                    c1, c2 = st.columns(2)
                    with c1:
                        doc_no = st.text_input("文号",
                            value=wm.get("document_no") or text_meta.get("document_no") or "")
                        authority = st.text_input("发文单位",
                            value=wm.get("issuing_authority_candidate")
                            or text_meta.get("issuing_authority") or "",
                            placeholder="待人工确认")
                        pub_date = st.text_input("发布日期",
                            value=wm.get("publish_date") or text_meta.get("publish_date") or "")
                        spd = st.text_input("网页发布日期",
                            value=wm.get("source_publish_date", ""),
                            help="网页本身的发布日期，非文件发布日期")
                        pd = st.text_input("通过日期",
                            value=wm.get("pass_date", ""),
                            help="文件通过的日期")
                    with c2:
                        eff_date = st.text_input("实施日期",
                            value=wm.get("effective_date") or text_meta.get("effective_date") or "",
                            help='仅当正文有「自×起施行」时才填写')
                        exp_date = st.text_input("失效日期",
                            value=text_meta.get("expiry_date", "") or "")
                        lrd = st.text_input("最近修正日期",
                            value=wm.get("latest_revision_date", ""))
                        s = text_meta.get("status", "待核实")
                        st_idx = DOC_STATUS_OPTIONS.index(s) if s in DOC_STATUS_OPTIONS else DOC_STATUS_OPTIONS.index("待核实")
                        status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=st_idx)

                    region = st.selectbox("适用地区", REGION_OPTIONS,
                        index=REGION_OPTIONS.index(wm.get("region")) if wm.get("region") in REGION_OPTIONS else 0)
                    suggested_cat = (wm.get("category")
                        or classify_document(wm.get("title", ""), wm.get("document_no", ""), text))
                    cat_idx = DOC_CATEGORY_OPTIONS.index(suggested_cat) if suggested_cat in DOC_CATEGORY_OPTIONS else DOC_CATEGORY_OPTIONS.index("其他")
                    category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS, index=cat_idx)
                    keywords = st.text_input("关键词")
                    source_name = st.text_input("来源网站",
                        value=wm.get("source_name", ""),
                        help="转载来源网站名，非发文单位")
                    revision_history = st.text_area("文件沿革",
                        value=wm.get("revision_history", ""),
                        height=60,
                        help="文件的通过、修正、修订历史")
                    auto_bt = classify_business_tags(
                        wm.get("title", ""), keywords if keywords else "", text)
                    bt_selected = st.multiselect(
                        "业务类型", BUSINESS_TYPE_OPTIONS, default=auto_bt)
                    sl = st.selectbox("敏感级别", SENSITIVITY_LEVEL_OPTIONS,
                        index=0, key="url_import_sl")
                    notes = st.text_input("备注")

                    cfb, cfb2 = st.columns([1, 4])
                    with cfb:
                        confirmed = st.form_submit_button("确认入库")
                    with cfb2:
                        cancel = st.form_submit_button("取消")

                    if confirmed:
                        if "涉密禁止上传" in sl:
                            st.error("该级别文件禁止上传本系统，请使用单位规定的涉密系统或专用环境处理。")
                        elif not title.strip():
                            st.error("文件名称不能为空")
                        else:
                            data = {
                                "title": title.strip(),
                                "document_no": doc_no.strip() if doc_no else "",
                                "issuing_authority": authority.strip() if authority else "",
                                "publish_date": pub_date.strip() if pub_date else "",
                                "effective_date": eff_date.strip() if eff_date else "",
                                "expiry_date": exp_date.strip() if exp_date else "",
                                "source_publish_date": spd.strip() if spd else "",
                                "pass_date": pd.strip() if pd else "",
                                "latest_revision_date": lrd.strip() if lrd else "",
                                "revision_history": revision_history.strip() if revision_history else "",
                                "source_name": source_name.strip() if source_name else "",
                                "status": status,
                                "region": region,
                                "category": category,
                                "keywords": keywords.strip() if keywords else "",
                                "business_tags": ",".join(bt_selected),
                                "sensitivity_level": sl,
                                "full_text": text,
                                "source_type": "公开网页导入",
                                "source_url": st.session_state.get("fetch_url", ""),
                                "confirmed": 0,
                                "notes": notes.strip() if notes else "",
                            }
                            doc_id = db.create_document(data)
                            db.log_operation({
                                "action": "网址导入", "target_type": "document",
                                "target_id": doc_id, "file_name": title.strip(),
                                "sensitivity_level": sl,
                            })
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
    from modules.batch_upload_ui import render_batch_upload_ui
    render_batch_upload_ui(uploader_key="policy_file_uploader_lib")


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
        bt_default = classify_business_tags(title, keywords, "")
        bt_selected = st.multiselect("业务类型", BUSINESS_TYPE_OPTIONS, default=bt_default, key="add_bt")
        sl = st.selectbox("敏感级别", SENSITIVITY_LEVEL_OPTIONS, index=0, key="add_sl")
        summary = st.text_area("摘要", height=60)
        full_text = st.text_area("正文全文（可粘贴）", height=120)
        notes = st.text_area("备注", height=60)

        submitted = st.form_submit_button("确认新增")
        if submitted:
            if "涉密禁止上传" in sl:
                st.error("该级别文件禁止上传本系统，请使用单位规定的涉密系统或专用环境处理。")
            elif not title.strip():
                st.error("文件名称不能为空")
            else:
                if not bt_selected:
                    bt_selected = classify_business_tags(title, keywords, full_text)
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
                    "business_tags": ",".join(bt_selected),
                    "sensitivity_level": sl,
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
                        db.log_operation({
                            "action": "手工录入", "target_type": "document",
                            "target_id": doc_id, "file_name": title.strip(),
                            "sensitivity_level": sl,
                        })
                        st.success(f"新增成功！ID: {doc_id}")
                        st.rerun()
                else:
                    doc_id = db.create_document(data)
                    db.log_operation({
                        "action": "手工录入", "target_type": "document",
                        "target_id": doc_id, "file_name": title.strip(),
                        "sensitivity_level": sl,
                    })
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
        if result.get("relation_notes"):
            for note in result["relation_notes"]:
                st.info(note)
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

# --- Tab6: 本地文件夹导入（预解析 → 清单确认 → 入库）---
with tab_folder:
    st.caption("读取运行程序主机电脑上的本地路径，扫描并批量导入政策文件")
    st.info("本功能读取的是运行程序主机电脑上的本地路径。局域网访问者输入自己电脑路径无效。")

    # 初始化 session_state
    for key in ["folder_scan_results", "folder_parse_results", "folder_import_report"]:
        if key not in st.session_state:
            st.session_state[key] = None

    local_dir = st.text_input("文件夹路径", value=DEFAULT_LOCAL_IMPORT_DIR, key="local_import_dir")
    default_sl = st.selectbox("默认敏感级别", SENSITIVITY_LEVEL_OPTIONS[:3], index=0, key="local_default_sl")

    # === 步骤1：扫描文件夹 ===
    col_scan1, col_scan2, col_scan3 = st.columns([1, 1, 4])
    with col_scan1:
        scan_btn = st.button("步骤1：扫描文件夹", key="scan_local_dir")
    with col_scan2:
        clear_scan = st.button("清空扫描结果", key="clear_scan", disabled=not bool(st.session_state.get("folder_scan_results")))

    if clear_scan:
        st.session_state["folder_scan_results"] = None
        st.session_state["folder_parse_results"] = None
        st.session_state["folder_import_report"] = None
        st.rerun()

    if scan_btn:
        if not os.path.isdir(local_dir):
            st.error("文件夹路径不存在或无法访问")
        else:
            supported_exts = {".docx", ".pdf", ".xlsx", ".xls", ".txt"}
            results = []
            for root, dirs, files in os.walk(local_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    full_path = os.path.join(root, f)
                    if ext in supported_exts:
                        size = os.path.getsize(full_path)
                        # 检查是否已入库（按文号和文件名双重检查需要后续预解析）
                        conn = db.get_connection()
                        match = conn.execute(
                            "SELECT id, title FROM documents WHERE file_name = ?", (f,)
                        ).fetchone()
                        conn.close()
                        existing = bool(match)
                        results.append({
                            "file_name": f,
                            "file_path": full_path,
                            "file_size": size,
                            "file_type": ext.lstrip("."),
                            "exists_in_db": existing,
                            "status": "未解析",
                        })
                    elif ext == ".doc":
                        results.append({
                            "file_name": f,
                            "file_path": os.path.join(root, f),
                            "file_size": os.path.getsize(os.path.join(root, f)),
                            "file_type": "doc",
                            "exists_in_db": False,
                            "status": "不支持，请转换 .docx",
                        })
            st.session_state["folder_scan_results"] = results
            st.session_state["folder_parse_results"] = None
            st.session_state["folder_import_report"] = None

    # 显示扫描结果
    scan_results = st.session_state.get("folder_scan_results")
    if scan_results:
        st.markdown(f"共扫描到 **{len(scan_results)}** 个文件")
        df_data = []
        for r in scan_results:
            size_kb = r["file_size"] / 1024
            df_data.append({
                "文件名": r["file_name"],
                "文件路径": r["file_path"],
                "大小(KB)": f"{size_kb:.1f}",
                "类型": r["file_type"],
                "已入库": "是" if r["exists_in_db"] else "否",
                "状态": r["status"],
            })
        st.dataframe(df_data, use_container_width=True, hide_index=True)

    # === 步骤2：批量预解析 ===
    if scan_results:
        st.markdown("---")
        col_parse1, col_parse2 = st.columns([2, 4])
        with col_parse1:
            parse_btn = st.button("步骤2：批量预解析", key="batch_pre_parse", type="primary")
        if parse_btn:
            import_count = 0
            fail_count = 0
            skip_count = 0
            parse_results = []
            progress = st.progress(0, "正在预解析...")
            total = len(scan_results)

            for i, item in enumerate(scan_results):
                progress.progress((i + 1) / total, f"预解析中 ({i+1}/{total}): {item['file_name']}")
                if item["status"].startswith("不支持"):
                    skip_count += 1
                    parse_results.append({
                        **item,
                        "title": "",
                        "document_no": "",
                        "issuing_authority": "",
                        "publish_date": "",
                        "category": "",
                        "business_type": "",
                        "sensitivity_level": default_sl,
                        "title_quality": "不支持格式",
                        "suggestion": "不支持格式",
                        "is_duplicate": False,
                        "recommend_import": False,
                        "fail_reason": item["status"],
                        "full_text": "",
                    })
                    continue
                try:
                    text = parse_file(item["file_path"], pdf_max_pages=30)
                    meta = extract_all_metadata(text, file_name=item["file_name"])
                    title = meta.get("title", "")
                    doc_no = meta.get("document_no") or ""

                    # 标题质量校验
                    validation = validate_import_candidate(
                        title=title, document_no=doc_no, text=text, file_name=item["file_name"],
                    )

                    # 附件标题检查
                    is_att, att_reason = is_attachment_title(title)

                    # 重复检查
                    dup_check = db.check_duplicate(
                        title=title, document_no=doc_no,
                        file_name=item["file_name"], file_size=item["file_size"],
                        full_text=text,
                    )

                    recommend = validation["valid"] and not dup_check["is_duplicate"] and not is_att

                    # 标题候选信息
                    title_score = meta.get("title_score", 0)
                    title_source = meta.get("title_source", "")
                    title_candidates = meta.get("title_candidates", [])
                    other_candidates = [c["title"][:40] for c in title_candidates[1:4] if c["title"] != title]
                    doc_no_source = meta.get("document_no_source", "")

                    parse_results.append({
                        **item,
                        "title": title,
                        "document_no": doc_no,
                        "issuing_authority": meta.get("issuing_authority", ""),
                        "publish_date": meta.get("publish_date", ""),
                        "effective_date": meta.get("effective_date", ""),
                        "status_field": meta.get("status", "待核实"),
                        "category": classify_document(title, doc_no, text),
                        "business_type": "",
                        "sensitivity_level": default_sl,
                        "title_quality": validation["level"],
                        "suggestion": validation.get("suggestion", ""),
                        "quality_reason": validation["reason"],
                        "is_duplicate": dup_check["is_duplicate"],
                        "dup_reason": dup_check["reason"],
                        "recommend_import": recommend,
                        "fail_reason": "",
                        "full_text": text,
                        "keywords": meta.get("keywords", ""),
                        # 新增候选信息字段
                        "title_score": title_score,
                        "title_source": title_source,
                        "other_candidates": other_candidates,
                        "is_attachment_title": is_att,
                        "attachment_title_reason": att_reason,
                        "doc_no_source": doc_no_source,
                    })
                    import_count += 1
                except Exception as e:
                    fail_count += 1
                    parse_results.append({
                        **item,
                        "title": "",
                        "document_no": "",
                        "issuing_authority": "",
                        "publish_date": "",
                        "category": "",
                        "business_type": "",
                        "sensitivity_level": default_sl,
                        "title_quality": "解析失败",
                        "suggestion": "",
                        "is_duplicate": False,
                        "recommend_import": False,
                        "fail_reason": str(e),
                        "full_text": "",
                    })
            progress.empty()
            st.success(f"预解析完成：成功 {import_count}，失败 {fail_count}，跳过 {skip_count}")
            st.session_state["folder_parse_results"] = parse_results
            st.rerun()

    # === 步骤3：清单确认 → 入库 ===
    parse_results = st.session_state.get("folder_parse_results")
    if parse_results:
        st.markdown("---")
        st.subheader(f"预解析候选清单（共 {len(parse_results)} 条）")

        # 统计
        can_import = sum(1 for r in parse_results if r.get("title_quality") == "可入库")
        need_confirm = sum(1 for r in parse_results if r.get("title_quality") == "待人工确认")
        not_recommend = sum(1 for r in parse_results if r.get("title_quality") == "不建议入库")
        parse_fail = sum(1 for r in parse_results if r.get("title_quality") == "解析失败")
        dup_count = sum(1 for r in parse_results if r.get("is_duplicate"))
        unsupported = sum(1 for r in parse_results if r.get("title_quality") == "不支持格式")

        col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
        col_a.metric("可入库", can_import)
        col_b.metric("待人工确认", need_confirm)
        col_c.metric("不建议入库", not_recommend)
        col_d.metric("重复", dup_count)
        col_e.metric("解析失败", parse_fail)
        col_f.metric("不支持", unsupported)

        # 构建候选清单 dataframe
        list_data = []
        for idx, r in enumerate(parse_results):
            q = r.get("title_quality", "")
            dup_mark = "⚠️重复" if r.get("is_duplicate") else ""
            file_status = normalize_document_status(r.get("status_field", "待核实"))
            is_att = r.get("is_attachment_title", False)
            att_mark = "⚠️疑似附件" if is_att else ""
            other_titles = "; ".join(r.get("other_candidates", []))
            list_data.append({
                "序号": idx + 1,
                "文件名": r["file_name"],
                "识别标题": r.get("title", "")[:30],
                "识别文号": r.get("document_no", ""),
                "发文单位": r.get("issuing_authority", ""),
                "发布日期": r.get("publish_date", ""),
                "文件状态": file_status,
                "文件类别": r.get("category", ""),
                "标题质量": q,
                "标题来源": r.get("title_source", ""),
                "标题得分": r.get("title_score", 0),
                "附件标题": att_mark,
                "其他候选": other_candidates[:60],
                "重复": dup_mark,
                "是否建议入库": "是" if r.get("recommend_import") else "否",
                "建议": r.get("suggestion", "")[:30],
            })
        st.dataframe(list_data, use_container_width=True, hide_index=True, height=300)

        # 勾选入库
        st.markdown("**勾选要导入的文件：**")
        if "import_checklist" not in st.session_state:
            st.session_state["import_checklist"] = {}

        # 快捷按钮
        cb_col1, cb_col2, cb_col3 = st.columns(3)
        with cb_col1:
            if st.button("仅勾选「可入库」", key="check_can_import"):
                for idx, r in enumerate(parse_results):
                    if r.get("title_quality") == "可入库":
                        st.session_state["import_checklist"][str(idx)] = True
                    else:
                        st.session_state["import_checklist"][str(idx)] = False
                st.rerun()
        with cb_col2:
            if st.button("也勾选「待人工确认」", key="check_manual"):
                for idx, r in enumerate(parse_results):
                    if r.get("title_quality") in ("可入库", "待人工确认"):
                        st.session_state["import_checklist"][str(idx)] = True
                st.rerun()
        with cb_col3:
            if st.button("全部取消", key="uncheck_all"):
                st.session_state["import_checklist"] = {}
                st.rerun()

        for idx, r in enumerate(parse_results):
            q = r.get("title_quality", "")
            can_check = q in ("可入库", "待人工确认")
            is_dup = r.get("is_duplicate")

            col_cb, col_info = st.columns([0.5, 9.5])
            with col_cb:
                key = str(idx)
                default_val = (q == "可入库" and not is_dup)
                current_val = st.session_state["import_checklist"].get(key, default_val)
                checked = st.checkbox(
                    "",
                    value=current_val,
                    key=f"imp_cb_{idx}",
                    disabled=not can_check,
                    label_visibility="collapsed",
                )
                st.session_state["import_checklist"][key] = checked
            with col_info:
                dup_info = f" 🔄{r.get('dup_reason', '')}" if is_dup else ""
                fail_info = f" ❌{r.get('fail_reason', '')}" if r.get("fail_reason") else ""
                att_info = f" ⚠️疑似附件: {r.get('attachment_title_reason', '')}" if r.get("is_attachment_title") else ""
                score_info = f" 得分:{r.get('title_score', 0)}" if r.get("title_score") else ""
                source_info = f" 来源:{r.get('title_source', '')}" if r.get("title_source") else ""
                st.markdown(
                    f"**{r['file_name']}** → {r.get('title', '（未识别）')[:40]} "
                    f"| :{'green' if q == '可入库' else 'orange' if q == '待人工确认' else 'red'}[{q}]"
                    f"{score_info}{source_info}{att_info}{dup_info}{fail_info}"
                )

            # 可修改元数据
            if checked:
                with st.expander(f"修改元数据 - {r['file_name'][:40]}"):
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        new_title = st.text_input("标题", value=r.get("title", ""), key=f"mt_{idx}")
                        new_doc_no = st.text_input("文号", value=r.get("document_no", ""), key=f"mdn_{idx}")
                    with mc2:
                        # 自动分类建议的业务类型
                        auto_bt = classify_business_tags(
                            new_title or r.get("title", ""),
                            r.get("keywords", ""),
                            r.get("full_text", ""),
                        )
                        new_bt = st.multiselect(
                            "业务类型",
                            BUSINESS_TYPE_OPTIONS,
                            default=auto_bt,
                            key=f"mbt_{idx}"
                        )
                        new_sl = st.selectbox("敏感级别", SENSITIVITY_LEVEL_OPTIONS,
                            index=SENSITIVITY_LEVEL_OPTIONS.index(default_sl) if default_sl in SENSITIVITY_LEVEL_OPTIONS else 0,
                            key=f"msl_{idx}")

        # 确认导入按钮
        st.markdown("---")
        selected_indices = [int(k) for k, v in st.session_state["import_checklist"].items() if v]
        st.info(f"已勾选 **{len(selected_indices)}** 个文件待导入")

        imp_col1, imp_col2 = st.columns([2, 5])
        with imp_col1:
            if st.button("步骤3：确认导入选中文件", type="primary", key="confirm_import_selected",
                         disabled=len(selected_indices) == 0):
                if not selected_indices:
                    st.error("请至少勾选一个文件")
                else:
                    import_report = {"success": 0, "failed": 0, "skipped": 0, "duplicate": 0,
                                    "manual_confirm": 0, "not_recommended": 0, "details": []}
                    progress = st.progress(0, "正在导入...")
                    for i, idx in enumerate(sorted(selected_indices)):
                        progress.progress((i + 1) / len(selected_indices),
                            f"导入中 ({i+1}/{len(selected_indices)})")
                        r = parse_results[idx]
                        q = r.get("title_quality", "")
                        status = "跳过"
                        doc_id = None

                        try:
                            if q == "不建议入库":
                                import_report["not_recommended"] += 1
                                status = "不建议入库"
                                import_report["details"].append({
                                    "file_name": r["file_name"], "file_path": r["file_path"],
                                    "title": r.get("title", ""), "document_no": r.get("document_no", ""),
                                    "issuing_authority": r.get("issuing_authority", ""),
                                    "category": r.get("category", ""),
                                    "business_type": r.get("business_type", ""),
                                    "sensitivity_level": r.get("sensitivity_level", ""),
                                    "status": status, "fail_reason": q, "suggestion": r.get("suggestion", ""),
                                    "document_id": None,
                                })
                                continue

                            if r.get("is_duplicate"):
                                import_report["duplicate"] += 1
                                status = "重复"
                                import_report["details"].append({
                                    "file_name": r["file_name"], "file_path": r["file_path"],
                                    "title": r.get("title", ""), "document_no": r.get("document_no", ""),
                                    "issuing_authority": r.get("issuing_authority", ""),
                                    "category": r.get("category", ""),
                                    "business_type": r.get("business_type", ""),
                                    "sensitivity_level": r.get("sensitivity_level", ""),
                                    "status": status, "fail_reason": r.get("dup_reason", "重复"),
                                    "suggestion": "允许覆盖更新或保留为新记录", "document_id": None,
                                })
                                continue

                            title = r.get("title", "")
                            doc_no = r.get("document_no", "")

                            # 检查用户是否修改了元数据
                            if st.session_state["import_checklist"].get(str(idx)):
                                user_title = st.session_state.get(f"mt_{idx}")
                                if user_title and user_title != title:
                                    title = user_title
                                user_doc_no = st.session_state.get(f"mdn_{idx}")
                                if user_doc_no and user_doc_no != doc_no:
                                    doc_no = user_doc_no

                            bt_tags_list = st.session_state.get(f"mbt_{idx}", [])
                            sl = st.session_state.get(f"msl_{idx}", default_sl)

                            # 业务标签
                            if not bt_tags_list:
                                auto_bt = classify_business_tags(title, r.get("keywords", ""), r.get("full_text", ""))
                                bt_tags_list = auto_bt
                            bt_tags = ",".join(bt_tags_list) if isinstance(bt_tags_list, list) else bt_tags_list

                            # 保存原文件
                            file_path = ""
                            if SAVE_POLICY_FILE:
                                dest_name = f"{uuid.uuid4().hex}_{r['file_name']}"
                                dest = os.path.join(POLICY_FILES_DIR, dest_name)
                                import shutil
                                shutil.copy2(r["file_path"], dest)
                                file_path = dest

                            data = {
                                "title": title,
                                "document_no": doc_no,
                                "issuing_authority": r.get("issuing_authority", ""),
                                "publish_date": r.get("publish_date", ""),
                                "effective_date": r.get("effective_date", ""),
                                "status": normalize_document_status(r.get("status_field", "待核实")),
                                "region": "全国",
                                "category": r.get("category", "其他"),
                                "keywords": r.get("keywords", ""),
                                "business_tags": bt_tags,
                                "sensitivity_level": sl,
                                "file_name": r["file_name"],
                                "file_size": r["file_size"],
                                "file_type": r["file_type"],
                                "full_text": r.get("full_text", ""),
                                "source_type": "本地文件夹导入",
                                "file_path": file_path,
                                "confirmed": 0 if q == "待人工确认" else 1,
                            }
                            doc_id = db.create_document(data)
                            db.log_operation({
                                "action": "本地文件夹批量导入",
                                "target_type": "document",
                                "target_id": doc_id,
                                "file_name": r["file_name"],
                                "sensitivity_level": sl,
                                "notes": f"从 {local_dir} 导入，标题质量: {q}",
                            })
                            import_report["success"] += 1
                            status = "成功"
                        except Exception as e:
                            import_report["failed"] += 1
                            status = "失败"
                            import_report["details"].append({
                                "file_name": r["file_name"], "file_path": r["file_path"],
                                "title": r.get("title", ""), "document_no": r.get("document_no", ""),
                                "issuing_authority": r.get("issuing_authority", ""),
                                "category": r.get("category", ""),
                                "business_type": r.get("business_type", ""),
                                "sensitivity_level": r.get("sensitivity_level", ""),
                                "status": status, "fail_reason": str(e),
                                "suggestion": "", "document_id": doc_id,
                            })
                        import_report["details"].append({
                            "file_name": r["file_name"], "file_path": r["file_path"],
                            "title": title if status == "成功" else r.get("title", ""),
                            "document_no": r.get("document_no", ""),
                            "issuing_authority": r.get("issuing_authority", ""),
                            "category": r.get("category", ""),
                            "business_type": r.get("business_type", ""),
                            "sensitivity_level": r.get("sensitivity_level", ""),
                            "status": status,
                            "fail_reason": r.get("fail_reason", ""),
                            "suggestion": r.get("suggestion", ""),
                            "document_id": doc_id,
                        })

                    progress.empty()
                    st.session_state["folder_import_report"] = import_report
                    st.session_state["import_checklist"] = {}
                    st.success(
                        f"导入完成：成功 {import_report['success']}，失败 {import_report['failed']}，"
                        f"跳过 {import_report['skipped']}，重复 {import_report['duplicate']}，"
                        f"待人工确认 {import_report['manual_confirm']}，"
                        f"不建议入库 {import_report['not_recommended']}"
                    )
                    st.rerun()

    # 显示导入报告
    import_report = st.session_state.get("folder_import_report")
    if import_report:
        st.markdown("---")
        st.subheader("导入情况清单")

        ir_col1, ir_col2, ir_col3, ir_col4 = st.columns(4)
        ir_col1.metric("成功", import_report["success"])
        ir_col2.metric("失败", import_report["failed"])
        ir_col3.metric("跳过", import_report["skipped"])
        ir_col4.metric("重复", import_report["duplicate"])

        if import_report.get("details"):
            # 构建清单表格
            detail_rows = []
            for i, d in enumerate(import_report["details"], 1):
                detail_rows.append({
                    "序号": i,
                    "文件名": d.get("file_name", ""),
                    "文件路径": d.get("file_path", ""),
                    "识别标题": d.get("title", ""),
                    "识别文号": d.get("document_no", ""),
                    "发文单位": d.get("issuing_authority", ""),
                    "文件类别": d.get("category", ""),
                    "业务类型": d.get("business_type", ""),
                    "敏感级别": d.get("sensitivity_level", ""),
                    "入库状态": d.get("status", ""),
                    "失败原因": d.get("fail_reason", ""),
                    "处理建议": d.get("suggestion", ""),
                    "document_id": d.get("document_id", ""),
                })
            st.dataframe(detail_rows, use_container_width=True, hide_index=True, height=300)

            # 导出导入清单 Excel
            import io
            import pandas as pd
            df_export = pd.DataFrame(import_report["details"])
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df_export.to_excel(writer, index=False, sheet_name="导入清单")
            st.download_button(
                "导出导入情况清单 Excel",
                data=excel_buffer.getvalue(),
                file_name=f"导入情况清单_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_import_report",
            )

        # 清空按钮
        if st.button("清空导入结果", key="clear_import_report"):
            st.session_state["folder_scan_results"] = None
            st.session_state["folder_parse_results"] = None
            st.session_state["folder_import_report"] = None
            st.session_state["import_checklist"] = {}
            st.rerun()

# ═══════════ 文件列表 ═══════════
st.markdown("---")
st.subheader("政策文件列表")

# 分页参数
if "page_size" not in st.session_state:
    st.session_state["page_size"] = 50
if "current_page" not in st.session_state:
    st.session_state["current_page"] = 1

page_size_opts = [20, 50, 100]
col_ps, col_pn = st.columns([1, 5])
with col_ps:
    st.session_state["page_size"] = st.selectbox(
        "每页条数", page_size_opts,
        index=page_size_opts.index(st.session_state["page_size"])
        if st.session_state["page_size"] in page_size_opts else 1,
        key="page_size_select",
    )
    # 切换每页条数时重置到第1页
    if st.session_state.get("_prev_page_size", 50) != st.session_state["page_size"]:
        st.session_state["current_page"] = 1
    st.session_state["_prev_page_size"] = st.session_state["page_size"]

_stat_kw = keyword
_stat_st = "" if status_filter == "全部" else status_filter
_stat_rg = "" if region_filter == "全部" else region_filter
_stat_cat = "" if category_filter == "全部" else category_filter
_stat_bt = "" if bt_filter == "全部" else bt_filter
_stat_ts = title_status_filter  # "全部" / "正常标题" / "标题异常"

total_count = db.count_documents(_stat_kw, _stat_st, _stat_rg, _stat_cat, _stat_bt)
# 标题异常筛选时使用过滤后的 count
if _stat_ts in ("正常标题", "标题异常"):
    # 获取全量数据统计（简化：最多拉 5000 条做 Python 过滤）
    _all_for_count = db.search_documents(
        keyword=_stat_kw, status=_stat_st, region=_stat_rg,
        category=_stat_cat, business_type=_stat_bt, limit=5000, offset=0,
    )
    if _stat_ts == "标题异常":
        _all_for_count = [d for d in _all_for_count if detect_invalid_title(d.get("title", ""))]
    else:
        _all_for_count = [d for d in _all_for_count if not detect_invalid_title(d.get("title", ""))]
    total_count = len(_all_for_count)
total_pages = max(1, (total_count + st.session_state["page_size"] - 1) // st.session_state["page_size"])
if st.session_state["current_page"] > total_pages:
    st.session_state["current_page"] = total_pages
offset = (st.session_state["current_page"] - 1) * st.session_state["page_size"]

# 统计概览（紧凑摘要栏）
stats = db.get_document_stats(_stat_kw, _stat_st, _stat_rg, _stat_cat, _stat_bt)
valid_count = stats["by_status"].get("现行有效", 0)
pending_count = stats["by_status"].get("待核实", 0)
abolished_count = stats["by_status"].get("已废止", 0) + stats["by_status"].get("已失效", 0)
public_count = stats["by_sensitivity"].get("公开", 0)
internal_count = stats["by_sensitivity"].get("内部", 0) + stats["by_sensitivity"].get("敏感", 0)

bt_line = ""
if _stat_bt:
    bt_line = f"<span>业务类型：<b>{_stat_bt}</b></span>　"

st.markdown(
    f"""
    <div style="padding:8px 14px;border:1px solid #e5e7eb;border-radius:8px;background:#f9fafb;font-size:13px;line-height:1.8;">
    <b>当前筛选：</b>共 {total_count} 份
    {bt_line}
    <span>现行有效：{valid_count}</span>
    <span>待核实：{pending_count}</span>
    <span>废止/失效：{abolished_count}</span>
    <span>公开：{public_count}</span>
    <span>内部/敏感：{internal_count}</span>
    <span>有原文件：{stats['with_file']}</span>
    <span>无原文件：{stats['without_file']}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# 非标准状态检查（仅在 >0 时显示，含清理按钮）
standard_set = {"现行有效", "已废止", "已失效", "被替代", "部分废止", "即将失效", "待核实", "不明"}
non_standard_count = sum(
    cnt for st_name, cnt in stats["by_status"].items()
    if st_name not in standard_set
)
if non_standard_count > 0:
    ns_col1, ns_col2 = st.columns([3, 1])
    with ns_col1:
        st.warning(f"发现 **{non_standard_count}** 条非标准文件状态，建议执行数据库迁移清理。")
    with ns_col2:
        if st.button("执行状态清理", key="clean_status_btn"):
            result = db.clean_document_statuses()
            st.success(f"已清理 {result['updated']} 条状态")
            time.sleep(0.5)
            st.rerun()

# 详细统计（默认折叠）
with st.expander("查看详细统计", expanded=False):
    if stats.get("by_business_type"):
        st.markdown("**业务类型分布**")
        bt_sorted = sorted(stats["by_business_type"].items(), key=lambda x: x[1], reverse=True)
        bt_data = [{"业务类型": k, "文件数量": v} for k, v in bt_sorted]
        st.dataframe(bt_data, use_container_width=True, hide_index=True, height=min(35 * len(bt_data) + 38, 300))
    if stats.get("by_status"):
        st.markdown("**状态分布**")
        st_sorted = sorted(stats["by_status"].items(), key=lambda x: x[1], reverse=True)
        st_data = [{"状态": k, "数量": v} for k, v in st_sorted]
        st.dataframe(st_data, use_container_width=True, hide_index=True, height=min(35 * len(st_data) + 38, 200))
    if stats.get("by_sensitivity"):
        st.markdown("**敏感级别分布**")
        sl_sorted = sorted(stats["by_sensitivity"].items(), key=lambda x: x[1], reverse=True)
        sl_data = [{"敏感级别": k, "数量": v} for k, v in sl_sorted]
        st.dataframe(sl_data, use_container_width=True, hide_index=True)

st.caption(f"第 {st.session_state['current_page']} / {total_pages} 页，共 {total_count} 条记录")

# ═══════ 批量删除区域（页面顶部统一处理） ═══════
# 初始化
if "pending_delete_ids" not in st.session_state:
    st.session_state["pending_delete_ids"] = set()
if "show_delete_confirm" not in st.session_state:
    st.session_state["show_delete_confirm"] = False
if "selected_ids" not in st.session_state:
    st.session_state["selected_ids"] = set()

# 跟踪筛选条件，变化时清空选中
_filter_key = f"{_stat_kw}|{_stat_st}|{_stat_rg}|{_stat_cat}|{_stat_bt}|{st.session_state['current_page']}|{_stat_ts}"
if st.session_state.get("_last_filter_key", "") != _filter_key:
    st.session_state["selected_ids"] = set()
    st.session_state["_last_filter_key"] = _filter_key

# 获取当前页数据（标题异常筛选需要查更多数据后 Python 过滤）
_fetch_limit = st.session_state["page_size"] * 5 if _stat_ts in ("正常标题", "标题异常") else st.session_state["page_size"]
_fetch_offset = 0 if _stat_ts in ("正常标题", "标题异常") else offset
docs_raw = db.search_documents(
    keyword=_stat_kw,
    status=_stat_st,
    region=_stat_rg,
    category=_stat_cat,
    business_type=_stat_bt,
    limit=_fetch_limit,
    offset=_fetch_offset,
)

# 标题状态过滤（Python 层面）
if _stat_ts == "标题异常":
    docs_raw = [d for d in docs_raw if detect_invalid_title(d.get("title", ""))]
elif _stat_ts == "正常标题":
    docs_raw = [d for d in docs_raw if not detect_invalid_title(d.get("title", ""))]

# 重新分页
if _stat_ts in ("正常标题", "标题异常"):
    total_count = len(docs_raw)
    docs = docs_raw[offset:offset + st.session_state["page_size"]]
else:
    docs = docs_raw

current_page_ids = [doc["id"] for doc in docs]

# 批量操作按钮（在 docs 查询之后）
col_batch1, col_batch2, col_batch3, col_batch4, col_batch5 = st.columns([1, 1, 1, 1, 4])
with col_batch1:
    if st.button("✅ 全选本页", key="select_all_page", use_container_width=True):
        st.session_state["selected_ids"].update(current_page_ids)
        st.rerun()
with col_batch2:
    if st.button("❎ 取消本页", key="deselect_page", use_container_width=True):
        st.session_state["selected_ids"].difference_update(current_page_ids)
        st.rerun()
with col_batch3:
    if st.button("🗑 清空全部", key="clear_all_selection", use_container_width=True):
        st.session_state["selected_ids"] = set()
        st.rerun()
with col_batch4:
    sel_count = len(st.session_state["selected_ids"])
    if st.button(f"批量删除({sel_count})" if sel_count > 0 else "批量删除",
                 key="batch_delete_btn", type="primary" if sel_count > 0 else "secondary",
                 disabled=sel_count == 0, use_container_width=True):
        st.session_state["show_delete_confirm"] = True
        st.rerun()
with col_batch5:
    if st.button(f"批量重新解析({sel_count})" if sel_count > 0 else "批量重新解析元数据",
                 key="batch_reparse_btn", type="secondary",
                 disabled=sel_count == 0, use_container_width=True):
        st.session_state["show_reparse_confirm"] = True
        st.rerun()

# 批量删除确认对话框（含文件清单预览）
if st.session_state["show_delete_confirm"] and st.session_state["selected_ids"]:
    st.markdown("---")
    with st.container(border=True):
        st.warning(f"⚠️ 即将删除 **{len(st.session_state['selected_ids'])}** 条文件记录，请确认是否继续。")

        # 被删除文件清单预览
        preview_ids = list(st.session_state["selected_ids"])
        preview_data = []
        for pid in preview_ids[:50]:  # 最多预览50条
            pd_doc = db.get_document(pid)
            if pd_doc:
                has_file = "是" if (pd_doc.get("file_path") and os.path.isfile(pd_doc.get("file_path", ""))) else "否"
                preview_data.append({
                    "文件名称": pd_doc.get("title", "")[:30],
                    "文号": pd_doc.get("document_no", ""),
                    "文件状态": pd_doc.get("status", ""),
                    "敏感级别": pd_doc.get("sensitivity_level", ""),
                    "有原文件": has_file,
                })
        if preview_data:
            st.dataframe(preview_data, use_container_width=True, hide_index=True, height=min(200, 35 * len(preview_data) + 38))
        if len(preview_ids) > 50:
            st.caption(f"... 还有 {len(preview_ids) - 50} 条未显示")

        st.markdown("**请选择删除方式：**")
        del_col1, del_col2, del_col3 = st.columns([2, 2, 2])
        with del_col1:
            if st.button("仅删除数据库记录", key="del_db_only", type="primary"):
                result = db.batch_delete_documents(preview_ids, delete_files=False)
                st.success(f"已删除 {result['deleted']} 条记录")
                if result["errors"]:
                    for e in result["errors"][:10]:
                        st.caption(f"- {e}")
                st.session_state["selected_ids"] = set()
                st.session_state["show_delete_confirm"] = False
                st.session_state["pending_delete_ids"] = set()
                time.sleep(0.5)
                st.rerun()
        with del_col2:
            if st.button("同时删除原文件", key="del_with_files"):
                result = db.batch_delete_documents(preview_ids, delete_files=True)
                st.success(f"已删除 {result['deleted']} 条记录（含原文件）")
                if result["errors"]:
                    for e in result["errors"][:10]:
                        st.caption(f"- {e}")
                st.session_state["selected_ids"] = set()
                st.session_state["show_delete_confirm"] = False
                st.session_state["pending_delete_ids"] = set()
                time.sleep(0.5)
                st.rerun()
        with del_col3:
            if st.button("取消", key="del_cancel"):
                st.session_state["show_delete_confirm"] = False
                st.rerun()

# 批量重新解析确认对话框
if st.session_state.get("show_reparse_confirm") and st.session_state["selected_ids"]:
    st.markdown("---")
    with st.container(border=True):
        st.info(f"即将对 **{len(st.session_state['selected_ids'])}** 个文件重新解析元数据。")
        st.markdown("""
        **重新解析流程：**
        1. 重新读取原文件并提取元数据
        2. 显示新旧结果对比
        3. 用户确认后再更新
        4. 不会自动覆盖已有人工确认的字段
        """)

        reparse_col1, reparse_col2 = st.columns([2, 3])
        with reparse_col1:
            if st.button("开始批量重新解析", key="start_batch_reparse", type="primary"):
                preview_ids = list(st.session_state["selected_ids"])
                reparse_results = []
                progress = st.progress(0, "正在重新解析...")

                for i, pid in enumerate(preview_ids):
                    progress.progress((i + 1) / len(preview_ids), f"重新解析中 ({i+1}/{len(preview_ids)})")
                    doc_item = db.get_document(pid)
                    if not doc_item:
                        continue

                    fp = doc_item.get("file_path", "")
                    if not fp or not os.path.isfile(fp):
                        reparse_results.append({
                            "doc_id": pid,
                            "title": doc_item.get("title", ""),
                            "error": "无原文件",
                            "new_title": "",
                            "new_doc_no": "",
                            "changes": [],
                        })
                        continue

                    try:
                        structured = parse_file_with_structure(fp)
                        new_meta = extract_all_metadata(structured["full_text"])
                        old_title = doc_item.get("title", "")
                        new_title = new_meta.get("title", "")
                        old_doc_no = doc_item.get("document_no", "") or ""
                        new_doc_no = new_meta.get("document_no") or ""

                        changes = []
                        if old_title != new_title:
                            changes.append(("标题", old_title[:60], new_title[:60]))
                        if old_doc_no != new_doc_no:
                            changes.append(("文号", old_doc_no, new_doc_no))

                        reparse_results.append({
                            "doc_id": pid,
                            "title": old_title,
                            "error": "",
                            "new_title": new_title,
                            "new_doc_no": new_doc_no,
                            "new_authority": new_meta.get("issuing_authority", ""),
                            "new_publish_date": new_meta.get("publish_date", ""),
                            "title_source": new_meta.get("title_source", ""),
                            "title_confidence": new_meta.get("title_confidence", ""),
                            "title_score": new_meta.get("title_score", 0),
                            "changes": changes,
                        })
                    except Exception as e:
                        reparse_results.append({
                            "doc_id": pid,
                            "title": doc_item.get("title", ""),
                            "error": str(e),
                            "new_title": "",
                            "new_doc_no": "",
                            "changes": [],
                        })

                progress.empty()
                st.session_state["reparse_results"] = reparse_results
                st.session_state["show_reparse_results"] = True
                st.session_state["show_reparse_confirm"] = False
                st.rerun()

        with reparse_col2:
            if st.button("取消", key="reparse_cancel"):
                st.session_state["show_reparse_confirm"] = False
                st.rerun()

# 批量重新解析结果展示
if st.session_state.get("show_reparse_results") and st.session_state.get("reparse_results"):
    st.markdown("---")
    reparse_results = st.session_state["reparse_results"]
    success_count = sum(1 for r in reparse_results if not r.get("error"))
    error_count = sum(1 for r in reparse_results if r.get("error"))
    changed_count = sum(1 for r in reparse_results if r.get("changes"))

    st.subheader(f"重新解析结果：成功 {success_count}，有变化 {changed_count}，失败 {error_count}")

    compare_data = []
    for r in reparse_results:
        changes_str = "; ".join(f"{c[0]}: {c[1][:20]} → {c[2][:20]}" for c in r.get("changes", []))
        compare_data.append({
            "文件": r["title"][:30],
            "新标题": r.get("new_title", "")[:40] or r.get("error", ""),
            "新文号": r.get("new_doc_no", ""),
            "标题来源": r.get("title_source", ""),
            "置信度": r.get("title_confidence", ""),
            "变化": changes_str if changes_str else "无变化",
            "错误": r.get("error", ""),
        })

    st.dataframe(compare_data, use_container_width=True, hide_index=True, height=min(300, 35 * len(compare_data) + 38))

    # 确认更新
    st.markdown("**请选择操作：**")
    update_col1, update_col2, update_col3 = st.columns([2, 2, 3])
    with update_col1:
        if st.button("确认更新有变化的文件", key="confirm_batch_reparse", type="primary",
                     disabled=changed_count == 0):
            updated = 0
            for r in reparse_results:
                if r.get("changes") and not r.get("error"):
                    update_fields = {}
                    for change in r["changes"]:
                        field_name = change[0]
                        new_val = change[2]
                        if field_name == "标题":
                            update_fields["title"] = new_val
                        elif field_name == "文号":
                            update_fields["document_no"] = new_val
                    if update_fields:
                        db.update_document(r["doc_id"], update_fields)
                        updated += 1
            db.log_operation({
                "action": "批量重新解析元数据",
                "target_type": "document",
                "notes": f"共重新解析 {success_count} 个文件，更新 {updated} 个",
            })
            st.success(f"已更新 {updated} 个文件的元数据")
            st.session_state["selected_ids"] = set()
            st.session_state["show_reparse_results"] = False
            st.session_state["reparse_results"] = None
            time.sleep(1)
            st.rerun()
    with update_col2:
        if st.button("保留当前值不更新", key="skip_batch_reparse"):
            st.info("已保留所有文件的当前元数据")
            st.session_state["selected_ids"] = set()
            st.session_state["show_reparse_results"] = False
            st.session_state["reparse_results"] = None
            st.rerun()
    with update_col3:
        st.caption("仅更新有变化的字段。不会覆盖人工确认的状态。")

# 渲染文件列表（不在循环中直接删除）
for doc in docs:
    doc_id = doc["id"]
    with st.container():
        col_cb, col1, col2, col3 = st.columns([0.5, 4, 2, 1.5])
        with col_cb:
            # 复选框状态完全由 selected_ids 驱动
            is_selected = doc_id in st.session_state["selected_ids"]
            checked = st.checkbox(
                "",
                value=is_selected,
                key=f"sel_doc_{doc_id}",
                label_visibility="collapsed",
            )
            # 双向同步：checkbox 变化时更新 selected_ids
            if checked and not is_selected:
                st.session_state["selected_ids"].add(doc_id)
            elif not checked and is_selected:
                st.session_state["selected_ids"].discard(doc_id)
        with col1:
            raw_title = doc.get("title", "")
            display_title = get_display_title(raw_title)
            is_invalid = detect_invalid_title(raw_title) if raw_title else True

            if is_invalid:
                st.markdown(
                    f"<span style='color:#d32f2f;font-weight:bold;'>【未识别标题，请补录】</span> "
                    f"<span style='background:#ffcdd2;color:#b71c1c;padding:1px 6px;border-radius:4px;font-size:0.75em;'>标题异常</span>",
                    unsafe_allow_html=True,
                )
                if raw_title:
                    st.caption(f"原标题: {raw_title[:60]}")
            else:
                st.markdown(f"**《{display_title}》**")
            info_parts = []
            if doc["document_no"]:
                info_parts.append(doc["document_no"])
            if doc["issuing_authority"]:
                info_parts.append(doc["issuing_authority"])
            st.caption(" | ".join(info_parts))
            bt = doc.get("business_tags", "")
            if bt:
                tags = [t.strip() for t in bt.split(",") if t.strip()]
                tag_html = " ".join(
                    f"<span style='background:#e8f0fe;color:#1a73e8;padding:2px 6px;border-radius:4px;font-size:0.8em;margin-right:2px;'>{t}</span>"
                    for t in tags[:5]
                )
                st.markdown(tag_html, unsafe_allow_html=True)
        with col2:
            display_status = normalize_document_status(doc.get("status", ""))
            status_color = {
                "现行有效": "green", "已废止": "red", "已失效": "red",
                "被替代": "orange", "部分废止": "orange", "即将失效": "orange",
            }
            color = status_color.get(display_status, "grey")
            sl = doc.get("sensitivity_level", "")
            sl_icon = {"公开": "", "内部": "🔒", "敏感": "⚠️"}.get(sl, "")
            st.markdown(f":{color}[{display_status}] {sl_icon}")
        with col3:
            if st.button("查看", key=f"view_{doc_id}"):
                st.session_state["view_doc_id"] = doc_id
                st.rerun()
    st.markdown("---")

# ═══════════ 标题异常清理 ═══════════
st.markdown("---")
st.subheader("🧹 标题异常清理")

with st.expander("扫描并清理标题异常的记录", expanded=False):
    st.markdown("""
    **标题异常包括：**
    - 标题为空
    - 标题为《》或只含标点
    - 标题为【未识别标题，请补录】或"未识别"
    - 标题包含 PDF 解析提示
    - 标题明显为附件/材料清单
    """)

    from modules.rule_engine import detect_invalid_title

    if st.button("🔍 扫描标题异常记录", key="scan_anomaly"):
        with st.spinner("正在扫描..."):
            all_docs = db.search_documents(limit=5000, offset=0)
            anomaly_docs = []
            for d in all_docs:
                title = d.get("title", "")
                is_invalid = detect_invalid_title(title) if title else True
                if is_invalid:
                    reason_parts = []
                    if not title:
                        reason_parts.append("标题为空")
                    elif title in ("《》", "未识别", "未识别标题", "无标题"):
                        reason_parts.append(f"标题为'{title}'")
                    elif title == "【未识别标题，请补录】":
                        reason_parts.append("系统默认占位标题")
                    elif any(h in title for h in ["PDF共", "仅展示前", "仅显示前", "完整内容将"]):
                        reason_parts.append("包含PDF解析提示")
                    else:
                        from modules.import_validator import is_attachment_title as _is_att
                        is_att, att_reason = _is_att(title)
                        if is_att:
                            reason_parts.append(f"疑似附件/材料清单: {att_reason}")
                        else:
                            reason_parts.append("标题异常(规则检测)")

                    anomaly_docs.append({
                        "id": d["id"],
                        "title": title,
                        "document_no": d.get("document_no", ""),
                        "file_name": d.get("file_name", ""),
                        "file_path": d.get("file_path", ""),
                        "status": d.get("status", ""),
                        "reason": "; ".join(reason_parts),
                    })
            st.session_state["anomaly_docs"] = anomaly_docs
            st.success(f"扫描完成，共发现 **{len(anomaly_docs)}** 条标题异常记录")
            st.rerun()

    anomaly_docs = st.session_state.get("anomaly_docs")
    if anomaly_docs:
        st.markdown(f"**共 {len(anomaly_docs)} 条标题异常记录**")

        # 显示异常清单
        anomaly_df_data = []
        for d in anomaly_docs:
            anomaly_df_data.append({
                "ID": d["id"],
                "标题": d["title"][:40] if d["title"] else "（空）",
                "文号": d.get("document_no", ""),
                "文件名": d.get("file_name", ""),
                "状态": d.get("status", ""),
                "异常原因": d.get("reason", ""),
            })
        st.dataframe(anomaly_df_data, use_container_width=True, hide_index=True, height=300)

        # 导出异常清单
        import io as _io
        import pandas as _pd
        df_export = _pd.DataFrame(anomaly_docs)
        excel_buffer = _io.BytesIO()
        with _pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
            df_export.to_excel(writer, index=False, sheet_name="标题异常清单")
        st.download_button(
            "📥 导出标题异常清单 Excel",
            data=excel_buffer.getvalue(),
            file_name=f"标题异常清单_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_anomaly_list",
        )

        # 一键清理
        st.markdown("---")
        st.markdown("### ⚠️ 一键清理标题异常记录")

        del_col1, del_col2, del_col3 = st.columns([2, 2, 3])
        with del_col1:
            delete_files_too = st.checkbox("同时删除原文件", key="del_files_anomaly", help="默认只删除数据库记录")
        with del_col2:
            if st.button("🗑 一键清理异常记录", key="batch_clean_anomaly", type="primary"):
                anomaly_ids = [d["id"] for d in anomaly_docs]
                st.session_state["pending_anomaly_delete"] = anomaly_ids
                st.session_state["pending_anomaly_delete_files"] = delete_files_too
                st.rerun()

        # 二次确认
        pending_delete_ids = st.session_state.get("pending_anomaly_delete")
        if pending_delete_ids:
            st.warning(f"⚠️ 确认删除 **{len(pending_delete_ids)}** 条标题异常记录？")
            st.markdown("> 此操作不可撤销，请谨慎操作。")
            cfm_col1, cfm_col2 = st.columns([1, 3])
            with cfm_col1:
                if st.button("✅ 确认删除", key="cfm_anomaly_delete", type="primary"):
                    del_files = st.session_state.get("pending_anomaly_delete_files", False)
                    result = db.batch_delete_documents(pending_delete_ids, delete_files=del_files)
                    st.success(
                        f"已删除 {result['deleted']} 条记录"
                        f"{'（含原文件）' if del_files else ''}"
                    )
                    if result["errors"]:
                        for e in result["errors"][:5]:
                            st.caption(f"- {e}")
                    db.log_operation({
                        "action": "批量清理标题异常",
                        "target_type": "document",
                        "notes": f"清理了 {result['deleted']} 条标题异常记录",
                    })
                    del st.session_state["pending_anomaly_delete"]
                    del st.session_state["pending_anomaly_delete_files"]
                    del st.session_state["anomaly_docs"]
                    time.sleep(1)
                    st.rerun()
            with cfm_col2:
                if st.button("❌ 取消", key="cancel_anomaly_delete"):
                    del st.session_state["pending_anomaly_delete"]
                    del st.session_state["pending_anomaly_delete_files"]
                    st.rerun()

# 分页导航
if total_pages > 1:
    nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns([1, 1, 3, 1, 1])
    with nav_col1:
        if st.button("◀ 上一页", disabled=st.session_state["current_page"] <= 1, key="prev_page"):
            st.session_state["current_page"] = max(1, st.session_state["current_page"] - 1)
            st.rerun()
    with nav_col3:
        st.markdown(f"<div style='text-align:center;padding-top:5px;'>第 <b>{st.session_state['current_page']}</b> / {total_pages} 页</div>", unsafe_allow_html=True)
    with nav_col5:
        if st.button("下一页 ▶", disabled=st.session_state["current_page"] >= total_pages, key="next_page"):
            st.session_state["current_page"] = min(total_pages, st.session_state["current_page"] + 1)
            st.rerun()
