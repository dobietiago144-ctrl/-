"""政策文件查询页面 — 搜索、筛选、列表、批量下载"""

import os
import io
import re
import time
import uuid
import zipfile

import streamlit as st

import database.db as db
from config import (
    DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS,
    REGION_OPTIONS, BUSINESS_TYPE_OPTIONS, SENSITIVITY_LEVEL_OPTIONS,
    IMPORTANCE_LEVEL_OPTIONS, IMPORTANCE_LEVEL_DEFAULT,
    ALLOW_POLICY_DOWNLOAD,
    ALLOW_PUBLIC_DOWNLOAD, ALLOW_INTERNAL_DOWNLOAD, ALLOW_SENSITIVE_DOWNLOAD,
    BATCH_DOWNLOAD_DIR, POLICY_FILES_DIR,
)
from modules.status_utils import normalize_document_status
from modules.rule_engine import get_display_title, detect_invalid_title, truncate_text
from modules.excel_io import export_documents_to_excel


# ═══════════ 辅助函数（必须在所有 st 调用之前定义） ═══════════

def _build_business_type_options() -> list:
    """构建业务类型选项：预设 + 数据库中已有自定义类型"""
    conn = db.get_connection()
    rows = conn.execute("SELECT business_tags FROM documents WHERE business_tags != ''").fetchall()
    conn.close()
    custom_tags = set()
    for row in rows:
        for tag in row["business_tags"].split(","):
            tag = tag.strip()
            if tag and tag not in BUSINESS_TYPE_OPTIONS:
                custom_tags.add(tag)
    result = ["全部"] + list(BUSINESS_TYPE_OPTIONS)
    if custom_tags:
        result.append("── 自定义业务类型 ──")
        result.extend(sorted(custom_tags))
    return result


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


def _clean_zip_filename(s: str) -> str:
    """清理文件名中的非法字符，避免 Windows 路径报错"""
    s = s.replace("《", "").replace("》", "")
    illegal = r'[<>:"/\\|?*\n\r\t]'
    s = re.sub(illegal, "_", s)
    s = re.sub(r'_+', '_', s)
    s = s.strip("_ ")
    if len(s) > 80:
        s = s[:80]
    return s


def _can_download_by_sensitivity(sl: str) -> tuple:
    """检查敏感级别是否允许批量下载。返回 (允许, 提示信息)"""
    if sl in ("公开", ""):
        return (ALLOW_PUBLIC_DOWNLOAD, "")
    elif sl == "内部":
        if ALLOW_INTERNAL_DOWNLOAD:
            return (True, "仅限内部使用")
        return (False, "内部文件不允许下载")
    elif sl == "敏感":
        if ALLOW_SENSITIVE_DOWNLOAD:
            return (True, "敏感文件下载已开放")
        return (False, "敏感文件默认不允许批量下载")
    elif "涉密" in sl:
        return (False, "涉密文件禁止下载")
    return (False, f"未知敏感级别: {sl}")


def _perform_batch_download():
    """执行批量下载逻辑"""
    selected_ids = list(st.session_state["selected_ids"])
    total_selected = len(selected_ids)
    packed = 0
    no_file = 0
    file_missing = 0
    download_failed = 0
    skipped = 0
    not_downloaded = []

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(BATCH_DOWNLOAD_DIR, exist_ok=True)
    zip_name = f"批量下载_{timestamp}.zip"
    zip_path = os.path.join(BATCH_DOWNLOAD_DIR, zip_name)

    # 清理旧临时文件（超过24小时）
    try:
        cutoff = time.time() - 86400
        for fname in os.listdir(BATCH_DOWNLOAD_DIR):
            fpath = os.path.join(BATCH_DOWNLOAD_DIR, fname)
            if os.path.isfile(fpath) and "批量下载_" in fname:
                if os.path.getmtime(fpath) < cutoff:
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
    except Exception:
        pass

    name_counter = {}

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for doc_id in selected_ids:
            doc = db.get_document(doc_id)
            if not doc:
                continue

            title = doc.get("title", "无标题")
            doc_no = doc.get("document_no", "")
            sl = doc.get("sensitivity_level", "公开")

            can_dl, reason = _can_download_by_sensitivity(sl)
            if not can_dl:
                skipped += 1
                not_downloaded.append({
                    "文件名称": title,
                    "文号": doc_no,
                    "发文单位": doc.get("issuing_authority", ""),
                    "原因": f"敏感级别限制: {reason}",
                    "建议处理": "联系管理员或调整下载权限配置",
                })
                continue

            fp = doc.get("file_path", "")
            if not fp:
                no_file += 1
                not_downloaded.append({
                    "文件名称": title,
                    "文号": doc_no,
                    "发文单位": doc.get("issuing_authority", ""),
                    "原因": "无原文件路径",
                    "建议处理": "上传原文件后可下载",
                })
                continue

            if not os.path.isfile(fp):
                file_missing += 1
                not_downloaded.append({
                    "文件名称": title,
                    "文号": doc_no,
                    "发文单位": doc.get("issuing_authority", ""),
                    "原因": "原文件不存在",
                    "建议处理": "重新上传原文件",
                })
                continue

            try:
                ext = os.path.splitext(fp)[1]
                if doc_no:
                    zip_entry = _clean_zip_filename(f"{doc_no}_{title}")
                else:
                    zip_entry = _clean_zip_filename(title)
                if ext:
                    zip_entry += ext

                if zip_entry in name_counter:
                    name_counter[zip_entry] += 1
                    base, e = os.path.splitext(zip_entry)
                    zip_entry = f"{base}_{name_counter[zip_entry]}{e}"
                else:
                    name_counter[zip_entry] = 1

                zf.write(fp, arcname=zip_entry)
                packed += 1
            except Exception as e:
                download_failed += 1
                not_downloaded.append({
                    "文件名称": title,
                    "文号": doc_no,
                    "发文单位": doc.get("issuing_authority", ""),
                    "原因": f"文件读取失败: {str(e)[:100]}",
                    "建议处理": "检查原文件是否可读",
                })

    st.session_state["batch_dl_report"] = {
        "total_selected": total_selected,
        "packed": packed,
        "no_file": no_file,
        "file_missing": file_missing,
        "download_failed": download_failed,
        "skipped": skipped,
        "not_downloaded": not_downloaded,
    }
    st.session_state["batch_dl_zip_path"] = zip_path
    st.session_state["show_batch_dl_result"] = True

    db.log_operation({
        "action": "批量下载",
        "target_type": "document",
        "notes": f"选中 {total_selected}，成功打包 {packed}，无原文件 {no_file}，文件不存在 {file_missing}，失败 {download_failed}，跳过 {skipped}",
    })


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

    # 标题异常检测
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
        from modules.document_parser import analyze_document, safe_fetch_from_url
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
        # ── 构建业务类型选项（含自定义类型） ──
        all_bt_options = _build_business_type_options()
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
            # 业务类型：multiselect + 自定义输入
            cur_bt = [t.strip() for t in doc.get("business_tags", "").split(",") if t.strip()]
            bt_preset = [t for t in cur_bt if t in BUSINESS_TYPE_OPTIONS]
            bt_custom = [t for t in cur_bt if t not in BUSINESS_TYPE_OPTIONS]
            bt_selected = st.multiselect("业务类型（预设）", BUSINESS_TYPE_OPTIONS, default=bt_preset)
            bt_custom_input = st.text_input("自定义业务类型（逗号分隔）", value=",".join(bt_custom),
                placeholder="如：城市更新类, 历史遗留用地类")
            # importance_level
            cur_il = doc.get("importance_level", IMPORTANCE_LEVEL_DEFAULT)
            il_idx = IMPORTANCE_LEVEL_OPTIONS.index(cur_il) if cur_il in IMPORTANCE_LEVEL_OPTIONS else IMPORTANCE_LEVEL_OPTIONS.index(IMPORTANCE_LEVEL_DEFAULT)
            importance_level = st.selectbox("文件重要级别", IMPORTANCE_LEVEL_OPTIONS, index=il_idx,
                help="文件重要级别用于人工标记该政策文件在项目审查中的重要程度，不代表政策效力状态。")
            cur_sl = doc.get("sensitivity_level", "公开")
            sl_idx = SENSITIVITY_LEVEL_OPTIONS.index(cur_sl) if cur_sl in SENSITIVITY_LEVEL_OPTIONS else 0
            sl = st.selectbox("敏感级别", SENSITIVITY_LEVEL_OPTIONS, index=sl_idx)
            summary = st.text_area("摘要", value=doc.get("summary", ""), height=60)
            revision_history = st.text_area("文件沿革", value=doc.get("revision_history", ""), height=60)
            full_text = st.text_area("正文全文", value=doc.get("full_text", ""), height=200)
            notes = st.text_area("备注", value=doc.get("notes", ""), height=60)

            if st.form_submit_button("保存修改"):
                old_sl = doc.get("sensitivity_level", "")
                # 合并业务类型
                final_bt = _merge_business_tags(bt_selected, bt_custom_input)
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
                    "business_tags": final_bt,
                    "importance_level": importance_level,
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
        il = doc.get("importance_level", IMPORTANCE_LEVEL_DEFAULT)
        st.markdown(f"**文件重要级别：** {il}")
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




# ═══════════ 政策文件查询主页 ═══════════
from utils.ui import render_app_header
render_app_header("政策文件查询", "检索、筛选和维护已入库政策文件")

# ═══════════ 搜索和筛选栏 ═══════════
_allowed_statuses = list(DOC_STATUS_OPTIONS)
# 强制清理 session_state 中残留的旧状态值
for _bad_key in ["status_filter", "status_filter_v2", "文件状态"]:
    old_val = st.session_state.get(_bad_key)
    if old_val and old_val not in (["全部"] + _allowed_statuses):
        st.session_state[_bad_key] = "全部"

# 构建业务类型选项（含自定义）
all_bt_options = _build_business_type_options()

col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    keyword = st.text_input("搜索", placeholder="文件名称 / 文号 / 发文单位 / 关键词 / 业务类型")
with col2:
    status_filter = st.selectbox("文件状态", ["全部"] + _allowed_statuses, key="status_filter_v2")
with col3:
    region_filter = st.selectbox("适用地区", ["全部"] + REGION_OPTIONS)
with col4:
    category_filter = st.selectbox("文件类别", ["全部"] + DOC_CATEGORY_OPTIONS)

col5, col6, col7, col8 = st.columns([1, 1, 1, 1])
with col5:
    bt_filter = st.selectbox("业务类型", all_bt_options)
with col6:
    title_status_filter = st.selectbox("标题状态", ["全部", "正常标题", "标题异常"])
with col7:
    il_filter = st.selectbox("文件重要级别", ["全部"] + IMPORTANCE_LEVEL_OPTIONS)
with col8:
    sl_filter = st.selectbox("敏感级别", ["全部"] + SENSITIVITY_LEVEL_OPTIONS)

# ═══════════ 统计栏 ═══════════
_stat_kw = keyword
_stat_st = "" if status_filter == "全部" else status_filter
_stat_rg = "" if region_filter == "全部" else region_filter
_stat_cat = "" if category_filter == "全部" else category_filter
_stat_il = "" if il_filter == "全部" else il_filter
_stat_sl = "" if sl_filter == "全部" else sl_filter
_stat_ts = title_status_filter

# 业务类型：判断是否选择的是分隔符
_bt_key = "" if bt_filter == "全部" else bt_filter
if _bt_key and _bt_key.startswith("──"):
    _bt_key = ""

stats = db.get_document_stats(
    _stat_kw, _stat_st, _stat_rg, _stat_cat, _bt_key,
    importance_level=_stat_il, sensitivity_level=_stat_sl,
)
total_count = stats["total"]
valid_count = stats["by_status"].get("现行有效", 0)
pending_count = stats["by_status"].get("待核实", 0)
abolished_count = stats["by_status"].get("已废止", 0) + stats["by_status"].get("已失效", 0)
core_count = stats.get("by_importance", {}).get("核心", 0)
important_count = stats.get("by_importance", {}).get("重要", 0)
normal_count = stats.get("by_importance", {}).get("一般", 0)

bt_line = ""
if _bt_key:
    bt_line = f"<span>业务类型：<b>{_bt_key}</b></span>　"

st.markdown(
    f"""
    <div style="padding:8px 14px;border:1px solid #e5e7eb;border-radius:8px;background:#f9fafb;font-size:13px;line-height:1.8;">
    <b>当前筛选：</b>共 {total_count} 份
    {bt_line}
    <span>现行有效：{valid_count}</span>
    <span>待核实：{pending_count}</span>
    <span>废止/失效：{abolished_count}</span>
    <span>核心：{core_count}</span>
    <span>重要：{important_count}</span>
    <span>一般：{normal_count}</span>
    <span>有原文件：{stats['with_file']}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# 非标准状态检查
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
    if stats.get("by_importance"):
        st.markdown("**文件重要级别分布**")
        il_sorted = sorted(stats["by_importance"].items(), key=lambda x: x[1], reverse=True)
        il_data = [{"重要级别": k, "数量": v} for k, v in il_sorted]
        st.dataframe(il_data, use_container_width=True, hide_index=True)

# ═══════════ 分页 ═══════════
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
    if st.session_state.get("_prev_page_size", 50) != st.session_state["page_size"]:
        st.session_state["current_page"] = 1
    st.session_state["_prev_page_size"] = st.session_state["page_size"]

total_pages = max(1, (total_count + st.session_state["page_size"] - 1) // st.session_state["page_size"])
if st.session_state["current_page"] > total_pages:
    st.session_state["current_page"] = total_pages
offset = (st.session_state["current_page"] - 1) * st.session_state["page_size"]

st.caption(f"第 {st.session_state['current_page']} / {total_pages} 页，共 {total_count} 条记录")

# ═══════════ 批量操作区域 ═══════════
# 初始化 session state
for key in ["selected_ids", "show_delete_confirm", "show_batch_dl_result",
            "batch_dl_zip_path", "batch_dl_report", "show_batch_bt_modal",
            "show_batch_il_modal"]:
    if key not in st.session_state:
        st.session_state[key] = set() if key == "selected_ids" else False if "show" in key or "modal" in key else None

# 跟踪筛选条件，变化时清空选中
_filter_key = f"{_stat_kw}|{_stat_st}|{_stat_rg}|{_stat_cat}|{_bt_key}|{_stat_il}|{_stat_sl}|{st.session_state['current_page']}|{_stat_ts}"
if st.session_state.get("_last_filter_key", "") != _filter_key:
    st.session_state["selected_ids"] = set()
    st.session_state["_last_filter_key"] = _filter_key

# ── 获取当前页数据 ──
_fetch_limit = st.session_state["page_size"] * 5 if _stat_ts in ("正常标题", "标题异常") else st.session_state["page_size"]
_fetch_offset = 0 if _stat_ts in ("正常标题", "标题异常") else offset
docs_raw = db.search_documents(
    keyword=_stat_kw,
    status=_stat_st,
    region=_stat_rg,
    category=_stat_cat,
    business_type=_bt_key,
    importance_level=_stat_il,
    sensitivity_level=_stat_sl,
    limit=_fetch_limit,
    offset=_fetch_offset,
)

# 标题状态过滤（Python 层面）
if _stat_ts == "标题异常":
    docs_raw = [d for d in docs_raw if detect_invalid_title(d.get("title", ""))]
elif _stat_ts == "正常标题":
    docs_raw = [d for d in docs_raw if not detect_invalid_title(d.get("title", ""))]

if _stat_ts in ("正常标题", "标题异常"):
    total_count = len(docs_raw)
    docs = docs_raw[offset:offset + st.session_state["page_size"]]
else:
    docs = docs_raw

current_page_ids = [doc["id"] for doc in docs]
sel_count = len(st.session_state["selected_ids"])

# ── 批量操作按钮栏 ──
st.markdown(f"**已选择 {sel_count} 份文件**")
col_batch1, col_batch2, col_batch3, col_batch4, col_batch5, col_batch6 = st.columns([1, 1, 1, 1, 1, 3])
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

# 批量下载
with col_batch4:
    if st.button(f"⬇ 批量下载({sel_count})" if sel_count > 0 else "⬇ 批量下载",
                 key="batch_download_btn", disabled=sel_count == 0, use_container_width=True):
        _perform_batch_download()
        st.rerun()

# 批量删除
with col_batch5:
    if st.button(f"🗑 批量删除({sel_count})" if sel_count > 0 else "🗑 批量删除",
                 key="batch_delete_btn", type="primary" if sel_count > 0 else "secondary",
                 disabled=sel_count == 0, use_container_width=True):
        st.session_state["show_delete_confirm"] = True
        st.rerun()

# 批量修改重要级别 & 业务类型
with col_batch6:
    sub_col1, sub_col2 = st.columns(2)
    with sub_col1:
        if st.button(f"📝 批量改重要级别({sel_count})" if sel_count > 0 else "📝 改重要级别",
                     key="batch_il_btn", disabled=sel_count == 0, use_container_width=True):
            st.session_state["show_batch_il_modal"] = True
            st.rerun()
    with sub_col2:
        if st.button(f"🏷 批量追加业务类型({sel_count})" if sel_count > 0 else "🏷 追加业务类型",
                     key="batch_bt_btn", disabled=sel_count == 0, use_container_width=True):
            st.session_state["show_batch_bt_modal"] = True
            st.rerun()


# ── 批量下载结果 ──
if st.session_state.get("show_batch_dl_result") and st.session_state.get("batch_dl_report"):
    st.markdown("---")
    report = st.session_state["batch_dl_report"]
    with st.container(border=True):
        st.subheader("📦 批量下载结果")
        cols = st.columns(5)
        cols[0].metric("选中文件数", report["total_selected"])
        cols[1].metric("成功打包", report["packed"])
        cols[2].metric("无原文件", report["no_file"])
        cols[3].metric("文件不存在", report["file_missing"])
        cols[4].metric("下载失败/跳过", report.get("download_failed", 0) + report.get("skipped", 0))

        # 下载 ZIP
        zip_path = st.session_state.get("batch_dl_zip_path", "")
        if zip_path and os.path.isfile(zip_path):
            with open(zip_path, "rb") as f:
                st.download_button(
                    "📥 下载 ZIP 文件",
                    data=f.read(),
                    file_name=os.path.basename(zip_path),
                    mime="application/zip",
                    key="dl_batch_zip",
                )

        # 导出未下载清单
        if report.get("not_downloaded"):
            import pandas as pd
            nd_df = pd.DataFrame(report["not_downloaded"])
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                nd_df.to_excel(writer, index=False, sheet_name="未下载清单")
            st.download_button(
                "📥 导出未下载清单 Excel",
                data=excel_buffer.getvalue(),
                file_name=f"未下载清单_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_not_downloaded",
            )

    if st.button("清除下载结果", key="clear_dl_result"):
        st.session_state["show_batch_dl_result"] = False
        st.session_state["batch_dl_report"] = None
        st.session_state["batch_dl_zip_path"] = ""
        st.rerun()


# ── 批量删除确认 ──
if st.session_state.get("show_delete_confirm") and st.session_state["selected_ids"]:
    st.markdown("---")
    with st.container(border=True):
        st.warning(f"⚠️ 即将删除 **{len(st.session_state['selected_ids'])}** 条文件记录，请确认是否继续。")
        preview_ids = list(st.session_state["selected_ids"])
        preview_data = []
        for pid in preview_ids[:50]:
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
                time.sleep(0.5)
                st.rerun()
        with del_col3:
            if st.button("取消", key="del_cancel"):
                st.session_state["show_delete_confirm"] = False
                st.rerun()


# ── 批量修改重要级别弹窗 ──
if st.session_state.get("show_batch_il_modal") and st.session_state["selected_ids"]:
    st.markdown("---")
    with st.container(border=True):
        st.subheader(f"批量修改文件重要级别（选中 {sel_count} 份）")
        new_il = st.selectbox("选择新的重要级别", IMPORTANCE_LEVEL_OPTIONS, key="batch_new_il")
        il_col1, il_col2 = st.columns([2, 3])
        with il_col1:
            if st.button("确认修改", key="cfm_batch_il", type="primary"):
                ids_list = list(st.session_state["selected_ids"])
                updated = 0
                for did in ids_list:
                    try:
                        db.update_document(did, {"importance_level": new_il})
                        updated += 1
                    except Exception:
                        pass
                db.log_operation({
                    "action": "批量修改重要级别",
                    "target_type": "document",
                    "notes": f"修改 {updated} 份文件重要级别为「{new_il}」",
                })
                st.success(f"已修改 {updated} 份文件的重要级别为「{new_il}」")
                st.session_state["show_batch_il_modal"] = False
                st.session_state["selected_ids"] = set()
                time.sleep(0.5)
                st.rerun()
        with il_col2:
            if st.button("取消", key="cancel_batch_il"):
                st.session_state["show_batch_il_modal"] = False
                st.rerun()


# ── 批量追加业务类型弹窗 ──
if st.session_state.get("show_batch_bt_modal") and st.session_state["selected_ids"]:
    st.markdown("---")
    with st.container(border=True):
        st.subheader(f"批量追加业务类型（选中 {sel_count} 份）")
        st.caption("追加：在现有业务类型基础上增加，不会覆盖已有标签。")
        bt_preset = st.multiselect("预设业务类型", BUSINESS_TYPE_OPTIONS, key="batch_bt_preset")
        bt_custom = st.text_input("自定义业务类型（逗号分隔）", key="batch_bt_custom",
            placeholder="如：城市更新类, 历史遗留用地类")
        bt_col1, bt_col2 = st.columns([2, 3])
        with bt_col1:
            if st.button("确认追加", key="cfm_batch_bt", type="primary"):
                new_tags = _merge_business_tags(bt_preset, bt_custom)
                if not new_tags:
                    st.warning("请至少选择或输入一个业务类型")
                else:
                    ids_list = list(st.session_state["selected_ids"])
                    updated = 0
                    for did in ids_list:
                        try:
                            doc = db.get_document(did)
                            if doc:
                                existing = set(t.strip() for t in doc.get("business_tags", "").split(",") if t.strip())
                                existing.update(t.strip() for t in new_tags.split(",") if t.strip())
                                merged = ",".join(sorted(existing))
                                db.update_document(did, {"business_tags": merged})
                                updated += 1
                        except Exception:
                            pass
                    db.log_operation({
                        "action": "批量追加业务类型",
                        "target_type": "document",
                        "notes": f"追加 {updated} 份文件业务类型「{new_tags}」",
                    })
                    st.success(f"已为 {updated} 份文件追加业务类型「{new_tags}」")
                    st.session_state["show_batch_bt_modal"] = False
                    st.session_state["selected_ids"] = set()
                    time.sleep(0.5)
                    st.rerun()
        with bt_col2:
            if st.button("取消", key="cancel_batch_bt"):
                st.session_state["show_batch_bt_modal"] = False
                st.rerun()


# ═══════════ 文件列表 ═══════════
st.markdown("---")
st.subheader("政策文件列表")

for doc in docs:
    doc_id = doc["id"]
    with st.container():
        col_cb, col_main, col_action = st.columns([0.5, 5.5, 1])
        with col_cb:
            is_selected = doc_id in st.session_state["selected_ids"]
            checked = st.checkbox(
                "",
                value=is_selected,
                key=f"sel_doc_{doc_id}",
                label_visibility="collapsed",
            )
            if checked and not is_selected:
                st.session_state["selected_ids"].add(doc_id)
            elif not checked and is_selected:
                st.session_state["selected_ids"].discard(doc_id)
        with col_main:
            # 第一行：标题
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
                # 截断过长标题
                display = display_title[:60] + "…" if len(display_title) > 60 else display_title
                st.markdown(f"**《{display}》**")

            # 第二行：文号｜发文单位｜发布日期
            line2_parts = []
            if doc.get("document_no"):
                line2_parts.append(doc["document_no"])
            if doc.get("issuing_authority"):
                line2_parts.append(doc["issuing_authority"])
            if doc.get("publish_date"):
                line2_parts.append(doc["publish_date"])
            if line2_parts:
                st.caption("｜".join(line2_parts))

            # 第三行：标签
            tag_parts = []
            status_display = normalize_document_status(doc.get("status", ""))
            status_color = {
                "现行有效": "green", "已废止": "red", "已失效": "red",
                "被替代": "orange", "部分废止": "orange", "即将失效": "orange",
            }
            color = status_color.get(status_display, "grey")
            tag_parts.append(f":{color}[{status_display}]")

            bt = doc.get("business_tags", "")
            if bt:
                bt_short = " / ".join([t.strip() for t in bt.split(",") if t.strip()][:3])
                if bt_short:
                    tag_parts.append(f"📌 {bt_short}")

            il = doc.get("importance_level", IMPORTANCE_LEVEL_DEFAULT)
            il_icon = {"核心": "⭐", "重要": "🔶", "一般": "🔹", "参考": "📎", "待评估": "❓"}.get(il, "")
            tag_parts.append(f"{il_icon} {il}")

            sl = doc.get("sensitivity_level", "公开")
            sl_icon = {"公开": "🌐", "内部": "🔒", "敏感": "⚠️", "涉密禁止上传": "🚫"}.get(sl, "")
            tag_parts.append(f"{sl_icon} {sl}")

            has_file = bool(doc.get("file_path") and os.path.isfile(doc.get("file_path", "")))
            tag_parts.append("📁 有原文件" if has_file else "📭 无原文件")

            tag_html = " ".join(
                f"<span style='background:#e8f0fe;color:#1a73e8;padding:2px 6px;border-radius:4px;font-size:0.8em;margin-right:3px;'>{t}</span>"
                for t in tag_parts
            )
            st.markdown(tag_html, unsafe_allow_html=True)

        with col_action:
            if st.button("查看", key=f"view_{doc_id}"):
                st.session_state["view_doc_id"] = doc_id
                st.rerun()
    st.markdown("---")

# ═══════════ 分页导航 ═══════════
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
