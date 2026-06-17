"""首页 — 系统概览（v7.0.0 品牌化重构）"""

import streamlit as st
import database.db as db
from version import APP_VERSION, APP_UPDATE_DATE, VERSION_HISTORY
from utils.ui import (
    render_home_hero,
    render_feature_card,
    render_metric_card,
    render_notice,
    render_footer,
)


# ═══════════════════════════════════════════
#  1. 品牌 Hero 区
# ═══════════════════════════════════════════
render_home_hero()


# ═══════════════════════════════════════════
#  2. 主功能入口区（4 个大卡片）
# ═══════════════════════════════════════════
st.markdown(
    '<h3 style="color:#1F2937;font-weight:700;margin-bottom:16px;">功能入口</h3>',
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    render_feature_card(
        "政策文件录入",
        "上传政策文件，自动识别标题、文号、发文单位、日期等元数据。",
        "📤",
    )
with col2:
    render_feature_card(
        "政策文件查询",
        "检索、筛选、编辑和维护已入库政策文件，支持批量下载。",
        "📋",
    )
with col3:
    render_feature_card(
        "文档审查",
        "上传待审查文档，识别失效依据、错误文号和可替代文件。",
        "🔍",
    )
with col4:
    render_feature_card(
        "新旧关系",
        "维护废止文件、现行文件、传承关系和规则配置。",
        "🔗",
    )

st.markdown("<br>", unsafe_allow_html=True)


# ═══════════════════════════════════════════
#  3. 数据概览区（4 个小卡片）
# ═══════════════════════════════════════════
st.markdown(
    '<h3 style="color:#1F2937;font-weight:700;margin-bottom:16px;">数据概览</h3>',
    unsafe_allow_html=True,
)

stats = db.get_stats()

# 尝试获取今日新录入数量
today_new = "--"
try:
    conn = db.get_connection()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM documents WHERE DATE(created_at) = DATE('now','localtime')"
    ).fetchone()
    conn.close()
    if row:
        today_new = row["cnt"]
except Exception:
    pass

mc1, mc2, mc3, mc4 = st.columns(4)
with mc1:
    render_metric_card("政策文件总数", stats["total"])
with mc2:
    render_metric_card("现行有效", stats["valid"])
with mc3:
    render_metric_card("已废止/已失效", stats["abolished"])
with mc4:
    render_metric_card("今日新录入", today_new)

st.markdown("<br>", unsafe_allow_html=True)


# ═══════════════════════════════════════════
#  4. 最近更新区
# ═══════════════════════════════════════════
with st.expander("📋 最近版本更新", expanded=False):
    for v in VERSION_HISTORY:
        st.markdown(
            f'<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:8px;">'
            f'<span style="background:#0A4A84;color:#FFF;padding:2px 10px;border-radius:4px;'
            f'font-size:0.78rem;font-weight:600;white-space:nowrap;">{v["version"]}</span>'
            f'<span style="color:#6B7280;font-size:0.75rem;white-space:nowrap;">{v["date"]}</span>'
            f'<span style="color:#1F2937;font-size:0.85rem;">{v["summary"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════
#  5. 系统信息 / 使用说明（默认折叠）
# ═══════════════════════════════════════════
with st.expander("💡 使用说明与系统信息", expanded=False):
    # 浏览器翻译提醒
    st.warning(
        "⚠️ 请关闭浏览器自动翻译功能后使用本系统，否则可能导致状态名称显示不准确"
        "（例如 Chrome 翻译会把\"编码有效\"误译为\"现行有效\"）。"
        "建议在 Chrome 地址栏点击翻译图标 → 选择\"一律不翻译此网站\"。"
    )

    # 运行模式提示
    run_mode = st.session_state.get("run_mode", "unknown")
    lan_ips = st.session_state.get("lan_ips", [])

    if run_mode == "local":
        st.info("💻 当前为**单机模式**，仅本机可访问")
    elif run_mode == "lan":
        st.warning(
            "当前为局域网共享模式，请仅在可信内网环境使用。"
            "请勿将端口暴露到公网。涉密或敏感文件不得上传普通版本处理。"
        )
        st.error(
            "当前为局域网共享模式，保存在系统中的文件可能被同一局域网内"
            "有访问权限的用户查看或下载。请勿上传涉密、疑似涉密或单位禁止共享的敏感资料。"
        )
        if lan_ips:
            st.info(
                "**本机访问**（仅限当前运行程序的电脑）：\n"
                "http://127.0.0.1:8501\n\n"
                "> ⚠️ 127.0.0.1 **只能在本机打开**，其他电脑不能使用此地址。\n\n"
                "**局域网其他电脑访问**：\n\n" +
                "\n".join(
                    f"  {i}. http://{ip}:8501"
                    for i, ip in enumerate(lan_ips, 1)
                ) + "\n\n"
                "请在**其他电脑的浏览器**中输入上述局域网地址（不要用 127.0.0.1）。"
            )
        else:
            st.info(
                "**本机访问**（仅限当前运行程序的电脑）：\n"
                "http://127.0.0.1:8501\n\n"
                "> ⚠️ 127.0.0.1 **只能在本机打开**，其他电脑不能使用此地址。\n\n"
                "局域网访问地址未能自动检测，请查看命令窗口中的 IP 地址。"
            )
    else:
        st.caption("运行模式未指定（请通过 start_local.bat 或 start_lan.bat 启动）")
        st.info(
            "**本机访问**：http://127.0.0.1:8501\n\n"
            "> ⚠️ 127.0.0.1 只能在当前运行程序的电脑上打开，其他电脑无法使用此地址访问。\n\n"
            "如需局域网共享，请使用 `start_lan.bat` 启动。"
        )

    # 局域网访问故障排查
    with st.expander("💡 局域网访问打不开怎么办？"):
        st.markdown("""
        ### 排查步骤

        1. **确认启动方式**：必须使用 `start_lan.bat` 启动（不是 `start_local.bat`）
        2. **确认地址正确**：在其他电脑上复制局域网地址（如 `http://192.168.x.x:8501`），**不要使用** `127.0.0.1`
        3. **检查网络**：确保两台电脑连接在**同一 Wi-Fi / 同一内网**
        4. **防火墙放行**：在主机电脑上，打开 Windows 防火墙 → 允许应用通过防火墙 → 允许 Python 或添加 8501 端口入站规则
        5. **关闭 VPN/代理**：VPN 或代理软件可能拦截局域网流量，请关闭后重试
        6. **检查主机休眠**：主机电脑休眠后网络会断开，请保持主机唤醒
        7. **检查地址拼写**：确认没有多复制空格、标点等字符
        8. **尝试 ping**：在其他电脑上打开命令提示符，输入 `ping 192.168.x.x`（替换为主机 IP），确认网络通
        """)

    # 操作指引
    st.markdown("### 操作指引")
    st.markdown("""
    1. **上传政策文件建库**：在「文件录入」页面上传政策文件，或通过 Excel 批量导入
    2. **维护文件状态**：确认每个文件的状态（现行有效、已废止等）
    3. **维护新旧关系**：在「文件库维护」页面建立新旧文件的替代/废止关系
    4. **文档审查**：在「依据审查」页面上传待审查文档，系统自动进行比对
    5. **查看结果**：审查完成后，查看结果并导出 Excel 报告
    """)

    # 数据库说明
    st.markdown("### 数据库说明")
    st.markdown("""
    当前使用 **SQLite** 数据库，适合个人或少量人员局域网试用。
    如需多人长期同时使用，建议升级为 **PostgreSQL** 数据库和正式内网部署版本。

    - SQLite 在并发写入时可能出现锁定问题
    - 多人同时操作时，建议部署 PostgreSQL 版本
    - 单机或 2-3 人同时使用尚可接受
    """)

    # 当前版本信息
    st.markdown(
        f'<div style="color:#6B7280;font-size:0.78rem;margin-top:12px;">'
        f'当前版本：{APP_VERSION} | 更新日期：{APP_UPDATE_DATE}</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════
#  6. 最近审查记录
# ═══════════════════════════════════════════
st.markdown("---")
st.markdown(
    '<h3 style="color:#1F2937;font-weight:700;margin-bottom:12px;">最近审查记录</h3>',
    unsafe_allow_html=True,
)
tasks = db.get_all_review_tasks(limit=10)
if tasks:
    for t in tasks:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                st.markdown(f"**{t.get('uploaded_file_name', '未命名')}**")
            with col2:
                st.caption(f"识别 {t.get('extracted_count', 0)} 项依据")
            with col3:
                risk_parts = []
                if t.get("risk_high_count"):
                    risk_parts.append(f"🔴 高/严重 {t['risk_high_count']}")
                if t.get("risk_medium_count"):
                    risk_parts.append(f"🟡 中 {t['risk_medium_count']}")
                if t.get("risk_normal_count"):
                    risk_parts.append(f"🟢 正常 {t['risk_normal_count']}")
                st.caption(" | ".join(risk_parts) if risk_parts else "暂无风险标记")
            st.caption(t.get("created_at", ""))
else:
    st.info("暂无审查记录，请先上传待审查文档进行审查")


# ═══════════════════════════════════════════
#  7. 页脚品牌条
# ═══════════════════════════════════════════
render_footer()
