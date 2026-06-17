"""批量上传文件 UI 共享模块

供 2_document_import.py 和 1_document_library.py 的 Tab2 统一使用。
实现需求五：上传后进入待确认队列，每个文件三按钮操作，顶部清空/取消。
"""

import os
import uuid
import sqlite3
import shutil
import streamlit as st

import database.db as db
from config import (
    UPLOADS_DIR,
    DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS, REGION_OPTIONS,
    SAVE_POLICY_FILE, POLICY_FILES_DIR,
    BUSINESS_TYPE_OPTIONS, SENSITIVITY_LEVEL_OPTIONS,
    IMPORTANCE_LEVEL_OPTIONS, IMPORTANCE_LEVEL_DEFAULT,
    APP_VERSION,
)
from modules.document_parser import parse_file, get_supported_types
from modules.metadata_extractor import extract_all_metadata, classify_document
from modules.classifier import classify_business_tags
from modules.import_validator import validate_import_candidate


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


def _cleanup_temp_file(file_path: str):
    """安全删除临时上传文件"""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass


def _set_flash(uploader_key: str, level: str, message: str):
    """把提示信息暂存到 session_state，避免 st.rerun() 后提示丢失。

    这里不直接 st.success，因为入库后通常会 st.rerun() 刷新队列；
    先把消息存起来，下一轮渲染时再显示。
    """
    st.session_state[f"{uploader_key}_flash"] = {
        "id": uuid.uuid4().hex,
        "level": level,
        "message": message,
    }


def _clear_flash(uploader_key: str):
    """用户开始新一轮上传时，清理上一轮提示。"""
    flash_key = f"{uploader_key}_flash"
    st.session_state.pop(flash_key, None)
    # 清理 toast 已显示标记，避免 session_state 长期堆积。
    for key in list(st.session_state.keys()):
        if key.startswith(f"{flash_key}_toast_seen_"):
            st.session_state.pop(key, None)


def _show_flash(uploader_key: str):
    """显示入库/移除结果提示。

    成功入库后同时显示页面提示和右上角 toast，避免用户在页面底部点击后
    看不到顶部提示，以为按钮没有反应。
    """
    flash_key = f"{uploader_key}_flash"
    flash = st.session_state.get(flash_key)
    if not flash:
        return
    level = flash.get("level", "info")
    msg = flash.get("message", "")

    toast_seen_key = f"{flash_key}_toast_seen_{flash.get('id', '')}"
    if msg and not st.session_state.get(toast_seen_key):
        try:
            if level == "success":
                st.toast(msg, icon="✅")
            elif level == "warning":
                st.toast(msg, icon="⚠️")
            elif level == "error":
                st.toast(msg, icon="❌")
            else:
                st.toast(msg, icon="ℹ️")
        except Exception:
            # 老版本 Streamlit 没有 st.toast 时，保留页面提示即可。
            pass
        st.session_state[toast_seen_key] = True

    if level == "success":
        st.success(f"✅ {msg}")
    elif level == "warning":
        st.warning(msg)
    elif level == "error":
        st.error(msg)
    else:
        st.info(msg)


def _reset_uploader_widget(uploader_key: str):
    """重置文件选择控件，避免 st.rerun 后同一文件被反复解析、反复入库。"""
    counter_key = f"{uploader_key}_reset_counter"
    st.session_state[counter_key] = int(st.session_state.get(counter_key, 0)) + 1
    st.session_state.pop(f"{uploader_key}_last_upload_sig", None)


def _remove_batch_item(index: int):
    """从待确认队列中移除一个文件。"""
    batch = st.session_state.get("upload_batch", [])
    if 0 <= index < len(batch):
        batch[index] = None
    remaining = [item for item in batch if item is not None]
    if remaining:
        st.session_state["upload_batch"] = remaining
    else:
        st.session_state.pop("upload_batch", None)


def _clear_stale_batch_after_version_update(uploader_key: str) -> bool:
    """程序版本更新后，清理旧版本已解析但未入库的待录入队列。

    Streamlit 有时会保留浏览器会话里的旧 session_state，导致替换代码后页面还显示旧解析结果。
    这里用 APP_VERSION 标记解析版本，发现旧队列就清空并要求重新上传。
    """
    batch = st.session_state.get("upload_batch", [])
    if not batch:
        return False
    stale = any((item or {}).get("app_version") != APP_VERSION for item in batch if item is not None)
    if not stale:
        return False
    for item in batch:
        if item:
            _cleanup_temp_file(item.get("path", ""))
    st.session_state.pop("upload_batch", None)
    st.session_state.pop(f"{uploader_key}_last_upload_sig", None)
    _reset_uploader_widget(uploader_key)
    _set_flash(uploader_key, "warning", f"程序已更新到 {APP_VERSION}，旧解析队列已清空，请重新上传文件以使用新版识别规则。")
    return True


def _copy_policy_file_if_needed(item: dict) -> str:
    """保存上传原文到政策文件目录，返回保存路径。"""
    if not (SAVE_POLICY_FILE and os.path.exists(item.get("path", ""))):
        return ""
    os.makedirs(POLICY_FILES_DIR, exist_ok=True)
    dest_name = f"{uuid.uuid4().hex}_{item['name']}"
    policy_dest = os.path.join(POLICY_FILES_DIR, dest_name)
    shutil.copy2(item["path"], policy_dest)
    return policy_dest


def _handle_duplicate_before_insert(data: dict) -> dict:
    """入库前查重，避免重复点击导致 SQLite 唯一约束报错。"""
    return db.check_duplicate(
        title=data.get("title", ""),
        document_no=data.get("document_no", ""),
        file_name=data.get("file_name", ""),
        file_size=data.get("file_size", 0),
        full_text=data.get("full_text", ""),
    )


def render_batch_upload_ui(uploader_key: str = "policy_file_uploader"):
    """渲染批量上传文件UI。

    流程：
    1. 文件选择器 → 并行解析 → 存入 upload_batch
    2. 显示待确认队列，每个文件卡片有3个操作按钮
    3. 顶部有清空本次上传 / 取消全部待录入按钮
    """
    supported_types = get_supported_types()
    st.caption(f"支持格式：{', '.join(supported_types)}")
    _show_flash(uploader_key)
    if _clear_stale_batch_after_version_update(uploader_key):
        st.rerun()

    # 使用动态 key 创建上传控件。入库/取消后重置 key，防止同一个上传文件在 rerun 后被重新解析、重新加入待录入队列。
    reset_counter_key = f"{uploader_key}_reset_counter"
    st.session_state.setdefault(reset_counter_key, 0)
    uploader_widget_key = f"{uploader_key}_{st.session_state[reset_counter_key]}"

    uploaded_files = st.file_uploader(
        "选择政策文件（可一次选择多个）",
        type=supported_types,
        accept_multiple_files=True,
        key=uploader_widget_key,
        label_visibility="collapsed",
    )

    if uploaded_files:
        upload_sig = (APP_VERSION, tuple((uf.name, getattr(uf, "size", 0), getattr(uf, "type", "")) for uf in uploaded_files))
        sig_key = f"{uploader_key}_last_upload_sig"

        # 只有文件选择发生变化时才解析。否则 st.rerun 会把同一文件重复加入队列。
        if st.session_state.get(sig_key) != upload_sig:
            st.info(f"已选择 {len(uploaded_files)} 个文件，正在解析...")
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def process_one(uf):
                safe_name = f"{uuid.uuid4().hex}_{uf.name}"
                file_path = os.path.join(UPLOADS_DIR, safe_name)
                with open(file_path, "wb") as f:
                    f.write(uf.read())
                try:
                    text = parse_file(file_path, pdf_max_pages=15)
                    meta = extract_all_metadata(text, file_name=uf.name)
                    return {"name": uf.name, "path": file_path, "text": text, "meta": meta, "error": None, "app_version": APP_VERSION}
                except Exception as e:
                    return {"name": uf.name, "path": file_path, "text": "", "meta": {}, "error": str(e), "app_version": APP_VERSION}

            pending = []
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {ex.submit(process_one, uf): uf for uf in uploaded_files}
                for fut in as_completed(futures):
                    pending.append(fut.result())

            st.session_state["upload_batch"] = pending
            st.session_state[sig_key] = upload_sig

    batch = st.session_state.get("upload_batch", [])
    if batch:
        st.markdown("---")

        # ── 顶部操作栏：清空本次上传 / 取消全部待录入 ──
        remaining_items = [item for item in batch if item is not None]
        if remaining_items:
            st.subheader(f"待确认录入队列（共 {len(remaining_items)} 个文件）")
            col_top1, col_top2, col_top3 = st.columns([1.2, 1.2, 8])
            with col_top1:
                if st.button("清空本次上传", key=f"{uploader_key}_clear_all",
                             type="secondary", use_container_width=True):
                    for item in remaining_items:
                        _cleanup_temp_file(item.get("path", ""))
                    st.session_state.pop("upload_batch", None)
                    _reset_uploader_widget(uploader_key)
                    _set_flash(uploader_key, "info", "已清空所有待录入文件，临时文件已删除。")
                    st.rerun()
            with col_top2:
                if st.button("取消全部待录入", key=f"{uploader_key}_cancel_all",
                             type="secondary", use_container_width=True):
                    for item in remaining_items:
                        _cleanup_temp_file(item.get("path", ""))
                    st.session_state.pop("upload_batch", None)
                    _reset_uploader_widget(uploader_key)
                    _set_flash(uploader_key, "info", "已取消全部待录入，未写入数据库。")
                    st.rerun()
            with col_top3:
                st.caption("清空/取消都会清空待录入队列，并重置上传控件，避免重复入库。")

        st.markdown("---")

        for i, item in enumerate(batch):
            if item is None:
                continue

            with st.container():
                if item["error"]:
                    st.error(f"  {item['name']} — 解析失败: {item['error']}")
                    # 失败的文件也允许移除
                    if st.button("移除", key=f"{uploader_key}_rm_err_{i}"):
                        _cleanup_temp_file(item.get("path", ""))
                        _remove_batch_item(i)
                        _set_flash(uploader_key, "info", f"已移除「{item['name']}」，未入库。")
                        st.rerun()
                else:
                    meta = item["meta"]
                    text = item["text"]
                    raw_title = meta.get("title", "")

                    validation = validate_import_candidate(
                        title=raw_title,
                        document_no=meta.get("document_no") or "",
                        text=text,
                        file_name=item["name"],
                    )

                    st.markdown(
                        f"**文件 {i+1}：{item['name']}**"
                        f"（{len(text)} 字）"
                    )

                    v_level = validation["level"]
                    v_color = {"可入库": "green", "待人工确认": "orange", "不建议入库": "red"}.get(v_level, "grey")
                    st.markdown(
                        f"标题质量：:<span style='color:{v_color}'>{v_level}</span> "
                        f"— {validation['reason']}",
                        unsafe_allow_html=True,
                    )
                    if validation.get("suggestion"):
                        st.caption(f"💡 {validation['suggestion']}")

                    cols = st.columns(4)
                    with cols[0]:
                        st.metric("识别标题", raw_title[:20] or "未识别")
                    with cols[1]:
                        st.metric("识别文号", meta.get("document_no", "未识别") or "未识别")
                    with cols[2]:
                        st.metric("发文单位", meta.get("issuing_authority", "未识别") or "未识别")
                    with cols[3]:
                        st.metric("发布日期", meta.get("publish_date", "未识别") or "未识别")

                    with st.expander("查看正文 / 修改元数据并入库"):
                        st.text_area(
                            "", text[:3000], height=150, disabled=True,
                            label_visibility="collapsed",
                            key=f"{uploader_key}_preview_{i}",
                        )

                        form_key = f"{uploader_key}_form_{i}"
                        with st.form(form_key):
                            default_title = raw_title if validation["valid"] else ""
                            title = st.text_input(
                                "文件名称 *",
                                value=default_title,
                                key=f"{uploader_key}_t_{i}",
                                placeholder="标题识别失败，请手工填写有效文件名称"
                                if not validation["valid"] else "",
                            )
                            if title.strip() and title.strip() != raw_title:
                                manual_v = validate_import_candidate(
                                    title=title.strip(),
                                    document_no=meta.get("document_no") or "",
                                    text=text,
                                    file_name=item["name"],
                                )
                                if not manual_v["valid"]:
                                    st.warning(f"⚠️ {manual_v['reason']} — {manual_v.get('suggestion', '')}")

                            c1, c2 = st.columns(2)
                            with c1:
                                doc_no = st.text_input(
                                    "文号",
                                    value=meta.get("document_no", "") or "",
                                    key=f"{uploader_key}_dn_{i}",
                                )
                                authority = st.text_input(
                                    "发文单位",
                                    value=meta.get("issuing_authority", "") or "",
                                    key=f"{uploader_key}_au_{i}",
                                )
                                pub_date = st.text_input(
                                    "发布日期",
                                    value=meta.get("publish_date", "") or "",
                                    key=f"{uploader_key}_pd_{i}",
                                )
                            with c2:
                                eff_date = st.text_input(
                                    "实施日期",
                                    value=meta.get("effective_date", "") or "",
                                    key=f"{uploader_key}_ed_{i}",
                                )
                                exp_date = st.text_input(
                                    "失效日期",
                                    value=meta.get("expiry_date", "") or "",
                                    key=f"{uploader_key}_xd_{i}",
                                )
                                s = meta.get("status", "待核实")
                                st_idx = DOC_STATUS_OPTIONS.index(s) if s in DOC_STATUS_OPTIONS else DOC_STATUS_OPTIONS.index("待核实")
                                status = st.selectbox(
                                    "文件状态", DOC_STATUS_OPTIONS, index=st_idx,
                                    key=f"{uploader_key}_st_{i}",
                                )

                            region = st.selectbox("适用地区", REGION_OPTIONS, key=f"{uploader_key}_rg_{i}")
                            suggested_cat = classify_document(
                                title.strip() or raw_title, meta.get("document_no", ""), text)
                            cat_idx = DOC_CATEGORY_OPTIONS.index(suggested_cat) if suggested_cat in DOC_CATEGORY_OPTIONS else DOC_CATEGORY_OPTIONS.index("其他")
                            category = st.selectbox(
                                "文件类别", DOC_CATEGORY_OPTIONS, index=cat_idx,
                                key=f"{uploader_key}_cg_{i}",
                            )
                            keywords = st.text_input("关键词", key=f"{uploader_key}_kw_{i}")

                            auto_bt = classify_business_tags(
                                title.strip() or raw_title, keywords, text)
                            bt_selected = st.multiselect(
                                "业务类型（预设）", BUSINESS_TYPE_OPTIONS, default=auto_bt,
                                key=f"{uploader_key}_bt_{i}",
                            )
                            bt_custom = st.text_input(
                                "自定义业务类型（逗号分隔）",
                                key=f"{uploader_key}_bt_cust_{i}",
                                placeholder="如：城市更新类, 历史遗留用地类",
                            )

                            il = st.selectbox(
                                "文件重要级别", IMPORTANCE_LEVEL_OPTIONS,
                                index=IMPORTANCE_LEVEL_OPTIONS.index(IMPORTANCE_LEVEL_DEFAULT),
                                key=f"{uploader_key}_il_{i}",
                                help="文件重要级别用于人工标记该政策文件在项目审查中的重要程度，不代表政策效力状态。",
                            )
                            sl = st.selectbox(
                                "敏感级别", SENSITIVITY_LEVEL_OPTIONS,
                                index=0, key=f"{uploader_key}_sl_{i}",
                            )
                            notes = st.text_input("备注", key=f"{uploader_key}_nt_{i}")

                            # ── 三按钮操作栏 ──
                            val_for_btn = validation if title.strip() == raw_title else validate_import_candidate(
                                title=title.strip(),
                                document_no=doc_no.strip() if doc_no else "",
                            )
                            can_confirm = bool(title.strip()) and val_for_btn["valid"]
                            confirm_help = ""
                            if not title.strip():
                                confirm_help = "请填写文件名称"
                            elif not can_confirm:
                                confirm_help = val_for_btn.get("suggestion", "标题不合格，请手工修改")

                            col_act1, col_act2, col_act3 = st.columns(3)
                            with col_act1:
                                confirm = st.form_submit_button(
                                    "确认入库",
                                    disabled=not can_confirm,
                                    help=confirm_help if not can_confirm else "",
                                    type="primary",
                                )
                            with col_act2:
                                modify_confirm = st.form_submit_button(
                                    "修改后入库",
                                    disabled=not bool(title.strip()),
                                    help="请填写文件名称" if not title.strip() else "",
                                )
                            with col_act3:
                                remove = st.form_submit_button("不录入并移除")

                            # ── 确认入库 / 修改后入库 处理 ──
                            def build_data(policy_path: str = "") -> dict:
                                final_bt = _merge_business_tags(bt_selected, bt_custom)
                                return {
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
                                    "business_tags": final_bt,
                                    "importance_level": il,
                                    "sensitivity_level": sl,
                                    "file_name": item["name"],
                                    "file_size": (os.path.getsize(item["path"]) if os.path.exists(item["path"]) else 0),
                                    "file_type": os.path.splitext(item["name"])[1].lstrip("."),
                                    "full_text": text,
                                    "source_type": "上传",
                                    "file_path": policy_path,
                                    "confirmed": 1,
                                    "notes": notes.strip() if notes else "",
                                }

                            def do_insert(action_label: str):
                                if "涉密禁止上传" in sl:
                                    st.error("该级别文件禁止上传本系统")
                                    return
                                if not title.strip():
                                    st.error("文件名称不能为空")
                                    return

                                # 先查重，再复制原文件、写数据库，避免重复点击造成 UNIQUE constraint failed。
                                data_for_check = build_data(policy_path="")
                                dup = _handle_duplicate_before_insert(data_for_check)
                                if dup.get("is_duplicate"):
                                    _cleanup_temp_file(item.get("path", ""))
                                    _remove_batch_item(i)
                                    _reset_uploader_widget(uploader_key)
                                    _set_flash(
                                        uploader_key,
                                        "warning",
                                        f"未重复入库：{dup.get('reason', '疑似重复')}。文件《{title.strip()}》可能已经在文件库中。",
                                    )
                                    st.rerun()
                                    return

                                policy_path = ""
                                try:
                                    policy_path = _copy_policy_file_if_needed(item)
                                    data = build_data(policy_path=policy_path)
                                    doc_id = db.create_document(data)
                                    db.log_operation({
                                        "action": action_label, "target_type": "document",
                                        "target_id": doc_id, "file_name": item["name"],
                                        "sensitivity_level": sl,
                                    })
                                except sqlite3.IntegrityError as e:
                                    # 兜底：即使查重遗漏，也不能让页面崩掉。
                                    if "documents.document_no" in str(e):
                                        if policy_path and os.path.exists(policy_path):
                                            _cleanup_temp_file(policy_path)
                                        _cleanup_temp_file(item.get("path", ""))
                                        _remove_batch_item(i)
                                        _reset_uploader_widget(uploader_key)
                                        _set_flash(
                                            uploader_key,
                                            "warning",
                                            f"未重复入库：文号「{doc_no.strip() if doc_no else ''}」已存在。",
                                        )
                                        st.rerun()
                                        return
                                    raise

                                _cleanup_temp_file(item.get("path", ""))
                                _remove_batch_item(i)
                                _reset_uploader_widget(uploader_key)
                                suffix = "（已使用修改后的元数据）" if action_label.endswith("修改后入库") else ""
                                _set_flash(uploader_key, "success", f"《{title.strip()}》入库成功！{suffix}")
                                st.rerun()

                            if confirm:
                                do_insert("文件上传")

                            if modify_confirm:
                                do_insert("文件上传（修改后入库）")

                            # ── 不录入并移除 处理 ──
                            if remove:
                                _cleanup_temp_file(item.get("path", ""))
                                _remove_batch_item(i)
                                _reset_uploader_widget(uploader_key)
                                _set_flash(uploader_key, "info", f"已移除「{item['name']}」，未入库。")
                                st.rerun()

            st.markdown("---")

        # 清理已处理的文件（正常按钮处理会即时 rerun；这里作为兜底，不再额外 rerun，避免循环刷新）
        if batch:
            remaining = [item for item in batch if item is not None]
            if remaining:
                st.session_state["upload_batch"] = remaining
            else:
                st.session_state.pop("upload_batch", None)
