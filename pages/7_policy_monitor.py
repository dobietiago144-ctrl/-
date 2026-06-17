"""废止/失效依据库 — 维护废止决定、失效公告等依据文件，管理被影响政策清单"""

import time
import streamlit as st

import database.db as db
from config import (
    ENABLE_AUTO_UPDATE_LIBRARY,
)
from modules.policy_monitor import (
    get_monitor_candidates, get_monitor_candidate,
    save_monitor_candidate, update_monitor_candidate,
    ignore_candidate,
    delete_monitor_candidate, add_manual_monitor_url, is_allowed_mnr_url,
    is_url_in_library, is_url_in_candidates, is_url_ignored,
    extract_obsolete_items_from_text, match_affected_items_with_library,
    extract_abrogation_basis,
    safe_fetch_html,
)
import json
from utils.ui import render_app_header

# --- v7.2.0: 依据类型 ---
EVIDENCE_TYPES = [
    "废止决定", "失效公告", "清理结果", "现行有效目录",
    "修订文件", "替代文件", "普通政策", "待人工判断",
]

# --- v7.2.0: 处理状态 ---
PROCESS_STATUSES = [
    "全部", "待确认", "已确认", "已忽略", "已加入待补录", "已更新政策库",
]

# --- v7.2.2: 预览可编辑辅助函数 ---
def _items_to_edit_text(items: list[dict]) -> str:
    """将解析出的具体政策清单转成便于人工编辑的多行文本。
    格式：政策名称｜文号｜影响类型
    """
    lines = []
    for item in items or []:
        title = item.get("old_title", "")
        doc_no = item.get("old_document_no", "")
        rel = item.get("relation_type", "废止")
        if title:
            lines.append(f"{title}｜{doc_no}｜{rel}")
    return "\n".join(lines)


def _edit_text_to_items(text: str, old_items: list[dict] | None = None) -> list[dict]:
    """将人工编辑的多行文本转回具体政策清单。
    支持：
    1. 政策名称
    2. 政策名称｜文号
    3. 政策名称｜文号｜影响类型
    """
    old_items = old_items or []
    old_map = {i.get("old_title", ""): i for i in old_items if i.get("old_title")}
    items = []
    seen = set()

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        # 兼容 | / ｜ / tab / 逗号
        parts = [p.strip() for p in re.split(r"[｜|\t]", line)]
        if len(parts) == 1:
            parts = [p.strip() for p in re.split(r"，|,", line, maxsplit=2)]

        title = parts[0].strip().strip("《》")
        if not title or title in seen:
            continue
        seen.add(title)

        doc_no = parts[1].strip() if len(parts) >= 2 else ""
        relation_type = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else "废止"

        base = dict(old_map.get(title, {}))
        base.update({
            "old_title": title,
            "old_document_no": doc_no,
            "relation_type": relation_type,
            "matched": base.get("matched", False),
            "match_status": base.get("match_status", "未匹配"),
            "match_score": base.get("match_score", 0),
            "match_method": base.get("match_method", ""),
        })
        items.append(base)

    return items

def _mark_pending_item_status(evidence_id: int, affected_title: str, affected_doc_no: str = "", *, doc_id: int | None = None, status: str = "已补录"):
    """v7.2.4: 将待补录清单中的单条政策标记为已补录/暂不补录。

    旧版本“去补录”只是跳转，新增成功后原清单仍会显示。
    这里直接回写 affected_items JSON，后续待补录列表会自动过滤掉已补录/暂不补录项。
    """
    if not evidence_id or not affected_title:
        return

    cand = get_monitor_candidate(evidence_id)
    if not cand:
        return

    raw = cand.get("affected_items", "")
    try:
        items = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
    except Exception:
        items = []

    changed = False
    for item in items:
        title_match = (item.get("old_title", "") == affected_title)
        no_match = True
        if affected_doc_no:
            no_match = (item.get("old_document_no", "") == affected_doc_no)
        if title_match and no_match:
            item["pending_import_status"] = status
            if doc_id:
                item["matched"] = True
                item["matched_id"] = doc_id
                item["matched_document_id"] = doc_id
                item["matched_title"] = affected_title
                item["match_status"] = "已补录"
                item["match_method"] = "人工补录"
                item["match_score"] = 1.0
            elif status == "暂不补录":
                item["match_status"] = "暂不补录"
            changed = True
            break

    if changed:
        update_monitor_candidate(evidence_id, {
            "affected_items": json.dumps(items, ensure_ascii=False)
        })


def _unignore_url(url: str):
    """v7.2.5: 取消已忽略链接，让该链接可以重新抓取。"""
    if not url:
        return
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    conn = db.get_connection()
    try:
        conn.execute(
            "DELETE FROM policy_monitor_ignored_urls WHERE url = ? OR url_hash = ?",
            (url, url_hash),
        )
        conn.commit()
    finally:
        conn.close()



# ═══════════════════════════════════════════
#  Header
# ═══════════════════════════════════════════
render_app_header(
    "废止/失效依据库",
    "维护废止决定、失效公告、清理结果、现行有效目录等政策状态变化依据，"
    "并重点录入其中涉及的具体政策清单。"
)

st.info(
    "⚠️ **安全边界：** "
    "仅官方域名 | 不自动修改正式库 | 所有关系需人工二次确认 | "
    "未匹配文件仅进入待补录清单，不自动更新政策库"
)

# ═══════════════════════════════════════════
#  Section 1: 批量添加依据链接
# ═══════════════════════════════════════════
st.subheader("📎 批量添加依据链接")
st.caption("支持一次粘贴多个官网链接，一行一个。抓取失败不影响其他链接。")

batch_urls = st.text_area(
    "依据链接（一行一个）",
    placeholder="https://f.mnr.gov.cn/202606/t20260605_2931308.html\nhttps://f.mnr.gov.cn/202505/t20250501_2900001.html",
    height=120,
    key="batch_evidence_urls",
    label_visibility="collapsed",
)

col_b1, col_b2, col_b3, col_b4 = st.columns([1.5, 1, 1, 4])
with col_b1:
    if st.button("🔍 抓取并预览", key="batch_fetch_btn", type="primary", use_container_width=True):
        urls = [u.strip() for u in batch_urls.split("\n") if u.strip()]
        if not urls:
            st.error("请输入至少一个链接")
        else:
            previews = []
            failed = []
            progress = st.progress(0, text="正在抓取...")
            for idx, url in enumerate(urls):
                progress.progress((idx + 1) / len(urls), text=f"抓取 {idx+1}/{len(urls)}: {url[:60]}...")
                if not is_allowed_mnr_url(url):
                    failed.append({"url": url, "reason": "非允许域名"})
                    continue
                if is_url_ignored(url):
                    failed.append({"url": url, "reason": "已被忽略"})
                    continue
                if is_url_in_candidates(url):
                    failed.append({"url": url, "reason": "已在依据库中"})
                    continue
                result = add_manual_monitor_url(url, source_name="批量添加")
                if result.get("preview"):
                    previews.append({"url": url, "preview": result["preview"]})
                else:
                    failed.append({"url": url, "reason": result.get("message", "抓取失败")})
            progress.empty()
            st.session_state["batch_previews"] = previews
            st.session_state["batch_failed"] = failed
            st.rerun()

with col_b2:
    if st.button("🗑 清空", key="batch_clear_btn", use_container_width=True):
        st.session_state.pop("batch_previews", None)
        st.session_state.pop("batch_failed", None)
        st.session_state.pop("batch_evidence_urls", None)
        st.rerun()

# ═══════════════════════════════════════════
#  Section 2: 抓取预览区
# ═══════════════════════════════════════════
batch_previews = st.session_state.get("batch_previews", [])
batch_failed = st.session_state.get("batch_failed", [])

if batch_failed:
    with st.expander(f"⚠️ 抓取失败 ({len(batch_failed)} 条)", expanded=True):
        for fi, f in enumerate(batch_failed):
            reason = f.get("reason", "")
            url = f.get("url", "")
            if "已被忽略" in reason or "已忽略" in reason:
                c_fail1, c_fail2 = st.columns([5, 1.2])
                with c_fail1:
                    st.warning(f"**{url[:100]}**: {reason}")
                with c_fail2:
                    if st.button("取消忽略", key=f"unignore_failed_{fi}", use_container_width=True):
                        _unignore_url(url)
                        batch_failed.pop(fi)
                        st.session_state["batch_failed"] = batch_failed
                        st.success("已取消忽略，可重新抓取该链接。")
                        time.sleep(0.3)
                        st.rerun()
            else:
                st.warning(f"**{url[:100]}**: {reason}")

if batch_previews:
    st.subheader(f"📋 抓取预览（{len(batch_previews)} 条）")

    # v7.2.0: 批量操作
    col_ba1, col_ba2 = st.columns([1, 5])
    with col_ba1:
        if st.button("✅ 全部加入依据库", key="batch_confirm_all", type="primary"):
            import json as _json
            count = 0
            for bp in batch_previews:
                p = bp["preview"]
                try:
                    detail = {
                        "source_name": "批量添加",
                        "source_domain": "mnr.gov.cn",
                        "source_url": bp["url"],
                        "title": p.get("title", ""),
                        "document_no": p.get("document_no", ""),
                        "publish_date": p.get("publish_date", ""),
                        "full_text": p.get("full_text", ""),
                        "candidate_type": p.get("candidate_type", "其他"),
                        "detected_keywords": p.get("detected_keywords", ""),
                        "relation_basis_text": p.get("abrogation_basis", ""),
                        "status": "待确认",
                        "affected_items": _json.dumps(p.get("obsolete_items", []), ensure_ascii=False),
                    }
                    save_monitor_candidate(detail)
                    count += 1
                except Exception:
                    pass
            st.success(f"已加入 {count} 条到依据库")
            st.session_state.pop("batch_previews", None)
            st.session_state.pop("batch_failed", None)
            time.sleep(0.5)
            st.rerun()

    # 每个链接生成预览卡片
    for bi, bp in enumerate(batch_previews):
        url = bp["url"]
        p = bp["preview"]
        with st.container(border=True):
            # 卡片顶部：标题
            st.markdown(f"### {bi+1}. {p.get('title', '（未识别标题）')[:80]}")

            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                st.caption(f"**来源**: {p.get('issuing_authority', '自然资源部')}")
                st.caption(f"**文号**: {p.get('document_no', '（空）')}")
            with col_c2:
                st.caption(f"**发布日期**: {p.get('publish_date', '（空）')}")
                evidence_type = p.get('candidate_type', '待人工判断')
                if evidence_type == "废止决定":
                    st.error(f"**依据类型**: {evidence_type}")
                elif evidence_type in ("废止公告", "失效公告"):
                    st.warning(f"**依据类型**: {evidence_type}")
                else:
                    st.info(f"**依据类型**: {evidence_type}")
            with col_c3:
                st.caption(f"**命中关键词**: {p.get('detected_keywords', '（无）')}")
                st.caption(f"**原文链接**: [{url[:50]}...]({url})")

            # v7.2.2: 预览结果允许人工编辑，先修正再入库
            with st.expander("✏️ 编辑预览信息", expanded=False):
                st.caption("识别结果有小错误时，可在这里直接修正；保存后再点击“加入依据库”。")
                with st.form(f"edit_preview_form_{bi}"):
                    e_col1, e_col2 = st.columns(2)
                    with e_col1:
                        edit_title = st.text_input(
                            "依据标题",
                            value=p.get("title", ""),
                            key=f"edit_title_{bi}",
                        )
                        edit_doc_no = st.text_input(
                            "文号",
                            value=p.get("document_no", ""),
                            key=f"edit_doc_no_{bi}",
                        )
                        edit_issuer = st.text_input(
                            "发布机构 / 来源",
                            value=p.get("issuing_authority", ""),
                            key=f"edit_issuer_{bi}",
                        )
                    with e_col2:
                        edit_publish_date = st.text_input(
                            "发布日期",
                            value=p.get("publish_date", ""),
                            key=f"edit_publish_date_{bi}",
                            help="建议格式：YYYY-MM-DD；识别不到可留空。",
                        )
                        current_type = p.get("candidate_type", "待人工判断")
                        type_options = EVIDENCE_TYPES
                        type_index = type_options.index(current_type) if current_type in type_options else len(type_options) - 1
                        edit_candidate_type = st.selectbox(
                            "依据类型",
                            type_options,
                            index=type_index,
                            key=f"edit_candidate_type_{bi}",
                        )
                        edit_keywords = st.text_input(
                            "命中关键词",
                            value=p.get("detected_keywords", ""),
                            key=f"edit_keywords_{bi}",
                        )

                    edit_abrogation_basis = st.text_area(
                        "废止/失效依据段落",
                        value=p.get("abrogation_basis", ""),
                        height=120,
                        key=f"edit_abrogation_basis_{bi}",
                    )

                    st.markdown("**具体政策清单**")
                    st.caption("一行一个。格式建议：政策名称｜文号｜影响类型。文号没有可留空，例如：建设项目用地预审管理办法｜国土资源部令第7号｜废止")
                    edit_items_text = st.text_area(
                        "具体政策清单",
                        value=_items_to_edit_text(p.get("obsolete_items", [])),
                        height=160,
                        key=f"edit_items_text_{bi}",
                        label_visibility="collapsed",
                    )

                    edit_full_text = st.text_area(
                        "全文内容（一般不必改，可用于修正正文摘要或重新保存）",
                        value=p.get("full_text", ""),
                        height=180,
                        key=f"edit_full_text_{bi}",
                    )

                    save_edit = st.form_submit_button("💾 保存修改", type="primary")
                    if save_edit:
                        edited_items = _edit_text_to_items(edit_items_text, p.get("obsolete_items", []))
                        # 手动修改后重新匹配一次本地库，仍然只做精确匹配，避免误判
                        try:
                            match_affected_items_with_library(edited_items, deep_match=False)
                        except Exception:
                            pass

                        st.session_state["batch_previews"][bi]["preview"].update({
                            "title": edit_title.strip(),
                            "document_no": edit_doc_no.strip(),
                            "issuing_authority": edit_issuer.strip(),
                            "publish_date": edit_publish_date.strip(),
                            "candidate_type": edit_candidate_type,
                            "detected_keywords": edit_keywords.strip(),
                            "abrogation_basis": edit_abrogation_basis.strip(),
                            "obsolete_items": edited_items,
                            "obsolete_count": len(edited_items),
                            "full_text": edit_full_text,
                        })
                        st.success("已保存修改，请确认无误后加入依据库。")
                        time.sleep(0.3)
                        st.rerun()

            # 正文摘要
            with st.expander("📄 正文摘要"):
                st.text(p.get("full_text", "")[:1000] or "（无法提取正文）")

            # 废止依据段落
            abr = p.get("abrogation_basis", "")
            if abr:
                with st.expander("📝 废止/失效依据段落"):
                    st.text_area("依据段落", abr[:2000], height=100, disabled=True, label_visibility="collapsed")

            # 解析出的具体政策清单
            items = p.get("obsolete_items", [])
            if items:
                matched_count = sum(1 for it in items if it.get("matched"))
                unmatched_count = len(items) - matched_count
                st.markdown(f"**📋 解析出的具体政策清单**: {len(items)} 条（已匹配: {matched_count} | 未匹配: {unmatched_count}）")

                for j, item in enumerate(items, 1):
                    if item.get("matched"):
                        st.success(
                            f"  {j}. 📎 《{item['old_title']}》→ "
                            f"已匹配: 《{item['matched_title']}》（{item.get('match_method', '')}）"
                        )
                    else:
                        st.warning(
                            f"  {j}. ❓ 《{item['old_title']}》→ "
                            "**未匹配**（将进入待补录清单）"
                        )
                    if item.get("old_document_no"):
                        st.caption(f"      文号: {item['old_document_no']}")
            else:
                st.caption("未解析出具体政策清单")

            # 卡片操作
            col_act1, col_act2 = st.columns([1, 5])
            with col_act1:
                if st.button(f"✅ 加入依据库", key=f"batch_add_{bi}", type="primary"):
                    import json as _json
                    detail = {
                        "source_name": "批量添加",
                        "source_domain": "mnr.gov.cn",
                        "source_url": url,
                        "title": p.get("title", ""),
                        "document_no": p.get("document_no", ""),
                        "publish_date": p.get("publish_date", ""),
                        "full_text": p.get("full_text", ""),
                        "candidate_type": p.get("candidate_type", "其他"),
                        "detected_keywords": p.get("detected_keywords", ""),
                        "relation_basis_text": p.get("abrogation_basis", ""),
                        "status": "待确认",
                        "affected_items": _json.dumps(p.get("obsolete_items", []), ensure_ascii=False),
                    }
                    cid = save_monitor_candidate(detail)
                    st.success(f"已加入依据库 (ID: {cid})")
                    batch_previews.pop(bi)
                    st.session_state["batch_previews"] = batch_previews
                    time.sleep(0.5)
                    st.rerun()
            with col_act2:
                if st.button(f"⏭ 忽略", key=f"batch_ignore_{bi}"):
                    batch_previews.pop(bi)
                    st.session_state["batch_previews"] = batch_previews
                    st.rerun()

    st.markdown("---")

# ═══════════════════════════════════════════
#  Section 3: 依据库列表
# ═══════════════════════════════════════════
st.subheader("📚 废止/失效依据库")

filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 4])
with filter_col1:
    status_filter = st.selectbox(
        "状态", PROCESS_STATUSES, key="evidence_status_filter"
    )
with filter_col2:
    type_filter = st.selectbox(
        "依据类型", ["全部"] + EVIDENCE_TYPES, key="evidence_type_filter"
    )

candidates = get_monitor_candidates(
    status="" if status_filter == "全部" else status_filter,
    limit=200,
)

# 类型筛选（内存过滤）
if type_filter != "全部":
    candidates = [c for c in candidates if c.get("candidate_type") == type_filter]

st.caption(f"共 **{len(candidates)}** 条依据记录")

if candidates:
    for i, c in enumerate(candidates):
        with st.container():
            cid = c["id"]
            c_status = c.get("status", "")
            c_type = c.get("candidate_type", "")

            st.markdown(
                f"**{i+1}. 《{c.get('title', '无标题')[:60]}》**"
            )
            st.caption(
                f"文号: {c.get('document_no', '（空）')} | "
                f"发布: {c.get('publish_date', '（空）')} | "
                f"来源: {c.get('source_name', '')}"
            )
            st.caption(
                f"类型: :blue[{c_type}] | "
                f"关键词: {c.get('detected_keywords', '（无）')} | "
                f"状态: :orange[{c_status}]"
            )

            # 显示解析统计
            affected_raw = c.get("affected_items", "")
            item_count = 0
            matched_count = 0
            if affected_raw:
                try:
                    items = json.loads(affected_raw) if isinstance(affected_raw, str) else affected_raw
                    item_count = len(items)
                    matched_count = sum(1 for it in items if it.get("matched"))
                except Exception:
                    pass
            if item_count > 0:
                st.caption(f"📋 解析: {item_count} 个政策 | 已匹配本地库: {matched_count} | 未匹配: {item_count - matched_count}")

            # 操作按钮
            final_statuses = ("已确认", "已加入待补录", "已更新政策库")
            if c_status in final_statuses:
                # 已确认/已进入待补录流程后，不再显示“确认/忽略/加入待补录”三个流程按钮，避免重复操作。
                op_col1, op_col2, op_col3 = st.columns([1, 1, 6])
                with op_col1:
                    if st.button("📄 查看详情", key=f"view_ev_{cid}", use_container_width=True):
                        st.session_state["view_evidence_id"] = cid
                        st.session_state.pop("edit_evidence_id", None)
                        st.rerun()
                with op_col2:
                    if st.button("✏️ 编辑", key=f"edit_ev_{cid}", use_container_width=True):
                        st.session_state["view_evidence_id"] = cid
                        st.session_state["edit_evidence_id"] = cid
                        st.rerun()
            else:
                op_col1, op_col2, op_col3, op_col4 = st.columns(4)
                with op_col1:
                    if st.button("📄 查看详情", key=f"view_ev_{cid}"):
                        st.session_state["view_evidence_id"] = cid
                        st.session_state.pop("edit_evidence_id", None)
                        st.rerun()
                with op_col2:
                    if st.button("✅ 确认依据", key=f"confirm_ev_{cid}"):
                        update_monitor_candidate(cid, {"status": "已确认"})
                        st.success("已确认")
                        time.sleep(0.3)
                        st.rerun()
                with op_col3:
                    if st.button("⏭ 忽略", key=f"ignore_ev_{cid}"):
                        ignore_candidate(cid, "人工忽略", add_to_ignored=True)
                        st.success("已忽略")
                        time.sleep(0.3)
                        st.rerun()
                with op_col4:
                    if st.button("📝 加入待补录", key=f"pending_ev_{cid}"):
                        update_monitor_candidate(cid, {"status": "已加入待补录"})
                        st.success("已加入待补录清单")
                        time.sleep(0.3)
                        st.rerun()

        st.divider()
else:
    st.info("暂无依据记录。请在上方批量添加依据链接。")

# ═══════════════════════════════════════════
#  Section 4: 依据详情区
# ═══════════════════════════════════════════
view_id = st.session_state.get("view_evidence_id")
if view_id:
    cand = get_monitor_candidate(view_id)
    if cand:
        st.markdown("---")
        st.subheader(f"依据详情: {cand.get('title', '无标题')}")

        # 基本信息
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown(f"**依据标题**: {cand.get('title', '（无）')}")
            st.markdown(f"**文号**: {cand.get('document_no', '（空）')}")
            st.markdown(f"**发布机构**: {cand.get('source_name', '')}")
            st.markdown(f"**发布日期**: {cand.get('publish_date', '（空）')}")
        with col_d2:
            st.markdown(f"**依据类型**: :blue[{cand.get('candidate_type', '')}]")
            st.markdown(f"**命中关键词**: {cand.get('detected_keywords', '（无）')}")
            st.markdown(f"**处理状态**: :orange[{cand.get('status', '')}]")
            st.markdown(f"**原文链接**: [{cand.get('source_url', '')[:50]}...]({cand.get('source_url', '')})")

        # v7.2.5: 依据详情编辑
        if st.session_state.get("edit_evidence_id") == view_id:
            st.markdown("---")
            st.subheader("✏️ 编辑依据记录")
            affected_raw_for_edit = cand.get("affected_items", "")
            try:
                edit_items = json.loads(affected_raw_for_edit) if isinstance(affected_raw_for_edit, str) and affected_raw_for_edit else (affected_raw_for_edit or [])
            except Exception:
                edit_items = []

            with st.form(f"edit_evidence_form_{view_id}"):
                e1, e2 = st.columns(2)
                with e1:
                    edit_title = st.text_input("依据标题", value=cand.get("title", ""))
                    edit_doc_no = st.text_input("文号", value=cand.get("document_no", ""))
                    edit_publish_date = st.text_input("发布日期", value=cand.get("publish_date", ""))
                with e2:
                    cur_type = cand.get("candidate_type", "待人工判断")
                    type_idx = EVIDENCE_TYPES.index(cur_type) if cur_type in EVIDENCE_TYPES else len(EVIDENCE_TYPES) - 1
                    edit_type = st.selectbox("依据类型", EVIDENCE_TYPES, index=type_idx)
                    cur_status = cand.get("status", "待确认")
                    status_opts = [s for s in PROCESS_STATUSES if s != "全部"]
                    status_idx = status_opts.index(cur_status) if cur_status in status_opts else 0
                    edit_status = st.selectbox("处理状态", status_opts, index=status_idx)
                    edit_keywords = st.text_input("命中关键词", value=cand.get("detected_keywords", ""))

                edit_basis = st.text_area(
                    "废止/失效依据段落",
                    value=cand.get("relation_basis_text", ""),
                    height=120,
                )
                st.caption("具体政策清单：一行一个，格式：政策名称｜文号｜影响类型。已补录/暂不补录状态会尽量保留。")
                edit_items_text = st.text_area(
                    "具体政策清单",
                    value=_items_to_edit_text(edit_items),
                    height=180,
                )
                edit_summary = st.text_area("摘要", value=cand.get("summary", ""), height=80)

                save_edit, cancel_edit = st.columns([1, 5])
                with save_edit:
                    submitted_edit = st.form_submit_button("保存编辑", type="primary")
                with cancel_edit:
                    canceled_edit = st.form_submit_button("取消编辑")

                if canceled_edit:
                    st.session_state.pop("edit_evidence_id", None)
                    st.rerun()

                if submitted_edit:
                    new_items = _edit_text_to_items(edit_items_text, edit_items)
                    try:
                        match_affected_items_with_library(new_items, deep_match=True)
                    except Exception:
                        pass
                    update_monitor_candidate(view_id, {
                        "title": edit_title.strip(),
                        "document_no": edit_doc_no.strip(),
                        "publish_date": edit_publish_date.strip(),
                        "candidate_type": edit_type,
                        "status": edit_status,
                        "detected_keywords": edit_keywords.strip(),
                        "relation_basis_text": edit_basis.strip(),
                        "summary": edit_summary.strip(),
                        "affected_items": json.dumps(new_items, ensure_ascii=False),
                    })
                    st.session_state.pop("edit_evidence_id", None)
                    st.success("依据记录已更新")
                    time.sleep(0.3)
                    st.rerun()

        # 废止依据段落
        abr_text = cand.get("relation_basis_text", "")
        if abr_text:
            with st.expander("📝 废止/失效依据段落", expanded=True):
                st.text_area("依据段落", abr_text, height=120, disabled=True, label_visibility="collapsed")

        # 具体政策清单
        affected_raw = cand.get("affected_items", "")
        if affected_raw:
            try:
                affected_items = json.loads(affected_raw) if isinstance(affected_raw, str) else affected_raw
            except Exception:
                affected_items = []
        else:
            affected_items = []

        if affected_items:
            st.markdown("---")
            st.markdown(f"### 📋 具体政策清单（{len(affected_items)} 条）")

            # 重新匹配
            match_affected_items_with_library(affected_items, deep_match=True)

            matched = [it for it in affected_items if it.get("matched")]
            unmatched = [it for it in affected_items if not it.get("matched")]

            st.caption(f"已匹配本地库: **{len(matched)}** | 未匹配: **{len(unmatched)}**")

            if matched:
                st.markdown("#### 📎 已匹配政策")
                for it in matched:
                    st.success(
                        f"《{it['old_title']}》→ 已匹配: 《{it.get('matched_title', '')}》"
                        f"（{it.get('match_method', '')}）"
                    )
                    if it.get("old_document_no"):
                        st.caption(f"    文号: {it['old_document_no']}")
                    if it.get("basis_text"):
                        st.caption(f"    依据: {it['basis_text'][:200]}...")

            if unmatched:
                st.markdown("#### ❓ 未匹配政策（待补录）")
                for it in unmatched:
                    st.warning(
                        f"《{it['old_title']}》→ **建议加入待补录清单**"
                    )
                    if it.get("old_document_no"):
                        st.caption(f"    文号: {it['old_document_no']}")
                    if it.get("basis_text"):
                        st.caption(f"    依据: {it['basis_text'][:200]}...")
        else:
            st.info("未解析出具体政策清单")

        # 全文预览
        with st.expander("📄 全文预览"):
            st.text_area("全文", cand.get("full_text", "")[:5000], height=200, disabled=True, label_visibility="collapsed")

        # 操作按钮
        st.markdown("---")
        final_statuses_detail = ("已确认", "已加入待补录", "已更新政策库")
        if cand.get("status", "") in final_statuses_detail:
            d_col1, d_col2 = st.columns([1, 5])
            with d_col1:
                if st.button("✏️ 编辑依据", key=f"edit_detail_{view_id}", use_container_width=True):
                    st.session_state["edit_evidence_id"] = view_id
                    st.rerun()
            with d_col2:
                st.caption("该依据已确认或已进入待补录流程，流程按钮已隐藏；需要调整内容时请点击“编辑依据”。")
        else:
            st.markdown("### ⚡ 更新政策库操作")
            st.caption("以下操作需要人工确认后执行，将修改正式政策文件库。")
            col_up1, col_up2, col_up3 = st.columns(3)
            with col_up1:
                if st.button("🔄 更新已匹配文件状态", key=f"update_lib_{view_id}", type="primary", disabled=True,
                             help="v7.2.0: 待后续实现二次确认流程"):
                    st.info("此功能将在后续版本实现二次确认后启用")
            with col_up2:
                if st.button("📝 将未匹配项加入待补录", key=f"add_pending_{view_id}"):
                    update_monitor_candidate(view_id, {"status": "已加入待补录"})
                    st.success("未匹配项已标记为待补录")
                    time.sleep(0.3)
                    st.rerun()
            with col_up3:
                if st.button("⏭ 忽略此依据", key=f"ignore_detail_{view_id}"):
                    ignore_candidate(view_id, "人工忽略", add_to_ignored=True)
                    st.success("已忽略")
                    del st.session_state["view_evidence_id"]
                    time.sleep(0.3)
                    st.rerun()

    else:
        st.error("依据记录不存在")

    if st.button("✖ 关闭详情"):
        del st.session_state["view_evidence_id"]
        st.rerun()

# ═══════════════════════════════════════════
#  Section 5: 待补录清单
# ═══════════════════════════════════════════
st.markdown("---")
st.subheader("📝 待补录清单")
st.caption("以下是从依据文件中解析出、但本地政策文件库未收录的政策清单。")

# 查询所有已加入待补录的依据
pending_candidates = get_monitor_candidates(status="已加入待补录", limit=50)
# 也查询状态为"待确认"但其中有无匹配项的（显示为候选待补录）

all_pending_items = []
for pc in pending_candidates:
    raw = pc.get("affected_items", "")
    if raw:
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            items = []
        for it in items:
            pending_status = it.get("pending_import_status", "")
            if not it.get("matched") and pending_status not in ("已补录", "暂不补录", "不补录"):
                all_pending_items.append({
                    "evidence_title": pc.get("title", ""),
                    "evidence_url": pc.get("source_url", ""),
                    "evidence_id": pc["id"],
                    "affected_title": it.get("old_title", ""),
                    "affected_doc_no": it.get("old_document_no", ""),
                    "effect_type": it.get("relation_type", "废止"),
                    "basis_text": it.get("basis_text", "")[:200],
                })

if all_pending_items:
    st.caption(f"共 **{len(all_pending_items)}** 条待补录政策")

    # 按依据分组展示
    grouped = {}
    for pi in all_pending_items:
        key = pi["evidence_title"] or pi["evidence_url"]
        grouped.setdefault(key, []).append(pi)

    for ev_title, items in grouped.items():
        with st.expander(f"依据: {ev_title[:60]}（{len(items)} 条待补录）"):
            for i, pi in enumerate(items, 1):
                col_t1, col_t2, col_t3 = st.columns([3, 1, 1])
                with col_t1:
                    st.markdown(f"**{i}.** 《{pi['affected_title']}》")
                    st.caption(f"文号: {pi['affected_doc_no'] or '（无）'} | 影响: {pi['effect_type']}")
                with col_t2:
                    st.caption(f"来源: [{pi['evidence_url'][:30]}...]({pi['evidence_url']})")
                with col_t3:
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("📝 去补录", key=f"goto_import_{pi['evidence_id']}_{i}", use_container_width=True):
                            # 将待补录信息带到“政策文件录入”页顶部的快捷补录表单
                            status_map = {
                                "废止": "已废止",
                                "失效": "已失效",
                                "替代": "被替代",
                                "修改": "待核实",
                                "疑似": "待核实",
                            }
                            st.session_state["pending_import_prefill"] = {
                                "title": pi.get("affected_title", ""),
                                "document_no": pi.get("affected_doc_no", ""),
                                "status": status_map.get(pi.get("effect_type", ""), "待核实"),
                                "source_url": pi.get("evidence_url", ""),
                                "source_evidence_id": pi.get("evidence_id"),
                                "source_affected_title": pi.get("affected_title", ""),
                                "source_affected_doc_no": pi.get("affected_doc_no", ""),
                                "notes": (
                                    f"来源依据：{pi.get('evidence_title', '')}\n"
                                    f"影响类型：{pi.get('effect_type', '')}\n"
                                    f"依据片段：{pi.get('basis_text', '')}"
                                ),
                            }
                            try:
                                st.switch_page("pages/2_document_import.py")
                            except Exception:
                                st.success("已带入待补录信息，请点击左侧“政策文件录入”查看。")
                                st.rerun()
                    with btn_col2:
                        if st.button("⏭ 暂不补录", key=f"skip_import_{pi['evidence_id']}_{i}", use_container_width=True):
                            _mark_pending_item_status(
                                pi.get("evidence_id"),
                                pi.get("affected_title", ""),
                                pi.get("affected_doc_no", ""),
                                status="暂不补录",
                            )
                            st.toast("已标记为暂不补录")
                            st.rerun()
else:
    st.info("暂无待补录政策。将依据文件中未匹配的政策加入待补录清单后，会显示在此处。")

# ═══════════════════════════════════════════
#  Footer
# ═══════════════════════════════════════════
st.markdown("---")
st.caption(
    "安全配置: "
    f"ENABLE_AUTO_UPDATE_LIBRARY = {ENABLE_AUTO_UPDATE_LIBRARY} | "
    f"所有依据需人工确认 | 未匹配文件仅进入待补录清单 | "
    f"更新正式库需二次确认（v7.2.3）"
)
