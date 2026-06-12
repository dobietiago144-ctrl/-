"""文件详情页面"""

import os
import time
import streamlit as st
import database.db as db
from config import (
    DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS, REGION_OPTIONS,
    ALLOW_POLICY_DOWNLOAD, BUSINESS_TYPE_OPTIONS, SENSITIVITY_LEVEL_OPTIONS,
    IMPORTANCE_LEVEL_OPTIONS, IMPORTANCE_LEVEL_DEFAULT,
)
from modules.metadata_extractor import extract_all_metadata, extract_title_with_meta, extract_primary_document_no
from modules.document_parser import analyze_document, parse_file_with_structure
from modules.classifier import classify_business_tags
from modules.import_validator import is_attachment_title

doc_id = st.session_state.get("view_doc_id", None)
doc = db.get_document(doc_id) if doc_id else None

if not doc_id:
    st.warning("请从文件库页面选择要查看的文件")
    st.stop()

if not doc:
    st.error("文件不存在")
    st.stop()

# Fallback: in non-Streamlit contexts, st.stop() may not halt execution.
# Use an empty dict to prevent NoneType errors downstream.
if doc is None:
    doc = {}

st.title(f"《{doc.get('title', '未知文件')}》")

# 返回按钮
if st.button("← 返回文件库", key="back_to_library"):
    st.switch_page("pages/1_document_query.py")

# 编辑模式
if "edit_mode" not in st.session_state:
    st.session_state["edit_mode"] = False
if "analyze_result" not in st.session_state:
    st.session_state["analyze_result"] = None

col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([1, 1, 1, 7])
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
with col_btn3:
    # 重新解析元数据按钮（仅在有原文件时可用）
    fp = doc.get("file_path", "")
    has_file = bool(fp and os.path.isfile(fp))
    if st.button("重新解析元数据", type="secondary", disabled=not has_file,
                 help="重新读取原文件并提取元数据，与当前值对比" if has_file else "无原文件，无法重新解析"):
        st.session_state["reparse_trigger"] = True
        st.rerun()
    if not has_file:
        st.caption("*无原文件")

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

# ═══════════ 重新解析元数据 ═══════════
if st.session_state.get("reparse_trigger") and has_file:
    with st.spinner("正在重新解析原文件..."):
        try:
            structured = parse_file_with_structure(fp)
            new_meta = extract_all_metadata(structured["full_text"])
            st.session_state["reparse_result"] = new_meta
            st.session_state["reparse_show"] = True
        except Exception as e:
            st.error(f"重新解析失败: {e}")
            st.session_state["reparse_result"] = None
            st.session_state["reparse_show"] = False
    st.session_state["reparse_trigger"] = False
    st.rerun()

if st.session_state.get("reparse_show") and st.session_state.get("reparse_result"):
    new_meta = st.session_state["reparse_result"]
    with st.container(border=True):
        st.markdown("### 重新解析元数据 - 新旧对比")

        # 对比表格
        compare_data = []
        fields = [
            ("标题", "title", doc.get("title", ""), new_meta.get("title", "")),
            ("文号", "document_no", doc.get("document_no", ""), new_meta.get("document_no") or ""),
            ("发文单位", "issuing_authority", doc.get("issuing_authority", ""), new_meta.get("issuing_authority", "")),
            ("发布日期", "publish_date", doc.get("publish_date", ""), new_meta.get("publish_date", "")),
            ("实施日期", "effective_date", doc.get("effective_date", ""), new_meta.get("effective_date", "")),
            ("文件状态", "status", doc.get("status", ""), new_meta.get("status", "")),
            ("文件类别", "category", doc.get("category", ""), "（需重新分类）"),
        ]

        for field_name, field_key, old_val, new_val in fields:
            changed = old_val != new_val
            marker = " ⬅ 有变化" if changed else ""
            compare_data.append({
                "字段": field_name,
                "当前值": old_val[:60] if old_val else "（空）",
                "新识别值": new_val[:60] if new_val else "（空）",
                "是否有变化": "是" if changed else "否",
            })

        st.dataframe(compare_data, use_container_width=True, hide_index=True, height=280)

        # 标题来源和置信度
        st.markdown("**解析来源说明：**")
        src_col1, src_col2, src_col3 = st.columns(3)
        with src_col1:
            st.metric("标题来源", new_meta.get("title_source", "未知"))
        with src_col2:
            st.metric("标题置信度", new_meta.get("title_confidence", "低"))
        with src_col3:
            title_score = new_meta.get("title_score", 0)
            st.metric("标题得分", f"{title_score}分")

        # 附件标题检查
        is_att, att_reason = is_attachment_title(new_meta.get("title", ""))
        if is_att:
            st.warning(f"⚠️ 新识别标题疑似为附件条目标题: {att_reason}")
            st.markdown("建议不要直接覆盖，先确认正确的政策文件主标题。")

        # 标题候选列表
        candidates = new_meta.get("title_candidates", [])
        if len(candidates) > 1:
            with st.expander("查看所有标题候选"):
                cand_data = []
                for c in candidates:
                    cand_data.append({
                        "候选标题": c["title"][:50],
                        "来源": c["source"],
                        "得分": c["score"],
                        "是否主标题": "是" if c["is_main_title"] else "否",
                        "原因": c["reason"],
                    })
                st.dataframe(cand_data, use_container_width=True, hide_index=True)

        # 确认操作
        st.markdown("**请选择操作：**")
        op_col1, op_col2, op_col3 = st.columns([2, 2, 3])
        with op_col1:
            if st.button("采用新识别值覆盖", type="primary",
                         help="将新识别的元数据覆盖保存到数据库"):
                # 检查是否有人工确认过的字段（confirmed=1 表示人工确认过）
                was_confirmed = doc.get("confirmed", 0)
                if was_confirmed:
                    st.warning("该文件已有人工确认记录。以下字段将保留人工值：")
                    # 只更新非人工确认的字段（标题+文号+发文单位+日期，不覆盖人工状态）
                update_data = {
                    "title": new_meta.get("title", doc.get("title", "")),
                    "document_no": new_meta.get("document_no") or doc.get("document_no", ""),
                    "issuing_authority": new_meta.get("issuing_authority", doc.get("issuing_authority", "")),
                    "publish_date": new_meta.get("publish_date", doc.get("publish_date", "")),
                    "effective_date": new_meta.get("effective_date", doc.get("effective_date", "")),
                    "expiry_date": new_meta.get("expiry_date", doc.get("expiry_date", "")),
                }
                # 不覆盖 status（保留人工设置）
                db.update_document(doc_id, update_data)
                db.log_operation({
                    "action": "重新解析元数据", "target_type": "document",
                    "target_id": doc_id, "file_name": doc.get("title", ""),
                    "notes": f"标题来源: {new_meta.get('title_source', '')}, 置信度: {new_meta.get('title_confidence', '')}",
                })
                st.success("元数据已更新")
                st.session_state["reparse_show"] = False
                st.session_state["reparse_result"] = None
                time.sleep(1)
                st.rerun()
        with op_col2:
            if st.button("保留当前值不覆盖"):
                st.info("已保留当前元数据")
                st.session_state["reparse_show"] = False
                st.session_state["reparse_result"] = None
                st.rerun()
        with op_col3:
            st.caption("新识别值仅作参考，不会自动覆盖已有人工确认的字段。")

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
        cur_bt = doc.get("business_tags", "").split(",") if doc.get("business_tags") else []
        bt_selected = st.multiselect("业务类型（预设）", BUSINESS_TYPE_OPTIONS,
            default=[t for t in cur_bt if t in BUSINESS_TYPE_OPTIONS])
        bt_custom = st.text_input("自定义业务类型（逗号分隔）",
            value=",".join([t for t in cur_bt if t not in BUSINESS_TYPE_OPTIONS]),
            placeholder="如：城市更新类, 历史遗留用地类")
        cur_il = doc.get("importance_level", IMPORTANCE_LEVEL_DEFAULT)
        il_idx = IMPORTANCE_LEVEL_OPTIONS.index(cur_il) if cur_il in IMPORTANCE_LEVEL_OPTIONS else IMPORTANCE_LEVEL_OPTIONS.index(IMPORTANCE_LEVEL_DEFAULT)
        importance_level = st.selectbox("文件重要级别", IMPORTANCE_LEVEL_OPTIONS, index=il_idx,
            help="文件重要级别用于人工标记该政策文件在项目审查中的重要程度，不代表政策效力状态。")
        cur_sl = doc.get("sensitivity_level", "公开")
        sl_idx = SENSITIVITY_LEVEL_OPTIONS.index(cur_sl) if cur_sl in SENSITIVITY_LEVEL_OPTIONS else 0
        sl = st.selectbox("敏感级别", SENSITIVITY_LEVEL_OPTIONS, index=sl_idx)
        summary = st.text_area("摘要", value=doc.get("summary", ""), height=60)
        full_text = st.text_area("正文全文", value=doc.get("full_text", ""), height=200)
        notes = st.text_area("备注", value=doc.get("notes", ""), height=60)
        confirmed = st.checkbox("已人工确认", value=bool(doc.get("confirmed", 0)))

        if st.form_submit_button("保存修改"):
            old_sl = doc.get("sensitivity_level", "")
            # 合并业务类型
            bt_tags = set()
            for t in bt_selected:
                t = t.strip()
                if t:
                    bt_tags.add(t)
            if bt_custom:
                for t in bt_custom.replace("，", ",").replace("、", ",").replace(";", ",").split(","):
                    t = t.strip()
                    if t:
                        bt_tags.add(t)
            final_bt = ",".join(sorted(bt_tags))
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
                "business_tags": final_bt,
                "importance_level": importance_level,
                "sensitivity_level": sl,
                "summary": summary.strip() if summary else "",
                "full_text": full_text.strip() if full_text else "",
                "source_url": source_url.strip() if source_url else "",
                "confirmed": 1 if confirmed else 0,
                "notes": notes.strip() if notes else "",
            }
            db.update_document(doc_id, data)
            if old_sl != sl:
                db.log_operation({
                    "action": "文件敏感级别修改", "target_type": "document",
                    "target_id": doc_id, "file_name": doc.get("title", ""),
                    "sensitivity_level": sl,
                    "notes": f"从 '{old_sl}' 改为 '{sl}'",
                })
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

    bt = doc.get("business_tags", "")
    if bt:
        bt_tags = [t.strip() for t in bt.split(",") if t.strip()]
        st.markdown(f"**业务类型：** {' / '.join(bt_tags)}")
    il = doc.get("importance_level", IMPORTANCE_LEVEL_DEFAULT)
    st.markdown(f"**文件重要级别：** {il}")
    st.markdown(f"**敏感级别：** {doc.get('sensitivity_level', '公开')}")

    # ── 解析来源说明 ──
    title_source = doc.get("title_source", "")
    title_confidence = doc.get("title_confidence", "")
    doc_no_source = doc.get("document_no_source", "")
    is_confirmed = doc.get("confirmed", 0)

    if title_source or title_confidence:
        with st.expander("解析来源说明", expanded=False):
            src_col1, src_col2 = st.columns(2)
            with src_col1:
                st.caption(f"**标题来源：** {title_source or '未知'}")
                confidence_label = {"高": "🟢 高", "中": "🟡 中", "低": "🔴 低"}.get(title_confidence, f"⚪ {title_confidence or '未知'}")
                st.caption(f"**标题置信度：** {confidence_label}")
                st.caption(f"**文号来源：** {doc_no_source or '未知'}")
            with src_col2:
                confirmed_label = "✅ 是" if is_confirmed else "⚠️ 否"
                st.caption(f"**是否人工确认：** {confirmed_label}")

            # 低置信度或附件标题警告
            if title_source in ("附件标题", "文件名兜底"):
                st.warning("⚠️ 该标题可能不是政策文件主标题，请人工核查。")
            elif title_confidence == "低":
                st.info("💡 标题置信度较低，建议人工确认。")

            if not is_confirmed:
                st.info("💡 该文件元数据尚未经人工确认。")

    source_url = doc.get("source_url", "")
    if source_url:
        st.markdown(f"**原文链接：** [{source_url}]({source_url})")
    if doc.get("summary"):
        st.caption("**摘要：**")
        st.markdown(doc["summary"])
    if doc.get("notes"):
        st.caption("**备注：**")
        st.markdown(doc["notes"])

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
                    key=f"dl_detail_{doc_id}",
                )
        else:
            st.caption("原文件不存在或已被删除")

    # 正文
    if doc.get("full_text"):
        with st.expander("文件正文"):
            st.text_area("", doc["full_text"], height=300, disabled=True, label_visibility="collapsed")

    # 新旧关系
    st.markdown("---")
    st.subheader("新旧关系")
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
