"""政策文件录入页面 — 导入链接、上传文件、新增文件、导入 Excel、本地文件夹导入"""

import os
import io
import uuid
import time

import pandas as pd
import streamlit as st

import database.db as db
from config import (
    DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS,
    REGION_OPTIONS, SOURCE_TYPE_OPTIONS, UPLOADS_DIR,
    ENABLE_WEB_IMPORT, SAVE_POLICY_FILE,
    POLICY_FILES_DIR, BUSINESS_TYPE_OPTIONS, SENSITIVITY_LEVEL_OPTIONS,
    IMPORTANCE_LEVEL_OPTIONS, IMPORTANCE_LEVEL_DEFAULT,
    DEFAULT_LOCAL_IMPORT_DIR, MAX_UPLOAD_SIZE_MB,
)
from modules.document_parser import parse_file, get_supported_types, safe_fetch_from_url, analyze_document, parse_file_with_structure
from modules.metadata_extractor import extract_all_metadata, classify_document, extract_title_with_meta, extract_primary_document_no, is_attachment_or_form_title
from modules.classifier import classify_business_tags
from modules.import_validator import (
    validate_import_candidate, clean_filename_for_title, looks_like_policy_filename,
    is_attachment_title,
)
from modules.status_utils import normalize_document_status
from modules.rule_engine import get_display_title, detect_invalid_title, truncate_text
from modules.excel_io import (
    generate_import_template, parse_import_excel,
    export_documents_to_excel,
)
from utils.ui import render_app_header


def _mark_source_pending_item_done(prefill: dict, doc_id: int):
    """v7.2.4: 从待补录跳转新增成功后，回写废止/失效依据库中的清单状态。"""
    evidence_id = prefill.get("source_evidence_id")
    affected_title = prefill.get("source_affected_title") or prefill.get("title", "")
    affected_doc_no = prefill.get("source_affected_doc_no") or prefill.get("document_no", "")
    if not evidence_id or not affected_title:
        return
    try:
        from modules.policy_monitor import get_monitor_candidate, update_monitor_candidate
        import json as _json
        cand = get_monitor_candidate(evidence_id)
        if not cand:
            return
        raw = cand.get("affected_items", "")
        items = _json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
        changed = False
        for item in items:
            title_match = item.get("old_title", "") == affected_title
            no_match = True
            if affected_doc_no:
                no_match = item.get("old_document_no", "") == affected_doc_no
            if title_match and no_match:
                item["pending_import_status"] = "已补录"
                item["matched"] = True
                item["matched_id"] = doc_id
                item["matched_document_id"] = doc_id
                item["matched_title"] = affected_title
                item["match_status"] = "已补录"
                item["match_method"] = "人工补录"
                item["match_score"] = 1.0
                changed = True
                break
        if changed:
            update_monitor_candidate(evidence_id, {
                "affected_items": _json.dumps(items, ensure_ascii=False)
            })
    except Exception:
        pass


def _merge_business_tags(preset_selected: list, custom_input: str) -> str:
    """合并预设多选和自定义输入，去重排序"""
    tags = set()
    for t in preset_selected:
        t = t.strip()
        if t:
            tags.add(t)
    if custom_input:
        for t in custom_input.replace("，", ",").replace("、", ",").replace(";", ",").split(","):
            t = t.strip()
            if t:
                tags.add(t)
    return ",".join(sorted(tags))


# v7.2.0: 批量链接导入的辅助函数
def _build_document_data(wm: dict, text_meta: dict, text: str, url: str) -> dict:
    """从抓取结果构建 document 数据字典"""
    from modules.classifier import classify_business_tags
    keywords = text_meta.get("keywords", "")
    auto_bt = ",".join(classify_business_tags(
        wm.get("title", ""), keywords, text))
    return {
        "title": (wm.get("title") or text_meta.get("title") or "未命名政策").strip(),
        "document_no": (wm.get("document_no") or text_meta.get("document_no") or "").strip(),
        "issuing_authority": (wm.get("issuing_authority_candidate")
                              or text_meta.get("issuing_authority") or "").strip(),
        "publish_date": (wm.get("publish_date") or text_meta.get("publish_date") or "").strip(),
        "effective_date": (wm.get("effective_date") or text_meta.get("effective_date") or "").strip(),
        "source_publish_date": wm.get("source_publish_date", ""),
        "pass_date": wm.get("pass_date", ""),
        "latest_revision_date": wm.get("latest_revision_date", ""),
        "revision_history": wm.get("revision_history", ""),
        "source_name": wm.get("source_name", ""),
        "status": text_meta.get("status", "待核实"),
        "region": wm.get("region") if wm.get("region") in ["全国", "省", "市", "县", "其他"] else "全国",
        "category": wm.get("category")
                    or classify_document(wm.get("title", ""), wm.get("document_no", ""), text)
                    or "其他",
        "keywords": keywords,
        "business_tags": auto_bt,
        "importance_level": "一般",
        "sensitivity_level": "公开",
        "full_text": text,
        "source_type": "公开网页导入",
        "source_url": url,
        "confirmed": 0,
        "notes": "",
    }


render_app_header("政策文件录入", "上传政策文件并确认识别结果后入库")

# ═══════════ v7.2.3: 待补录快捷新增 ═══════════
_pending_prefill = st.session_state.get("pending_import_prefill")
if _pending_prefill:
    st.success("已从“废止/失效依据库”带入待补录政策信息，可核对修改后直接新增。")
    with st.container(border=True):
        st.subheader("📝 待补录快捷新增")
        with st.form("pending_import_quick_form"):
            q_title = st.text_input("文件名称 *", value=_pending_prefill.get("title", ""))
            q_col1, q_col2 = st.columns(2)
            with q_col1:
                q_doc_no = st.text_input("文号", value=_pending_prefill.get("document_no", ""))
                q_authority = st.text_input("发文单位", value=_pending_prefill.get("issuing_authority", ""))
                q_publish_date = st.text_input("发布日期 (YYYY-MM-DD)", value=_pending_prefill.get("publish_date", ""))
                q_effective_date = st.text_input("实施日期 (YYYY-MM-DD)", value="")
            with q_col2:
                q_status_default = _pending_prefill.get("status", "待核实")
                q_status_idx = DOC_STATUS_OPTIONS.index(q_status_default) if q_status_default in DOC_STATUS_OPTIONS else DOC_STATUS_OPTIONS.index("待核实")
                q_status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=q_status_idx, key="pending_status")
                q_region = st.selectbox("适用地区", REGION_OPTIONS, index=0, key="pending_region")
                q_category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS, index=DOC_CATEGORY_OPTIONS.index("其他"), key="pending_category")
                q_source_type = st.selectbox("来源类型", SOURCE_TYPE_OPTIONS, index=SOURCE_TYPE_OPTIONS.index("手工录入") if "手工录入" in SOURCE_TYPE_OPTIONS else 0, key="pending_source_type")
            q_source_url = st.text_input("依据/来源链接", value=_pending_prefill.get("source_url", ""))
            q_keywords = st.text_input("关键词（逗号分隔）", value="")
            q_summary = st.text_area("摘要", height=60, value="")
            q_full_text = st.text_area("正文全文（可粘贴，暂时没有可留空）", height=100, value="")
            q_notes = st.text_area("备注", height=90, value=_pending_prefill.get("notes", ""))

            q_btn1, q_btn2 = st.columns([1, 4])
            with q_btn1:
                q_submitted = st.form_submit_button("确认新增", type="primary")
            with q_btn2:
                q_cancel = st.form_submit_button("取消待补录")

            if q_cancel:
                st.session_state.pop("pending_import_prefill", None)
                st.rerun()

            if q_submitted:
                if not q_title.strip():
                    st.error("文件名称不能为空")
                else:
                    data = {
                        "title": q_title.strip(),
                        "document_no": q_doc_no.strip(),
                        "issuing_authority": q_authority.strip(),
                        "publish_date": q_publish_date.strip(),
                        "effective_date": q_effective_date.strip(),
                        "expiry_date": "",
                        "status": q_status,
                        "region": q_region,
                        "category": q_category,
                        "keywords": q_keywords.strip(),
                        "business_tags": ",".join(classify_business_tags(q_title, q_keywords, q_full_text)),
                        "importance_level": IMPORTANCE_LEVEL_DEFAULT,
                        "sensitivity_level": "公开",
                        "summary": q_summary.strip(),
                        "full_text": q_full_text.strip(),
                        "source_type": q_source_type,
                        "source_url": q_source_url.strip(),
                        "confirmed": 1,
                        "notes": q_notes.strip(),
                    }
                    if q_doc_no.strip():
                        existing = db.get_document_by_no(q_doc_no.strip())
                        if existing:
                            st.error(f"文号「{q_doc_no.strip()}」已存在：《{existing['title']}》")
                        else:
                            doc_id = db.create_document(data)
                            db.log_operation({
                                "action": "待补录新增",
                                "target_type": "document",
                                "target_id": doc_id,
                                "file_name": q_title.strip(),
                                "notes": "从废止/失效依据库待补录清单跳转新增",
                            })
                            _mark_source_pending_item_done(_pending_prefill, doc_id)
                            st.session_state.pop("pending_import_prefill", None)
                            st.success(f"待补录政策新增成功！ID: {doc_id}，已从待补录清单移除。")
                            time.sleep(0.5)
                            st.rerun()
                    else:
                        doc_id = db.create_document(data)
                        db.log_operation({
                            "action": "待补录新增",
                            "target_type": "document",
                            "target_id": doc_id,
                            "file_name": q_title.strip(),
                            "notes": "从废止/失效依据库待补录清单跳转新增",
                        })
                        _mark_source_pending_item_done(_pending_prefill, doc_id)
                        st.session_state.pop("pending_import_prefill", None)
                        st.success(f"待补录政策新增成功！ID: {doc_id}，已从待补录清单移除。")
                        time.sleep(0.5)
                        st.rerun()


# ═══════════ 操作 Tab ═══════════
if ENABLE_WEB_IMPORT:
    tab1, tab2, tab3, tab4, tab5, tab_folder = st.tabs(
        ["导入链接", "上传文件", "新增文件", "导入 Excel", "导出 Excel", "本地文件夹导入"])
else:
    tab2, tab3, tab4, tab5, tab_folder = st.tabs(
        ["上传文件", "新增文件", "导入 Excel", "导出 Excel", "本地文件夹导入"])
    tab1 = None


# ═══════════ Tab1: 导入链接（v7.2.0: 支持批量链接） ═══════════
if tab1 is not None:
    with tab1:
        st.caption("粘贴政策文件的网页链接（支持多个链接，一行一个），系统自动抓取正文并提取元数据")
        st.warning(
            "本功能仅用于读取公开政策网页信息并录入本地政策文件库。"
            "请勿输入涉密、内部系统、非公开网页或需要登录权限的网址。"
            "本功能不会上传待审查文档内容，也不会在文档审查阶段联网搜索。"
        )

        # v7.2.0: 多行文本框，支持批量粘贴链接
        batch_url_input = st.text_area(
            "文件链接（一行一个）",
            placeholder="https://f.mnr.gov.cn/202606/t20260605_2931308.html\nhttps://www.mnr.gov.cn/gk/zcfg/202501/t20250101_2900001.html",
            height=100,
            label_visibility="collapsed",
            key="batch_import_urls",
        )
        safety_confirmed = st.checkbox(
            "我确认以上链接均为公开政策文件网页，不涉及涉密、内部敏感或非公开信息。",
            key="import_safety_check",
        )

        col_fetch, col_clear = st.columns([1, 5])
        with col_fetch:
            if st.button("🔍 批量抓取并预览", key="batch_fetch_btn", type="primary", disabled=not safety_confirmed):
                urls = [u.strip() for u in batch_url_input.split("\n") if u.strip()]
                if not urls:
                    st.error("请输入至少一个链接")
                else:
                    results = []
                    failed = []
                    progress = st.progress(0, text=f"抓取中 0/{len(urls)}...")
                    for idx, url in enumerate(urls):
                        progress.progress((idx + 1) / len(urls), text=f"抓取 {idx+1}/{len(urls)}: {url[:60]}...")
                        result = safe_fetch_from_url(url)
                        if result["error"]:
                            failed.append({"url": url, "reason": result["error"]})
                        elif not result["text"].strip():
                            failed.append({"url": url, "reason": "未能提取到有效文本内容"})
                        else:
                            # 检查重复文号
                            wm = result.get("webpage_meta", {})
                            text_meta = extract_all_metadata(result["text"])
                            doc_no = wm.get("document_no") or text_meta.get("document_no") or ""
                            dup_warning = ""
                            if doc_no:
                                existing = db.get_document_by_no(doc_no)
                                if existing:
                                    dup_warning = f"该文号已存在: 《{existing['title']}》(ID: {existing['id']})，将不会重复入库。"
                            results.append({
                                "url": url,
                                "result": result,
                                "dup_warning": dup_warning,
                            })
                    progress.empty()
                    st.session_state["batch_fetch_results"] = results
                    st.session_state["batch_fetch_failed"] = failed
                    st.rerun()

        with col_clear:
            if st.button("🗑 清空", key="batch_import_clear", use_container_width=True):
                keys = ["batch_fetch_results", "batch_fetch_failed", "batch_import_urls"]
                for k in keys:
                    st.session_state.pop(k, None)
                st.rerun()

        # v7.2.0: 显示抓取失败
        batch_failed = st.session_state.get("batch_fetch_failed", [])
        if batch_failed:
            with st.expander(f"⚠️ 抓取失败 ({len(batch_failed)} 条)", expanded=True):
                for f in batch_failed:
                    st.warning(f"**{f['url'][:80]}**: {f['reason']}")

        # v7.2.0: 批量预览卡片
        batch_results = st.session_state.get("batch_fetch_results", [])
        if batch_results:
            st.success(f"成功抓取 **{len(batch_results)}** 条")

            # 批量操作栏
            col_ba1, col_ba2, col_ba3 = st.columns([1, 1, 4])
            with col_ba1:
                if st.button("✅ 全部确认入库", key="batch_all_confirm", type="primary"):
                    imported = 0
                    skipped = 0
                    for br in batch_results:
                        if br.get("dup_warning"):
                            skipped += 1
                            continue
                        r = br["result"]
                        wm = r.get("webpage_meta", {})
                        text = r["text"]
                        text_meta = extract_all_metadata(text)
                        try:
                            data = _build_document_data(wm, text_meta, text, br["url"])
                            db.create_document(data)
                            imported += 1
                        except Exception:
                            skipped += 1
                    msg = f"已入库 {imported} 条"
                    if skipped:
                        msg += f"，跳过 {skipped} 条（含重复文号）"
                    st.success(msg)
                    st.session_state.pop("batch_fetch_results", None)
                    st.session_state.pop("batch_fetch_failed", None)
                    time.sleep(0.5)
                    st.rerun()
            with col_ba2:
                if st.button("🗑 清空本次导入", key="batch_all_clear"):
                    st.session_state.pop("batch_fetch_results", None)
                    st.session_state.pop("batch_fetch_failed", None)
                    st.rerun()

            st.divider()

            # 每个链接一个预览卡片
            for bi, br in enumerate(batch_results):
                url = br["url"]
                r = br["result"]
                text = r["text"]
                wm = r.get("webpage_meta", {})
                text_meta = extract_all_metadata(text)

                with st.container(border=True):
                    st.markdown(f"### {bi+1}. {(wm.get('title') or text_meta.get('title') or '未识别')[:60]}")

                    if br.get("dup_warning"):
                        st.warning(f"⚠️ {br['dup_warning']}")

                    # 识别结果
                    cols = st.columns(4)
                    with cols[0]:
                        st.metric("标题", (wm.get("title") or text_meta.get("title") or "未识别")[:25] or "未识别")
                    with cols[1]:
                        st.metric("文号", wm.get("document_no") or text_meta.get("document_no") or "（空）")
                    with cols[2]:
                        st.metric("发文单位", wm.get("issuing_authority_candidate")
                                  or text_meta.get("issuing_authority") or "（空）")
                    with cols[3]:
                        st.metric("发布日期", wm.get("publish_date") or text_meta.get("publish_date") or "（空）")

                    with st.expander("📄 正文摘要"):
                        st.text_area("正文", text[:2000], height=150, disabled=True, label_visibility="collapsed", key=f"preview_{bi}")
                        st.caption(f"原文链接: [{url[:60]}...]({url})")
                        st.caption(f"识别质量: {wm.get('parse_warning', '良好') or '良好'}")

                    # 卡片操作按钮
                    col_card1, col_card2, col_card3 = st.columns([1, 1, 4])
                    with col_card1:
                        if st.button("✅ 确认入库", key=f"confirm_{bi}", disabled=bool(br.get("dup_warning"))):
                            data = _build_document_data(wm, text_meta, text, url)
                            doc_id = db.create_document(data)
                            db.log_operation({
                                "action": "网址导入", "target_type": "document",
                                "target_id": doc_id, "file_name": data["title"],
                                "sensitivity_level": data["sensitivity_level"],
                            })
                            st.success(f"《{data['title']}》入库成功！ID: {doc_id}")
                            batch_results.pop(bi)
                            st.session_state["batch_fetch_results"] = batch_results
                            time.sleep(0.3)
                            st.rerun()
                    with col_card2:
                        if st.button("✏️ 修改后入库", key=f"edit_{bi}"):
                            st.session_state["batch_edit_idx"] = bi
                            st.session_state["batch_edit_url"] = url
                            st.session_state["batch_edit_data"] = r
                            st.rerun()
                    with col_card3:
                        if st.button("🗑 移除", key=f"remove_{bi}"):
                            batch_results.pop(bi)
                            st.session_state["batch_fetch_results"] = batch_results
                            st.rerun()

        # v7.2.0: 修改后入库的编辑表单
        edit_idx = st.session_state.get("batch_edit_idx")
        if edit_idx is not None:
            st.markdown("---")
            st.subheader("✏️ 修改并确认入库")
            r = st.session_state.get("batch_edit_data", {})
            text = r.get("text", "")
            wm = r.get("webpage_meta", {})
            text_meta = extract_all_metadata(text)
            url = st.session_state.get("batch_edit_url", "")

            with st.form("batch_edit_form"):
                title = st.text_input("文件名称 *", value=wm.get("title") or text_meta.get("title", ""))
                c1, c2 = st.columns(2)
                with c1:
                    doc_no = st.text_input("文号", value=wm.get("document_no") or text_meta.get("document_no") or "")
                    authority = st.text_input("发文单位", value=wm.get("issuing_authority_candidate") or text_meta.get("issuing_authority") or "")
                    pub_date = st.text_input("发布日期", value=wm.get("publish_date") or text_meta.get("publish_date") or "")
                with c2:
                    eff_date = st.text_input("实施日期", value=wm.get("effective_date") or text_meta.get("effective_date") or "")
                    s = text_meta.get("status", "待核实")
                    st_idx = DOC_STATUS_OPTIONS.index(s) if s in DOC_STATUS_OPTIONS else DOC_STATUS_OPTIONS.index("待核实")
                    status = st.selectbox("文件状态", DOC_STATUS_OPTIONS, index=st_idx)
                    region = st.selectbox("适用地区", REGION_OPTIONS,
                        index=REGION_OPTIONS.index(wm.get("region")) if wm.get("region") in REGION_OPTIONS else 0)
                suggested_cat = wm.get("category") or classify_document(wm.get("title", ""), wm.get("document_no", ""), text)
                cat_idx = DOC_CATEGORY_OPTIONS.index(suggested_cat) if suggested_cat in DOC_CATEGORY_OPTIONS else DOC_CATEGORY_OPTIONS.index("其他")
                category = st.selectbox("文件类别", DOC_CATEGORY_OPTIONS, index=cat_idx)
                keywords = st.text_input("关键词")
                sl = st.selectbox("敏感级别", SENSITIVITY_LEVEL_OPTIONS, index=0)
                notes = st.text_input("备注")

                cfb, cfb2 = st.columns([1, 4])
                with cfb:
                    confirmed = st.form_submit_button("确认入库")
                with cfb2:
                    cancel = st.form_submit_button("取消")

                if confirmed:
                    if "涉密禁止上传" in sl:
                        st.error("该级别文件禁止上传本系统。")
                    elif not title.strip():
                        st.error("文件名称不能为空")
                    else:
                        data = {
                            "title": title.strip(), "document_no": doc_no.strip() if doc_no else "",
                            "issuing_authority": authority.strip() if authority else "",
                            "publish_date": pub_date.strip() if pub_date else "",
                            "effective_date": eff_date.strip() if eff_date else "",
                            "status": status, "region": region, "category": category,
                            "keywords": keywords.strip() if keywords else "",
                            "sensitivity_level": sl,
                            "full_text": text, "source_type": "公开网页导入",
                            "source_url": url, "confirmed": 0,
                            "notes": notes.strip() if notes else "",
                            "business_tags": "",
                            "source_name": wm.get("source_name", ""),
                            "source_publish_date": wm.get("source_publish_date", ""),
                            "pass_date": wm.get("pass_date", ""),
                            "latest_revision_date": wm.get("latest_revision_date", ""),
                            "revision_history": wm.get("revision_history", ""),
                        }
                        doc_id = db.create_document(data)
                        db.log_operation({
                            "action": "网址导入", "target_type": "document",
                            "target_id": doc_id, "file_name": title.strip(),
                            "sensitivity_level": sl,
                        })
                        st.success(f"《{title.strip()}》入库成功！ID: {doc_id}")
                        st.session_state.pop("batch_edit_idx", None)
                        st.session_state.pop("batch_edit_data", None)
                        st.session_state.pop("batch_edit_url", None)
                        time.sleep(0.5)
                        st.rerun()
                if cancel:
                    st.session_state.pop("batch_edit_idx", None)
                    st.session_state.pop("batch_edit_data", None)
                    st.session_state.pop("batch_edit_url", None)
                    st.rerun()


# ═══════════ Tab2: 上传文件 ═══════════
with tab2:
    from modules.batch_upload_ui import render_batch_upload_ui
    render_batch_upload_ui(uploader_key="policy_file_uploader")


# ═══════════ Tab3: 新增文件 ═══════════
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
        bt_selected = st.multiselect("业务类型（预设）", BUSINESS_TYPE_OPTIONS, default=bt_default, key="add_bt")
        bt_custom = st.text_input("自定义业务类型（逗号分隔）", key="add_bt_custom",
            placeholder="如：城市更新类, 历史遗留用地类")
        il = st.selectbox("文件重要级别", IMPORTANCE_LEVEL_OPTIONS,
            index=IMPORTANCE_LEVEL_OPTIONS.index(IMPORTANCE_LEVEL_DEFAULT),
            key="add_il",
            help="文件重要级别用于人工标记该政策文件在项目审查中的重要程度，不代表政策效力状态。")
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
                final_bt = _merge_business_tags(bt_selected, bt_custom)
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
                    "business_tags": final_bt,
                    "importance_level": il,
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


# ═══════════ Tab4: 导入 Excel ═══════════
with tab4:
    st.markdown("请按照模板格式填写政策文件清单后上传")

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

        if result["success"]:
            st.success(f"导入完成：成功 {len(result['success'])} 条")
            # 显示导入结果清单
            with st.expander("查看导入结果清单"):
                success_data = [{"标题": s["title"], "ID": s["id"]} for s in result["success"]]
                st.dataframe(success_data, use_container_width=True, hide_index=True)
        if result.get("relation_notes"):
            for note in result["relation_notes"]:
                st.info(note)
        if result["errors"]:
            st.warning(f"失败 {len(result['errors'])} 条：")
            for err in result["errors"]:
                st.caption(f"- {err}")


# ═══════════ Tab5: 导出 Excel ═══════════
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


# ═══════════ Tab6: 本地文件夹导入 ═══════════
with tab_folder:
    st.caption("读取运行程序主机电脑上的本地路径，扫描并批量导入政策文件")
    st.info("本功能读取的是运行程序主机电脑上的本地路径。局域网访问者输入自己电脑路径无效。")

    for key in ["folder_scan_results", "folder_parse_results", "folder_import_report"]:
        if key not in st.session_state:
            st.session_state[key] = None

    local_dir = st.text_input("文件夹路径", value=DEFAULT_LOCAL_IMPORT_DIR, key="local_import_dir")
    default_sl = st.selectbox("默认敏感级别", SENSITIVITY_LEVEL_OPTIONS[:3], index=0, key="local_default_sl")
    default_il = st.selectbox("默认文件重要级别", IMPORTANCE_LEVEL_OPTIONS,
        index=IMPORTANCE_LEVEL_OPTIONS.index(IMPORTANCE_LEVEL_DEFAULT), key="local_default_il")

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
                        "title": "", "document_no": "", "issuing_authority": "",
                        "publish_date": "", "category": "", "business_type": "",
                        "sensitivity_level": default_sl, "importance_level": default_il,
                        "title_quality": "不支持格式", "suggestion": "不支持格式",
                        "is_duplicate": False, "recommend_import": False,
                        "fail_reason": item["status"], "full_text": "",
                    })
                    continue
                try:
                    text = parse_file(item["file_path"], pdf_max_pages=30)
                    meta = extract_all_metadata(text, file_name=item["file_name"])
                    title = meta.get("title", "")
                    doc_no = meta.get("document_no") or ""

                    validation = validate_import_candidate(
                        title=title, document_no=doc_no, text=text, file_name=item["file_name"],
                    )

                    is_att, att_reason = is_attachment_title(title)

                    dup_check = db.check_duplicate(
                        title=title, document_no=doc_no,
                        file_name=item["file_name"], file_size=item["file_size"],
                        full_text=text,
                    )

                    recommend = validation["valid"] and not dup_check["is_duplicate"] and not is_att

                    parse_results.append({
                        **item,
                        "title": title, "document_no": doc_no,
                        "issuing_authority": meta.get("issuing_authority", ""),
                        "publish_date": meta.get("publish_date", ""),
                        "effective_date": meta.get("effective_date", ""),
                        "status_field": meta.get("status", "待核实"),
                        "category": classify_document(title, doc_no, text),
                        "business_type": "",
                        "importance_level": default_il,
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
                    })
                    import_count += 1
                except Exception as e:
                    fail_count += 1
                    parse_results.append({
                        **item,
                        "title": "", "document_no": "", "issuing_authority": "",
                        "publish_date": "", "category": "", "business_type": "",
                        "importance_level": default_il, "sensitivity_level": default_sl,
                        "title_quality": "解析失败", "suggestion": "",
                        "is_duplicate": False, "recommend_import": False,
                        "fail_reason": str(e), "full_text": "",
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

        list_data = []
        for idx, r in enumerate(parse_results):
            q = r.get("title_quality", "")
            dup_mark = "⚠️重复" if r.get("is_duplicate") else ""
            file_status = normalize_document_status(r.get("status_field", "待核实"))
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
                "重复": dup_mark,
                "是否建议入库": "是" if r.get("recommend_import") else "否",
                "建议": r.get("suggestion", "")[:30],
            })
        st.dataframe(list_data, use_container_width=True, hide_index=True, height=300)

        # 勾选入库
        st.markdown("**勾选要导入的文件：**")
        if "import_checklist" not in st.session_state:
            st.session_state["import_checklist"] = {}

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
                st.markdown(
                    f"**{r['file_name']}** → {r.get('title', '（未识别）')[:40]} "
                    f"| :{'green' if q == '可入库' else 'orange' if q == '待人工确认' else 'red'}[{q}]"
                    f"{dup_info}{fail_info}"
                )

            if checked:
                with st.expander(f"修改元数据 - {r['file_name'][:40]}"):
                    mc1, mc2 = st.columns(2)
                    with mc1:
                        new_title = st.text_input("标题", value=r.get("title", ""), key=f"mt_{idx}")
                        new_doc_no = st.text_input("文号", value=r.get("document_no", ""), key=f"mdn_{idx}")
                    with mc2:
                        auto_bt = classify_business_tags(
                            new_title or r.get("title", ""),
                            r.get("keywords", ""),
                            r.get("full_text", ""),
                        )
                        new_bt = st.multiselect(
                            "业务类型（预设）",
                            BUSINESS_TYPE_OPTIONS,
                            default=auto_bt,
                            key=f"mbt_{idx}"
                        )
                        new_bt_custom = st.text_input("自定义业务类型", key=f"mbt_cust_{idx}",
                            placeholder="逗号分隔")
                        new_il = st.selectbox("文件重要级别", IMPORTANCE_LEVEL_OPTIONS,
                            index=IMPORTANCE_LEVEL_OPTIONS.index(default_il),
                            key=f"mil_{idx}")
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
                                    "importance_level": r.get("importance_level", default_il),
                                    "sensitivity_level": r.get("sensitivity_level", default_sl),
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
                                    "importance_level": r.get("importance_level", default_il),
                                    "sensitivity_level": r.get("sensitivity_level", default_sl),
                                    "status": status, "fail_reason": r.get("dup_reason", "重复"),
                                    "suggestion": "允许覆盖更新或保留为新记录", "document_id": None,
                                })
                                continue

                            title = r.get("title", "")
                            doc_no = r.get("document_no", "")

                            if st.session_state["import_checklist"].get(str(idx)):
                                user_title = st.session_state.get(f"mt_{idx}")
                                if user_title and user_title != title:
                                    title = user_title
                                user_doc_no = st.session_state.get(f"mdn_{idx}")
                                if user_doc_no and user_doc_no != doc_no:
                                    doc_no = user_doc_no

                            bt_tags_list = st.session_state.get(f"mbt_{idx}", [])
                            bt_custom_str = st.session_state.get(f"mbt_cust_{idx}", "")
                            final_bt = _merge_business_tags(bt_tags_list, bt_custom_str)
                            if not final_bt:
                                auto_bt = classify_business_tags(title, r.get("keywords", ""), r.get("full_text", ""))
                                final_bt = ",".join(auto_bt)

                            il_val = st.session_state.get(f"mil_{idx}", default_il)
                            sl_val = st.session_state.get(f"msl_{idx}", default_sl)

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
                                "business_tags": final_bt,
                                "importance_level": il_val,
                                "sensitivity_level": sl_val,
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
                                "sensitivity_level": sl_val,
                                "notes": f"从 {local_dir} 导入，标题质量: {q}",
                            })
                            import_report["success"] += 1
                            status = "成功"
                        except Exception as e:
                            import_report["failed"] += 1
                            status = "失败"
                        import_report["details"].append({
                            "file_name": r["file_name"], "file_path": r["file_path"],
                            "title": title if status == "成功" else r.get("title", ""),
                            "document_no": r.get("document_no", ""),
                            "issuing_authority": r.get("issuing_authority", ""),
                            "category": r.get("category", ""),
                            "business_type": r.get("business_type", ""),
                            "importance_level": r.get("importance_level", default_il),
                            "sensitivity_level": r.get("sensitivity_level", default_sl),
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
                    "重要级别": d.get("importance_level", ""),
                    "敏感级别": d.get("sensitivity_level", ""),
                    "入库状态": d.get("status", ""),
                    "失败原因": d.get("fail_reason", ""),
                    "处理建议": d.get("suggestion", ""),
                    "document_id": d.get("document_id", ""),
                })
            st.dataframe(detail_rows, use_container_width=True, hide_index=True, height=300)

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

        if st.button("清空导入结果", key="clear_import_report"):
            st.session_state["folder_scan_results"] = None
            st.session_state["folder_parse_results"] = None
            st.session_state["folder_import_report"] = None
            st.session_state["import_checklist"] = {}
            st.rerun()
