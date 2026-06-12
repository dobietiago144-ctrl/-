"""政策废止监测 — 候选池管理页面"""

import time
import streamlit as st

import database.db as db
from config import (
    OFFICIAL_POLICY_SOURCES, MONITOR_KEYWORDS,
    MONITOR_CANDIDATE_TYPES, MONITOR_CANDIDATE_STATUSES,
    ENABLE_AUTO_UPDATE_LIBRARY, DOC_STATUS_OPTIONS,
    BUSINESS_TYPE_OPTIONS, SENSITIVITY_LEVEL_OPTIONS,
)
from modules.policy_monitor import (
    get_monitor_keywords, get_monitor_candidates, get_monitor_candidate,
    save_monitor_candidate, update_monitor_candidate,
    confirm_candidate_to_library, ignore_candidate,
    mark_old_document_status, check_official_source,
    detect_obsolete_keywords, match_existing_documents,
    delete_monitor_candidate, add_manual_monitor_url, is_allowed_mnr_url,
    is_url_in_library, is_url_in_candidates, is_url_ignored,
    extract_obsolete_items_from_text, match_affected_items_with_library,
    parse_mnr_policy_library_detail,
    search_mnr_policy_library_by_keyword,
    safe_fetch_html, _extract_main_text,
)
from config import POLICY_MONITOR_TEST_URLS, POLICY_MONITOR_KEYWORDS
import json
from modules.status_utils import normalize_document_status

st.set_page_config(page_title="政策废止监测", page_icon="🔍", layout="wide")

st.title("🔍 政策废止监测")
st.caption("手动检查官方公开网站，发现废止/失效/替代政策，进入候选池后由人工确认")

# 安全提醒
st.info(
    "⚠️ **安全边界：** "
    "只访问配置中的官方域名 | 不访问任意URL | 不携带Cookie | "
    "不自动修改正式库（ENABLE_AUTO_UPDATE_LIBRARY = False）"
)

# ═══════════ 监测配置展示 ═══════════
with st.expander("📋 监测配置"):
    st.markdown(f"**监测模式**: {st.session_state.get('run_mode_label', '未知')}")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**官方来源**:")
        for s in OFFICIAL_POLICY_SOURCES:
            st.markdown(f"- {s['source_name']} ({s['domain']})")
    with col_b:
        st.markdown("**监测关键词**:")
        kw_cols = st.columns(3)
        for i, kw in enumerate(MONITOR_KEYWORDS):
            with kw_cols[i % 3]:
                st.markdown(f"- {kw}")

# ═══════════ 手动检查 ═══════════
st.subheader("手动检查")

source_options = {s["source_name"]: s for s in OFFICIAL_POLICY_SOURCES}
col_chk1, col_chk2 = st.columns(2)
check_results = {}

with col_chk1:
    st.markdown("#### 自然资源部")
    if st.button("🔍 立即检查自然资源部", key="check_mnr", type="primary", use_container_width=True):
        with st.spinner("正在访问自然资源部官网..."):
            source = source_options["自然资源部-政策"]
            result = check_official_source(source)
            check_results["mnr"] = result
            # 保存候选结果到数据库
            for c in result.get("candidates", []):
                try:
                    cid = save_monitor_candidate(c)
                    check_results.setdefault("saved", []).append(cid)
                except Exception:
                    pass
            st.session_state["last_mnr_check"] = result
            st.rerun()

    mnr_result = st.session_state.get("last_mnr_check")
    if mnr_result:
        if mnr_result.get("error"):
            st.error(f"检查失败: {mnr_result['error']}")
        else:
            new_c = mnr_result.get("new_count", 0)
            in_lib = mnr_result.get("in_library_count", 0)
            in_cand = mnr_result.get("in_candidates_count", 0)
            ignored = mnr_result.get("ignored_count", 0)
            dup = mnr_result.get("duplicate_count", 0)
            fail = mnr_result.get("failed_count", 0)
            scanned = mnr_result.get("scanned_count", 0)
            st.success(
                f"扫描 {scanned} 条链接 | "
                f"新增候选 **{new_c}** | "
                f"已在库 {in_lib} | "
                f"已在候选池 {in_cand} | "
                f"已忽略 {ignored} | "
                f"重复 {dup} | "
                f"失败 {fail}"
            )

with col_chk2:
    st.markdown("#### 广东省自然资源厅")
    if st.button("🔍 立即检查广东省自然资源厅", key="check_gd", type="primary", use_container_width=True):
        with st.spinner("正在访问广东省自然资源厅官网..."):
            source = source_options["广东省自然资源厅-政策法规"]
            result = check_official_source(source)
            check_results["gd"] = result
            for c in result.get("candidates", []):
                try:
                    cid = save_monitor_candidate(c)
                    check_results.setdefault("saved", []).append(cid)
                except Exception:
                    pass
            st.session_state["last_gd_check"] = result
            st.rerun()

    gd_result = st.session_state.get("last_gd_check")
    if gd_result:
        if gd_result.get("error"):
            st.error(f"检查失败: {gd_result['error']}")
        else:
            new_c = gd_result.get("new_count", 0)
            st.success(f"新增候选 **{new_c}** | 已在库 {gd_result.get('in_library_count', 0)} | 已忽略 {gd_result.get('ignored_count', 0)}")

# ═══════════ 关键词搜索 ═══════════
st.markdown("---")
st.subheader("🔎 关键词搜索自然资源部")

kw_col1, kw_col2, kw_col3 = st.columns([3, 1, 3])
with kw_col1:
    search_keyword = st.selectbox(
        "选择搜索关键词",
        POLICY_MONITOR_KEYWORDS,
        index=0,
        key="search_keyword",
    )
with kw_col2:
    search_pages = st.selectbox("搜索页数", [1, 2, 3], index=2, key="search_pages")
with kw_col3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔍 关键词搜索", key="keyword_search_btn", type="primary", use_container_width=True):
        with st.spinner(f"正在搜索关键词「{search_keyword}」..."):
            search_results = search_mnr_policy_library_by_keyword(search_keyword, max_pages=search_pages)
            st.session_state["keyword_search_results"] = search_results
            st.session_state["keyword_search_term"] = search_keyword
            st.rerun()

# 关键词搜索结果
kw_results = st.session_state.get("keyword_search_results")
if kw_results is not None:
    kw_term = st.session_state.get("keyword_search_term", "")
    if kw_results:
        st.success(f"关键词「{kw_term}」搜索到 **{len(kw_results)}** 条结果")
        for i, r in enumerate(kw_results[:20]):
            with st.container():
                st.markdown(f"**{i+1}.** [{r.get('title', '无标题')[:60]}]({r.get('url', '')})")
                st.caption(f"🔑 命中: {r.get('detected_keywords', '')}")
                if r.get("snippet"):
                    st.caption(f"📝 {r['snippet'][:150]}...")
                # 快速加入候选
                if st.button(f"加入候选池 #{i+1}", key=f"add_kw_{i}"):
                    try:
                        html, ferr = safe_fetch_html(r["url"], timeout=20)
                        if ferr:
                            html = ""
                        detail = {
                            "source_name": f"关键词搜索: {kw_term}",
                            "source_domain": "mnr.gov.cn",
                            "source_url": r["url"],
                            "title": r.get("title", ""),
                            "detected_keywords": r.get("detected_keywords", ""),
                            "candidate_type": "废止公告" if "废止" in r.get("detected_keywords", "") else "其他",
                            "relation_type_guess": "疑似废止" if "废止" in r.get("detected_keywords", "") else "其他",
                            "status": "已抓取待确认",
                        }
                        if html:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(html, "html.parser")
                            parsed = parse_mnr_policy_library_detail(html, r["url"])
                            detail["title"] = parsed.get("title", "") or r.get("title", "")
                            detail["document_no"] = parsed.get("document_no", "")
                            detail["publish_date"] = parsed.get("publish_date", "")
                            detail["full_text"] = parsed.get("full_text", "")
                            full_text = parsed.get("full_text", "") or _extract_main_text(soup)
                            obsolete_items = extract_obsolete_items_from_text(full_text)
                            detail["affected_items"] = json.dumps(obsolete_items, ensure_ascii=False)
                        cid = save_monitor_candidate(detail)
                        st.success(f"已加入候选池 (ID: {cid})")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"加入失败: {e}")
        st.markdown("---")
    else:
        st.info(f"关键词「{kw_term}」未搜索到结果")

# ═══════════ 手动添加监测链接 ═══════════
st.markdown("---")
st.subheader("🔗 手动添加监测链接")
manual_col1, manual_col2 = st.columns([4, 1])
with manual_col1:
    manual_url = st.text_input(
        "政策链接",
        placeholder="https://f.mnr.gov.cn/202606/t20260605_2931308.html",
        key="manual_monitor_url",
        label_visibility="collapsed",
    )
with manual_col2:
    if st.button("抓取并预览", key="manual_fetch_btn", type="secondary", use_container_width=True):
        if not manual_url.strip():
            st.error("请输入链接")
        elif not is_allowed_mnr_url(manual_url.strip()):
            st.error("仅支持自然资源部官方域名 (mnr.gov.cn)")
        elif is_url_in_library(manual_url.strip()):
            st.warning("该链接已在正式文件库中存在")
        elif is_url_in_candidates(manual_url.strip()):
            st.warning("该链接已在候选池中")
        elif is_url_ignored(manual_url.strip()):
            st.warning("该链接已被忽略")
        else:
            with st.spinner("正在抓取..."):
                result = add_manual_monitor_url(manual_url.strip())
                if result.get("preview"):
                    st.session_state["manual_preview"] = result["preview"]
                    st.session_state["manual_url"] = manual_url.strip()
                    st.rerun()
                elif result["success"]:
                    st.success(result["message"])
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning(result["message"])

# 手动添加预览确认
manual_preview = st.session_state.get("manual_preview")
if manual_preview:
    with st.container(border=True):
        st.subheader("解析预览")
        p = manual_preview
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st.markdown(f"**标题**: {p.get('title', '（未识别）')}")
            st.markdown(f"**文号**: {p.get('document_no', '（空）')}")
            st.markdown(f"**发布机构**: {p.get('issuing_authority', '（空）')}")
            st.markdown(f"**发布日期**: {p.get('publish_date', '（空）')}")
        with col_p2:
            st.markdown(f"**时效状态**: {p.get('status_from_source', '（空）')}")
            st.markdown(f"**效力级别**: {p.get('effectiveness_level', '（空）')}")
            st.markdown(f"**候选类型**: {p.get('candidate_type', '')}")
            st.markdown(f"**命中关键词**: {p.get('detected_keywords', '')}")

        if p.get("obsolete_items"):
            st.markdown(f"**被废止旧文件数量**: {p['obsolete_count']}")
            st.markdown("**被废止旧文件**:")
            for i, item in enumerate(p["obsolete_items"], 1):
                match_info = ""
                if item.get("matched"):
                    match_info = f" — 📎 已匹配: 《{item['matched_title']}》(ID: {item['matched_id']})"
                else:
                    match_info = " — ❓ 未匹配文件库"
                st.markdown(f"{i}. 《{item['old_title']}》{match_info}")
                if item.get("old_document_no"):
                    st.caption(f"   文号: {item['old_document_no']}")

        col_confirm, col_cancel = st.columns([1, 4])
        with col_confirm:
            if st.button("确认加入候选池", key="confirm_manual_import", type="primary"):
                import json as _json
                detail = {
                    "source_name": "手动添加",
                    "source_domain": "mnr.gov.cn",
                    "source_url": st.session_state.get("manual_url", ""),
                    "title": p.get("title", ""),
                    "document_no": p.get("document_no", ""),
                    "publish_date": p.get("publish_date", ""),
                    "full_text": p.get("full_text", ""),
                    "candidate_type": p.get("candidate_type", "其他"),
                    "detected_keywords": p.get("detected_keywords", ""),
                    "relation_type_guess": "疑似废止" if "废止" in p.get("detected_keywords", "") else "其他",
                    "status": "已抓取待确认",
                    "affected_items": _json.dumps(p.get("obsolete_items", []), ensure_ascii=False),
                }
                cid = save_monitor_candidate(detail)
                st.success(f"已加入候选池 (ID: {cid})")
                del st.session_state["manual_preview"]
                del st.session_state["manual_url"]
                time.sleep(0.5)
                st.rerun()
        with col_cancel:
            if st.button("取消", key="cancel_manual_import"):
                del st.session_state["manual_preview"]
                del st.session_state["manual_url"]
                st.rerun()

# ═══════════ 测试链接验证 ═══════════
with st.expander("🧪 测试链接验证", expanded=False):
    st.caption("内置测试链接 + 手动批量输入，用于验证监测解析质量")
    test_urls_default = "\n".join(POLICY_MONITOR_TEST_URLS)
    test_urls_input = st.text_area(
        "测试链接（一行一个）", value=test_urls_default, height=100, key="test_urls_input"
    )
    if st.button("批量测试抓取", key="batch_test_btn"):
        test_urls = [u.strip() for u in test_urls_input.split("\n") if u.strip()]
        test_results = []
        for t_url in test_urls[:10]:
            r = {"url": t_url, "allowed": is_allowed_mnr_url(t_url)}
            if not r["allowed"]:
                r["error"] = "非允许域名"
                test_results.append(r)
                continue
            if is_url_ignored(t_url):
                r["error"] = "已被忽略"
                test_results.append(r)
                continue
            result = add_manual_monitor_url(t_url)
            if result.get("preview"):
                p = result["preview"]
                r.update({
                    "title": p.get("title", ""),
                    "document_no": p.get("document_no", ""),
                    "issuing_authority": p.get("issuing_authority", ""),
                    "publish_date": p.get("publish_date", ""),
                    "status_from_source": p.get("status_from_source", ""),
                    "detected_keywords": p.get("detected_keywords", ""),
                    "candidate_type": p.get("candidate_type", ""),
                    "obsolete_count": p.get("obsolete_count", 0),
                    "error": "",
                })
            else:
                r["error"] = result.get("message", "抓取失败")
            test_results.append(r)

        st.session_state["test_results"] = test_results

    test_results = st.session_state.get("test_results", [])
    if test_results:
        test_data = []
        for r in test_results:
            test_data.append({
                "URL": r["url"][:50],
                "允许": "是" if r.get("allowed") else "否",
                "标题": r.get("title", "")[:30],
                "文号": r.get("document_no", ""),
                "发布": r.get("publish_date", ""),
                "时效": r.get("status_from_source", ""),
                "关键词": r.get("detected_keywords", "")[:20],
                "候选类型": r.get("candidate_type", ""),
                "旧文件数": r.get("obsolete_count", 0),
                "错误": r.get("error", "")[:30],
            })
        st.dataframe(test_data, use_container_width=True, hide_index=True)

# ═══════════ 候选池 ═══════════
st.markdown("---")
st.subheader("📥 废止监测候选池")

# 筛选
filter_col1, filter_col2 = st.columns([1, 4])
with filter_col1:
    candidate_status_filter = st.selectbox(
        "状态筛选", ["全部"] + MONITOR_CANDIDATE_STATUSES, key="monitor_status_filter"
    )
candidates = get_monitor_candidates(
    status="" if candidate_status_filter == "全部" else candidate_status_filter,
    limit=100,
)

st.caption(f"共 **{len(candidates)}** 条候选记录")

if candidates:
    for i, c in enumerate(candidates):
        with st.container():
            cid = c["id"]
            c_status = c.get("status", "")
            c_type = c.get("candidate_type", "")

            st.markdown(
                f"**{i+1}. 《{c.get('title', '无标题')}》** "
                f"| :grey[{c.get('source_name', '')}] "
                f"| :blue[{c_type}] "
                f"| :orange[{c_status}]"
            )
            st.caption(
                f"文号: {c.get('document_no', '（空）')} | "
                f"发布: {c.get('publish_date', '（空）')}"
            )
            if c.get("detected_keywords"):
                st.caption(f"🔑 命中关键词: {c.get('detected_keywords', '')}")
            if c.get("relation_basis_text"):
                st.caption(f"📝 命中句子: {c.get('relation_basis_text', '')[:120]}...")
            st.caption(f"候选类型: :blue[{c_type}] | 推测: {c.get('relation_type_guess', '')}")

            # 匹配信息
            if c.get("matched_document_id"):
                st.info(
                    f"📎 已匹配文件库: 《{c.get('matched_title', '')}》 "
                    f"(ID: {c['matched_document_id']}, 方式: {c.get('confidence', '')})"
                )

            # 推荐操作
            if "废止" in (c_type or ""):
                st.info("💡 推荐操作: 查看附件/目录，确认旧文件清理关系")
            elif c.get("matched_document_id") and ("废止" in (c.get("relation_type_guess", ""))):
                st.info("💡 推荐操作: 确认将匹配到的旧文件标记为已废止")

            # 操作按钮
            op_col1, op_col2, op_col3, op_col4, op_col5 = st.columns(5)

            with op_col1:
                detail_key = f"view_monitor_{cid}"
                if st.button("📄 查看详情", key=detail_key):
                    st.session_state["view_monitor_id"] = cid
                    st.rerun()

            with op_col2:
                if st.button("✅ 确认入库", key=f"confirm_{cid}"):
                    result = confirm_candidate_to_library(cid)
                    if result["success"]:
                        st.success(result["message"])
                        st.rerun()
                    else:
                        st.error(result["message"])

            with op_col3:
                if c.get("matched_document_id"):
                    matched_id = c["matched_document_id"]
                    matched_title = c.get("matched_title", "")
                    relation_guess = c.get("relation_type_guess", "")

                    if "废止" in relation_guess:
                        if st.button("📝 标为已废止", key=f"mark_abolish_{cid}"):
                            mark_old_document_status(
                                matched_id, "已废止",
                                f"根据 {c.get('source_name', '')} 监测结果",
                            )
                            # 建立新旧关系
                            new_doc_id = None
                            # 尝试查找新文件
                            if c.get("document_no"):
                                existing = db.get_document_by_no(c["document_no"])
                                if existing and existing["id"] != matched_id:
                                    new_doc_id = existing["id"]
                            if new_doc_id:
                                db.create_relation({
                                    "old_document_id": matched_id,
                                    "new_document_id": new_doc_id,
                                    "relation_type": "废止",
                                    "relation_basis": c.get("relation_basis_text", ""),
                                    "relation_date": c.get("publish_date", ""),
                                    "affected_scope": "全文",
                                    "confidence": "待核实",
                                    "notes": f"监测自动关联: {c.get('source_name', '')}",
                                })
                            update_monitor_candidate(cid, {
                                "status": "已确认入库",
                                "notes": f"已将旧文件《{matched_title}》标为已废止",
                            })
                            st.success(f"《{matched_title}》已标记为已废止")
                            time.sleep(0.5)
                            st.rerun()

                    if "失效" in relation_guess:
                        if st.button("📝 标为已失效", key=f"mark_expire_{cid}"):
                            mark_old_document_status(
                                matched_id, "已失效",
                                f"根据 {c.get('source_name', '')} 监测结果",
                            )
                            update_monitor_candidate(cid, {
                                "status": "已确认入库",
                                "notes": f"已将旧文件《{matched_title}》标为已失效",
                            })
                            st.success(f"《{matched_title}》已标记为已失效")
                            time.sleep(0.5)
                            st.rerun()

            with op_col4:
                if st.button("⏭ 忽略并删除", key=f"ignore_{cid}"):
                    ignore_candidate(cid, "人工忽略", add_to_ignored=True)
                    st.success("已忽略并删除，下次监测将跳过此链接")
                    time.sleep(0.5)
                    st.rerun()

            with op_col5:
                if st.button("🗑 仅删除", key=f"delete_{cid}"):
                    delete_monitor_candidate(cid)
                    st.success("已从候选池删除（下次监测仍可能重新发现）")
                    time.sleep(0.5)
                    st.rerun()
                    update_monitor_candidate(cid, {"status": "疑似重复"})
                    st.success("已标记")
                    time.sleep(0.5)
                    st.rerun()

        st.markdown("---")

else:
    st.info("暂无候选记录。请点击上方按钮手动检查官方来源。")

# ═══════════ 候选详情视图 ═══════════
view_id = st.session_state.get("view_monitor_id")
if view_id:
    cand = get_monitor_candidate(view_id)
    if cand:
        st.markdown("---")
        st.subheader(f"候选详情: {cand.get('title', '无标题')}")

        st.markdown(f"**来源**: {cand.get('source_name', '')}")
        st.markdown(f"**域名**: {cand.get('source_domain', '')}")
        st.markdown(f"**URL**: {cand.get('source_url', '')}")
        st.markdown(f"**文号**: {cand.get('document_no', '（空）')}")
        st.markdown(f"**发布日期**: {cand.get('publish_date', '（空）')}")
        st.markdown(f"**候选类型**: {cand.get('candidate_type', '')}")
        st.markdown(f"**监测关键词**: {cand.get('detected_keywords', '')}")
        st.markdown(f"**关系推测**: {cand.get('relation_type_guess', '')}")
        st.markdown(f"**匹配文件**: {cand.get('matched_title', '（无）')}")

        # 被废止旧文件清单
        affected_raw = cand.get("affected_items", "")
        if affected_raw:
            try:
                affected_items = json.loads(affected_raw) if isinstance(affected_raw, str) else affected_raw
            except Exception:
                affected_items = []
            if affected_items:
                st.markdown("---")
                st.markdown(f"### 📋 被废止旧文件清单（{len(affected_items)} 条）")
                match_affected_items_with_library(affected_items)
                for i, item in enumerate(affected_items, 1):
                    match_info = ""
                    if item.get("matched"):
                        match_info = f"📎 已匹配: 《{item['matched_title']}》(ID: {item['matched_id']})"
                    else:
                        match_info = "❓ 未匹配文件库"
                    st.markdown(f"**{i}.** 《{item['old_title']}》 {match_info}")
                    if item.get("old_document_no"):
                        st.caption(f"    文号: {item['old_document_no']}")
                    if item.get("basis_text"):
                        st.caption(f"    依据: {item['basis_text'][:150]}...")

                    # 操作按钮
                    if item.get("matched"):
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if st.button(f"确认废止 {item['old_title'][:15]}", key=f"cfm_abolish_{cand['id']}_{i}"):
                                mark_old_document_status(
                                    item["matched_id"], "已废止",
                                    f"根据自然资源部废止决定: {cand.get('title', '')}",
                                )
                                db.create_relation({
                                    "old_document_id": item["matched_id"],
                                    "new_document_id": None,
                                    "relation_type": "废止",
                                    "relation_basis": item.get("basis_text", ""),
                                    "relation_date": cand.get("publish_date", ""),
                                    "confidence": "待核实",
                                    "notes": f"监测候选ID: {cand['id']}",
                                })
                                st.success(f"已将《{item['matched_title']}》标为已废止")
                                time.sleep(0.5)
                                st.rerun()
                        with btn_col2:
                            if st.button(f"忽略 {item['old_title'][:15]}", key=f"ignore_item_{cand['id']}_{i}"):
                                st.info("已忽略该旧文件项")

        with st.expander("废止/替代依据文本"):
            st.text_area("", cand.get("relation_basis_text", ""), height=100, disabled=True, label_visibility="collapsed")

        with st.expander("全文预览"):
            st.text_area("", cand.get("full_text", "")[:5000], height=200, disabled=True, label_visibility="collapsed")

        with st.expander("摘要"):
            st.markdown(cand.get("summary", ""))
    else:
        st.error("候选记录不存在")

    if st.button("关闭详情"):
        del st.session_state["view_monitor_id"]
        st.rerun()

# ═══════════ 安全提醒 ═══════════
st.markdown("---")
st.caption(
    "安全配置: "
    f"ENABLE_AUTO_UPDATE_LIBRARY = {ENABLE_AUTO_UPDATE_LIBRARY} | "
    f"所有候选需人工确认后才写入正式库 | "
    f"不自动修改旧文件状态 | "
    f"不自动建立新旧关系"
)
