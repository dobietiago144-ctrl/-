# 政策废止监测模块 — 详细实施计划

> 依据：`修改意见23.txt` | 日期：2026-06-16

---

## 一、项目现状总结

| 维度 | 现状 | 目标 |
|------|------|------|
| 监测模式 | 仅手动触发检查 | 历史全量补录 + 日常增量监测 |
| 时间参数 | "搜索页数"（1/2/3页） | "监测时间范围"（近一月/半年/年/自定义/全量） |
| 关键词 | 约15个关键词，所有来源共用 | 可配置的关键词组，按来源定制 |
| 正文解析 | 仅保存全文，不解析被废止清单 | 自动解析废止决定正文中的被废止文件 |
| 匹配 | 简单 title+doc_no 匹配 | 四级匹配（文号→标题→相似度→关键词） |
| 候选流程 | 确认入库/忽略/删除 | 6种状态完整确认流程 |
| 手动添加 | 抓取预览，简单确认 | 完整8步流程 |
| 数据库 | 2张监测表（candidates + ignored_urls） | 4张表（sources/candidates/candidate_items/seen_urls） |
| 页面布局 | 扁平结构 | 5个区域模块化布局 |

**技术栈**: Python 3.12 + Streamlit + SQLite3 + BeautifulSoup4

---

## 二、分阶段实施计划

### 🔴 第一阶段：数据库层（预计 2-3 小时）

#### 1.1 新增 `monitor_sources` 表

```sql
CREATE TABLE monitor_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- 来源名称
    domain TEXT NOT NULL,                  -- 域名
    search_url TEXT DEFAULT '',            -- 搜索URL模板
    enabled INTEGER DEFAULT 1,             -- 是否启用
    last_checked_at TEXT DEFAULT '',       -- 上次检查时间
    last_success_at TEXT DEFAULT '',       -- 上次成功监测时间
    last_error TEXT DEFAULT '',            -- 最后错误信息
    keywords TEXT DEFAULT '',              -- 该来源专属关键词（逗号分隔，空则用全局）
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

#### 1.2 新增 `monitor_candidate_items` 表

用于保存从废止决定中解析出来的被废止文件：

```sql
CREATE TABLE monitor_candidate_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,         -- 关联 monitor_candidates.id
    old_title TEXT DEFAULT '',             -- 被废止文件名称
    old_document_no TEXT DEFAULT '',       -- 被废止文件文号
    old_issuer TEXT DEFAULT '',            -- 原发布机关
    old_publish_date TEXT DEFAULT '',      -- 原发布日期
    relation_type TEXT DEFAULT '废止',     -- 废止/失效/修改/替代/疑似废止
    evidence_text TEXT DEFAULT '',         -- 正文依据段落
    matched_document_id INTEGER,           -- 匹配到的本地文件ID
    match_score REAL DEFAULT 0,            -- 匹配置信度 0-1
    match_method TEXT DEFAULT '',          -- 匹配方式
    match_status TEXT DEFAULT '未匹配',    -- 已匹配/未匹配/待补录
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

#### 1.3 新增 `monitor_seen_urls` 表

```sql
CREATE TABLE monitor_seen_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,            -- 关联 monitor_sources.id
    url TEXT NOT NULL,
    content_hash TEXT DEFAULT '',          -- 内容 hash
    first_seen_at TEXT DEFAULT (datetime('now','localtime')),
    last_seen_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE UNIQUE INDEX idx_seen_source_url ON monitor_seen_urls(source_id, url);
```

#### 1.4 扩展现有 `policy_monitor_candidates` 表

新增字段：
- `content_hash TEXT DEFAULT ''` — 内容哈希，用于增量去重
- `candidate_status TEXT DEFAULT '待确认'` — 细分状态（替代原 `status` 字段的部分值）
- `abrogation_basis_text TEXT DEFAULT ''` — 废止/失效依据段落文本

**修改文件**:
- `database/models.py` — 新增 3 张表的 CREATE 语句
- `database/db.py` — 新增对应的 CRUD 函数

---

### 🟠 第二阶段：配置层（预计 1-2 小时）

#### 2.1 扩展 `config.py`

**新增/修改配置项**:

```python
# 监测模式
MONITOR_MODE_OPTIONS = ["日常增量监测", "历史全量补录"]

# 监测时间范围（替代搜索页数）
MONITOR_TIME_RANGES = {
    "近一个月": 30,
    "近半年": 182,
    "近一年": 365,
    "自定义": -1,
    "全量补录": 0,
}

# 扩展关键词组（按来源配置）
MONITOR_KEYWORDS_DEFAULT = [
    "废止", "失效", "宣布失效", "予以废止",
    "清理结果", "规范性文件清理", "现行有效目录",
    "部门规章", "决定", "公告", "修改", "修订",
    "停止执行", "自然资源部令", "规范性文件目录",
]

MONITOR_KEYWORDS_BY_SOURCE = {
    "自然资源部-政策": [
        "废止", "失效", "宣布失效", "予以废止",
        "废止的部门规章", "决定废止", "规范性文件清理",
        "部门规章的决定", "自然资源部令", "现行有效目录",
        "清理结果", "修改", "修订", "停止执行",
        "公告", "决定", "规范性文件目录",
    ],
    "广东省自然资源厅-政策法规": [
        "废止", "失效", "宣布失效", "予以废止",
        "清理结果", "规范性文件清理", "现行有效目录",
        "修改", "修订", "停止执行", "公告", "决定",
    ],
}

# 候选类型扩展
MONITOR_CANDIDATE_TYPES = [
    "废止决定", "失效公告", "修订文件",
    "现行有效目录", "普通政策文件", "其他",
]

# 候选状态（细分版）
MONITOR_CANDIDATE_STATUSES = [
    "待确认", "已确认有效", "已忽略",
    "已转入待补录", "已更新本地库", "解析失败",
]
```

**修改文件**:
- `config.py` — 新增配置项，保留旧配置作为兼容

---

### 🟡 第三阶段：后端逻辑层 — 核心功能（预计 4-6 小时）

#### 3.1 增量监测引擎

**文件**: `modules/policy_monitor.py`（新增函数）

```python
def get_last_success_at(source_id: int) -> str:
    """读取来源上次成功监测时间"""

def update_source_check_time(source_id: int, success: bool, error: str = ""):
    """更新来源监测时间戳"""

def is_url_seen(source_id: int, url: str, content_hash: str = "") -> dict:
    """检查URL是否已见过，返回 {seen, changed}"""

def mark_url_seen(source_id: int, url: str, content_hash: str):
    """记录已见过的URL"""

def incremental_monitor(source_id: int, time_range_days: int) -> dict:
    """增量监测：仅抓取 last_success_at 之后的新内容"""
```

#### 3.2 废止决定正文解析器增强

**文件**: `modules/policy_monitor.py`（增强现有 `extract_obsolete_items_from_text`）

当前已支持模式1（编号+《标题》+可选信息）和模式2（直接《标题》匹配），需增强：

1. **新增废止依据段落定位**：先定位包含"决定废止以下"、"宣布失效以下"等标记的段落，在该区域集中解析
2. **支持更多编号格式**：`（一）（二）`、`1. 2.`、`第X条` 等
3. **识别废止关系类型**：
   - 明确"废止" → `relation_type = "废止"`
   - "宣布失效" → `relation_type = "失效"`
   - "修改"、"修订" → `relation_type = "修改"`
   - 不确定 → `relation_type = "疑似废止"`

```python
def extract_obsolete_items_enhanced(text: str, url: str = "") -> dict:
    """增强版解析器，返回:
    {
        "basis_title": "依据文件标题",
        "basis_document_no": "依据文件文号",
        "basis_publish_date": "依据文件发布日期",
        "basis_paragraph": "依据正文段落",
        "items": [{old_title, old_document_no, old_issuer, old_publish_date, relation_type, evidence_text}]
    }
    """
```

3. **文本段落定位**：先搜索以下标记段落
   - "决定废止以下"
   - "予以废止"
   - "宣布失效"
   - "废止以下部门规章"
   - "废止的规范性文件"
   - "清理结果如下"
   - "现行有效目录"

#### 3.3 本地库匹配增强

**文件**: `modules/policy_monitor.py`（增强 `match_affected_items_with_library`）

实现四级匹配：

```python
def match_items_with_library_enhanced(items: list[dict]) -> list[dict]:
    """增强匹配，按优先级:
    1. 文号完全一致 → match_score=1.0, match_method="文号精确匹配"
    2. 标题完全一致 → match_score=0.95, match_method="标题精确匹配"
    3. 标题相似度匹配 → match_score=0.7-0.94, match_method="标题相似度匹配"
    4. 标题关键词匹配 → match_score=0.5-0.69, match_method="关键词匹配"
    5. 无法匹配 → match_status="待补录"
    """
```

#### 3.4 候选管理 CRUD 扩展

**文件**: `modules/policy_monitor.py`（新增函数）

```python
# monitor_sources CRUD
def get_monitor_sources(enabled_only: bool = True) -> list[dict]
def get_monitor_source(source_id: int) -> dict
def save_monitor_source(data: dict) -> int
def update_monitor_source(source_id: int, data: dict)

# monitor_candidate_items CRUD
def save_candidate_items(candidate_id: int, items: list[dict])
def get_candidate_items(candidate_id: int) -> list[dict]
def update_candidate_item(item_id: int, data: dict)

# monitor_seen_urls CRUD
def is_url_seen(source_id: int, url: str, content_hash: str = "") -> dict
def mark_url_seen(source_id: int, url: str, content_hash: str)
def get_seen_urls(source_id: int) -> list[dict]
```

**修改文件**:
- `modules/policy_monitor.py` — 新增约 400-600 行代码
- `database/db.py` — 新增约 150-200 行 CRUD 代码

---

### 🟢 第四阶段：页面重构（预计 4-6 小时）

**文件**: `pages/7_policy_monitor.py`（几乎重写）

#### 4.1 模块1：顶部说明区

```python
st.title("📋 政策废止监测")
st.markdown(
    "监测官方政策网站，发现**废止、失效、修订和替代**文件，"
    "并经**人工确认**后更新文件库。"
)
# 安全提醒
st.info("⚠️ 安全边界：仅官方域名 | 不自动修改正式库 | 所有关系需人工确认")
```

#### 4.2 模块2：监测配置区

```python
with st.expander("⚙️ 监测配置", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        monitor_mode = st.radio(
            "监测模式",
            ["日常增量监测", "历史全量补录"],
            horizontal=True
        )
    with col2:
        monitor_source = st.selectbox(
            "监测来源",
            ["自然资源部", "广东省自然资源厅", "自定义来源"]
        )

    col3, col4 = st.columns(2)
    with col3:
        time_range = st.selectbox(
            "监测时间范围",
            ["近一个月", "近半年", "近一年", "自定义", "全量补录"]
        )
        if time_range == "自定义":
            custom_start = st.date_input("开始日期")
            custom_end = st.date_input("结束日期")
    with col4:
        keyword_preset = st.selectbox(
            "关键词组",
            ["默认关键词", "扩展关键词", "自定义关键词"]
        )
        if keyword_preset == "自定义关键词":
            custom_keywords = st.text_area("每行一个关键词")

    st.checkbox("仅限官方域名", value=True, disabled=True)
    st.checkbox("自动加入候选池", value=True)
    st.checkbox("自动更新正式库", value=False, disabled=True,
                help="安全策略：禁止自动修改正式库")
```

#### 4.3 模块3：手动检查区

```python
st.subheader("🔍 手动检查")

col1, col2 = st.columns(2)
with col1:
    if st.button("🔍 立即检查自然资源部", type="primary"):
        # 执行监测逻辑（支持全量/增量模式）
        ...
    # 显示上次检查结果摘要
    mnr_result = st.session_state.get("last_mnr_check")
    if mnr_result:
        st.metric("新增候选", mnr_result.get("new_count", 0))
        st.metric("已在库", mnr_result.get("in_library_count", 0))
        ...

with col2:
    if st.button("🔍 立即检查广东省自然资源厅", type="primary"):
        ...
```

#### 4.4 模块4：候选列表区

```python
st.subheader("📥 废止监测候选池")

# 筛选栏
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    status_filter = st.selectbox("状态筛选", ["全部"] + MONITOR_CANDIDATE_STATUSES)
with col_f2:
    type_filter = st.selectbox("类型筛选", ["全部"] + MONITOR_CANDIDATE_TYPES)
with col_f3:
    source_filter = st.selectbox("来源筛选", ["全部", "自然资源部", "广东省自然资源厅"])

# 候选列表 — 每行显示
for c in candidates:
    with st.container():
        col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
        with col1:
            st.markdown(f"**{c['title'][:60]}**")
            st.caption(f"来源: {c['source_name']} | 日期: {c['publish_date']}")
        with col2:
            st.markdown(f":blue[{c['candidate_type']}]")
        with col3:
            st.markdown(f"解析: {c.get('items_count', 0)}个文件")
        with col4:
            st.markdown(f"匹配: {c.get('matched_count', 0)}个")
        with col5:
            st.markdown(f":orange[{c['candidate_status']}]")

        # 操作按钮行
        op_col1, op_col2, op_col3, op_col4 = st.columns(4)
        with op_col1:
            st.button("📄 查看详情", key=f"detail_{c['id']}")
        with op_col2:
            st.button("✅ 确认", key=f"confirm_{c['id']}")
        with op_col3:
            st.button("⏭ 忽略", key=f"ignore_{c['id']}")
        with op_col4:
            st.button("📝 转入待补录", key=f"pending_{c['id']}")
```

#### 4.5 模块5：候选详情区

```python
# 当用户点击"查看详情"时展开
if view_id:
    cand = get_monitor_candidate(view_id)
    items = get_candidate_items(view_id)

    st.subheader(f"候选详情: {cand['title']}")

    # Tab 切换
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 基本信息", "📝 废止依据", "📄 全文预览", "🔗 匹配结果"
    ])

    with tab1:
        # 网页基本信息
        st.markdown(f"**标题**: {cand['title']}")
        st.markdown(f"**URL**: {cand['source_url']}")
        st.markdown(f"**来源**: {cand['source_name']}")
        st.markdown(f"**文号**: {cand.get('document_no', '')}")
        st.markdown(f"**发布日期**: {cand.get('publish_date', '')}")
        st.markdown(f"**候选类型**: {cand['candidate_type']}")
        st.markdown(f"**命中关键词**: {cand.get('detected_keywords', '')}")

    with tab2:
        # 废止/失效依据段落
        st.markdown(cand.get('abrogation_basis_text', ''))

    with tab3:
        # 全文预览
        st.text_area("全文", cand.get('full_text', '')[:10000], height=300, disabled=True)

    with tab4:
        # 本地库匹配结果
        for item in items:
            matched = item.get('matched_document_id')
            if matched:
                st.success(
                    f"📎 **{item['old_title']}** → 已匹配: "
                    f"《{item.get('matched_title', '')}》"
                    f"（置信度: {item.get('match_score', 0):.0%}, "
                    f"方式: {item.get('match_method', '')}）"
                )
            else:
                st.warning(
                    f"❓ **{item['old_title']}** → 未匹配，建议转入待补录"
                )

    # 底部操作按钮
    col_act1, col_act2, col_act3, col_act4 = st.columns(4)
    with col_act1:
        if st.button("✅ 确认候选", type="primary"):
            # 更新候选状态为"已确认有效"
            ...
    with col_act2:
        if st.button("⏭ 忽略"):
            ...
    with col_act3:
        if st.button("📝 转入待补录"):
            ...
    with col_act4:
        if st.button("🔄 更新政策库", type="primary", disabled=True):
            # 仅在候选已确认后可用
            # 执行：更新文件状态 + 建立新旧关系
            ...
```

#### 4.6 手动添加监测链接（重构）

```python
st.subheader("🔗 手动添加监测链接")

manual_url = st.text_input("输入政策链接", placeholder="https://f.mnr.gov.cn/...")

if st.button("🔍 抓取并预览"):
    # Step 1: 抓取网页
    # Step 2: 显示标题、来源、发布日期、正文摘要
    # Step 3: 自动识别候选类型
    # Step 4: 自动解析被废止文件清单
    # Step 5: 自动匹配本地政策库
    # Step 6: 显示预览结果
    ...

if manual_preview:
    st.subheader("解析预览")

    # 显示识别结果
    st.markdown(f"**候选类型**: {preview['candidate_type']}")
    st.markdown(f"**命中关键词**: {preview['detected_keywords']}")

    # 被废止文件清单
    st.markdown(f"**解析出被废止文件**: {len(preview['items'])} 个")
    for item in preview['items']:
        match_badge = "📎 已匹配" if item.get('matched') else "❓ 未匹配"
        st.markdown(f"- 《{item['old_title']}》{match_badge}")

    # 确认按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ 确认加入候选池"):
            ...
    with col2:
        if st.button("🔄 确认并更新政策库"):
            # 直接更新正式库（仍需人工点这一步）
            ...
    if st.button("❌ 取消"):
        ...
```

**注意**: 所有"更新政策库"操作必须仅在被人工确认后才执行，且需二次确认弹窗。

---

### 🔵 第五阶段：集成测试与验证（预计 2-3 小时）

#### 5.1 功能测试清单

- [ ] 页面不再显示"搜索页数"，改为"监测时间范围"
- [ ] 支持"历史全量补录"和"日常增量监测"两种模式切换
- [ ] 能抓取自然资源部官网的废止决定类文件
- [ ] 能从废止决定正文中解析出被废止文件清单
- [ ] 未匹配文件进入"待补录文件清单"
- [ ] 已匹配文件显示匹配置信度和匹配方式
- [ ] 人工确认前不能自动修改正式库
- [ ] 人工确认后可更新文件状态，建立废止/替代关系
- [ ] 手动添加URL后可预览、解析、匹配、确认
- [ ] 原有政策文件录入、查询、文档审查功能不受影响

#### 5.2 测试数据

使用配置中的测试链接：
- `https://f.mnr.gov.cn/202606/t20260605_2931308.html`

以及手动测试更多真实废止决定页面。

#### 5.3 回归测试

- 运行现有测试：`tests/test_policy_monitor.py`
- 确认 `1_document_library.py`, `2_document_import.py`, `5_review.py` 等页面正常

**修改文件**:
- `tests/test_policy_monitor.py` — 新增/扩展测试用例

---

### ⚪ 第六阶段：文档与清理（预计 1 小时）

- [ ] 更新 `CLAUDE.md` 记录此次改动
- [ ] 在 `config.py` 中标记 `# v23 新增` 注释
- [ ] 清理废弃代码和注释

---

## 三、文件变更清单

| 文件 | 变更类型 | 预计行数变化 |
|------|----------|-------------|
| `database/models.py` | 新增表定义 | +80 行 |
| `database/db.py` | 新增 CRUD 函数 | +200 行 |
| `config.py` | 新增/修改配置项 | +80 行 |
| `modules/policy_monitor.py` | 核心逻辑重构 | +500 行 |
| `pages/7_policy_monitor.py` | 页面重写 | 约 600 行（重写） |
| `tests/test_policy_monitor.py` | 新增测试 | +100 行 |

---

## 四、风险与注意事项

1. **向后兼容**: 数据库表变更需做迁移，不能破坏现有数据
2. **性能**: 全量补录可能抓取大量页面，需做限流和超时保护
3. **编码问题**: 政府网站编码混乱（GB2312/GBK/UTF-8），已有 `decode_response_content` 函数需持续维护
4. **网站结构变化**: 自然资源部网站可能改版，解析器需定期维护
5. **安全**: 严格遵守安全边界 — 域名白名单、不自动修改正式库、人工确认机制

---

## 五、推荐实施顺序

```
第一阶段（数据库）
    ↓
第二阶段（配置）
    ↓
第三阶段（后端逻辑）
    ↓
第四阶段（页面重构）
    ↓
第五阶段（测试验证）
    ↓
第六阶段（文档清理）
```

建议按顺序逐阶段实施，每阶段完成后进行验证再进入下一阶段。
