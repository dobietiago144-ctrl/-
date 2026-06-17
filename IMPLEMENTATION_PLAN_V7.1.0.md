# 政策废止监测 v7.1.0 小闭环实施计划

> 依据：`修改要求24.txt` | 日期：2026-06-16
> 原则：**最小改动，最大收益。不改表结构，不重写页面，不影响已有功能。**

---

## 零、好消息：几乎不需要改数据库

现有 `policy_monitor_candidates` 表已有全部所需字段：

| 需求字段 | 现有列 | 用途 |
|----------|--------|------|
| parsed_items_json | `affected_items TEXT` | 存储解析出的被废止文件JSON列表 |
| abrogation_basis_text | `relation_basis_text TEXT` | 存储废止依据段落 |
| candidate_type | `candidate_type TEXT` | 已存在，候选类型分类 |

**结论：本轮无需任何数据库变更。** 只需更规范地使用现有列。

---

## 一、改动清单（4个文件，预计2-3小时）

### 文件1：`config.py` — 新增配置项（+15行）

```python
# === v7.1.0 新增：监测时间范围（内部页数转换） ===
MONITOR_TIME_RANGES = {
    "近一个月": 30,    # days
    "近半年": 182,
    "近一年": 365,
    "全量补录": 0,     # 0 = 不限时间
}

# 时间范围 → 内部搜索页数兼容转换
TIME_RANGE_TO_PAGES = {
    "近一个月": 1,
    "近半年": 2,
    "近一年": 3,
    "全量补录": 5,
}
```

### 文件2：`pages/7_policy_monitor.py` — 页面改动（约80行增量修改）

#### 改动点1：关键词搜索区 — 替换"搜索页数"为"监测时间范围"

**现有代码（行138-141）：**
```python
with kw_col2:
    search_pages = st.selectbox("搜索页数", [1, 2, 3], index=2, key="search_pages")
```

**改为：**
```python
with kw_col2:
    time_range = st.selectbox(
        "监测时间范围",
        list(TIME_RANGE_TO_PAGES.keys()),
        index=2,  # 默认"近一年"
        key="monitor_time_range"
    )
    # 内部转换
    search_pages = TIME_RANGE_TO_PAGES.get(time_range, 3)
```

#### 改动点2：手动添加链接区 — 改善预览展示

现有流程基本可用，但需增强：
- 解析预览中**明确显示"废止决定/废止公告"类型标签**
- 展示解析出的被废止文件清单时，**用醒目标记已匹配/未匹配**
- 未匹配文件显示 **"建议待补录"** 标签

#### 改动点3：候选列表区 — 简化操作按钮

去掉"标为已废止""标为已失效""标为疑似重复"等可能自动修改正式库的操作，本轮只保留：

```
[📄 查看详情] [✅ 确认候选] [⏭ 忽略] [📝 加入待补录]
```

#### 改动点4：候选详情区 — 增强展示

在现有详情视图中增加：
- **废止依据段落**（从 `relation_basis_text` 读取，高亮显示）
- **被废止文件清单**中明确区分已匹配/未匹配
- **未匹配项附带"建议待补录"标签**

#### 改动点5：页面布局微调

- 合理使用 `st.divider()` 分区
- 候选列表使用更清晰的卡片式布局
- 去掉冗余/无效的按钮

### 文件3：`modules/policy_monitor.py` — 核心逻辑增强（约150行增量）

#### 改动点1：增强 `extract_obsolete_items_from_text`（约40行）

在现有函数开头新增**段落定位逻辑**：

```python
def extract_obsolete_items_from_text(text: str) -> list[dict]:
    """
    增强版（v7.1.0）：先定位废止标记段落，再提取被废止文件名
    """
    if not text:
        return []

    # Step 0: 定位废止/失效标记段落
    basis_markers = [
        "决定废止以下", "废止以下部门规章", "废止以下规范性文件",
        "废止以下", "予以废止", "宣布失效", "决定宣布失效",
        "废止的部门规章", "废止或者失效",
    ]
    
    # 找到包含标记的段落，优先在该区域解析
    focus_text = text  # 默认用全文
    for marker in basis_markers:
        idx = text.find(marker)
        if idx >= 0:
            # 取标记位置前后各2000字符作为重点区域
            start = max(0, idx - 200)
            end = min(len(text), idx + 3000)
            focus_text = text[start:end]
            break

    # Step 1-2: 原有解析逻辑（在 focus_text 中搜索）
    # ...（保持现有模式1和模式2的逻辑）
```

#### 改动点2：新增 `extract_abrogation_basis` 函数（约20行）

```python
def extract_abrogation_basis(text: str) -> str:
    """
    从正文中提取废止依据段落。
    搜索包含关键标记的完整段落（以空行/换行为界）。
    """
    if not text:
        return ""
    
    markers = [
        "决定废止以下", "废止以下部门规章", "予以废止",
        "宣布失效", "废止的规范性文件",
    ]
    
    paragraphs = re.split(r'\n\s*\n', text)
    found = []
    for para in paragraphs:
        para = para.strip()
        if len(para) < 20:
            continue
        for marker in markers:
            if marker in para:
                found.append(para)
                break
        if len(found) >= 3:
            break
    
    return "\n\n".join(found)
```

#### 改动点3：简化 `add_manual_monitor_url` 中的匹配逻辑

确保只做两级匹配（文号精确 + 标题精确），不在手动添加时做模糊匹配：

```python
# 在 add_manual_monitor_url 中
match_affected_items_with_library(obsolete_items)  
# ⚠️ 需要检查此函数内部不做模糊匹配（当前它确实做了模糊匹配）
# → v7.1.0：传参控制匹配深度
```

#### 改动点4：`match_affected_items_with_library` 增加深度控制

```python
def match_affected_items_with_library(
    affected_items: list[dict], 
    deep_match: bool = False  # v7.1.0 默认False，只做精确匹配
) -> list[dict]:
    """
    v7.1.0: deep_match=False 时只做文号精确+标题精确匹配
    v7.2.0+: deep_match=True 时做完整四级匹配
    """
    for item in affected_items:
        old_title = item.get("old_title", "")
        old_no = item.get("old_document_no", "")

        # 1. 文号精确匹配（始终执行）
        if old_no:
            existing = db.get_document_by_no(old_no)
            if existing:
                item["matched"] = True
                item["matched_id"] = existing["id"]
                item["matched_title"] = existing["title"]
                item["match_method"] = "文号精确匹配"
                continue

        # 2. 标题精确匹配（始终执行）
        if old_title:
            existing = db.get_document_by_title(old_title)
            if existing:
                item["matched"] = True
                item["matched_id"] = existing["id"]
                item["matched_title"] = existing["title"]
                item["match_method"] = "标题精确匹配"
                continue

        # 3-4. 模糊匹配仅在 deep_match=True 时执行（v7.2.0+）
        if deep_match and old_title and len(old_title) >= 8:
            # ... 模糊匹配逻辑 ...
            pass

        item["matched"] = False
        item["matched_id"] = None
        item["matched_title"] = ""
        item["match_method"] = ""
    
    return affected_items
```

### 文件4：`tests/test_policy_monitor.py` — 新增测试用例（约30行）

```python
def test_extract_obsolete_items_from_abolish_decision():
    """测试从废止决定正文中解析被废止文件"""
    sample_text = """
    根据《自然资源部立法工作程序规定》的有关规定，自然资源部决定废止以下部门规章：
    一、《建设项目用地预审管理办法》（国土资源部令第7号）
    二、《海洋行政处罚实施办法》（国土资源部令第15号）
    上述规章自本决定发布之日起废止。
    """
    items = extract_obsolete_items_from_text(sample_text)
    assert len(items) >= 2
    assert any("建设项目用地预审管理办法" in item["old_title"] for item in items)
    assert any("海洋行政处罚实施办法" in item["old_title"] for item in items)

def test_extract_abrogation_basis():
    """测试提取废止依据段落"""
    sample_text = """
    自然资源部决定废止以下部门规章：
    一、《xxx办法》
    本决定自发布之日起施行。
    """
    basis = extract_abrogation_basis(sample_text)
    assert "决定废止以下部门规章" in basis
```

---

## 二、具体改动对照

### `pages/7_policy_monitor.py` 改动地图

| 行号范围 | 改动内容 | 类型 |
|----------|----------|------|
| L138-141 | 搜索页数 → 监测时间范围下拉框 | 替换 |
| L200-295 | 手动添加链接区：增强预览展示 | 增强 |
| L359-494 | 候选池列表：简化操作按钮（去掉自动修改库的按钮） | 删减 |
| L501-580 | 候选详情区：增加废止依据段落展示、待补录建议 | 增强 |
| 全局 | 布局微调：增加分区线、改善间距 | 微调 |

### `modules/policy_monitor.py` 改动地图

| 行号范围 | 改动内容 | 类型 |
|----------|----------|------|
| L1142-1263 | `extract_obsolete_items_from_text`: 增加段落定位逻辑 | 增强 |
| 新函数 | `extract_abrogation_basis`: 提取废止依据段落 | 新增 |
| L1266-1318 | `match_affected_items_with_library`: 增加深度控制参数 | 修改 |
| L497-560 | `add_manual_monitor_url`: 使用 extract_abrogation_basis | 增强 |

---

## 三、验收清单

完成后逐项验证：

- [ ] 页面不再出现"搜索页数"，改为"监测时间范围"
- [ ] 输入 `https://f.mnr.gov.cn/202606/t20260605_2931308.html` 能抓取成功
- [ ] 手动链接预览中显示：标题、发布日期、候选类型（废止决定）
- [ ] 能从正文中解析出 `《...》` 形式的被废止文件名
- [ ] 已匹配文件显示匹配信息，未匹配文件显示"建议待补录"
- [ ] 操作仅有：确认候选 / 忽略 / 加入待补录
- [ ] 没有任何操作会自动修改正式政策文件库
- [ ] `1_document_library.py` 正常打开
- [ ] `2_document_import.py` 正常打开
- [ ] `5_review.py` 正常打开

---

## 四、不改的内容（明确排除）

| 排除项 | 原因 |
|--------|------|
| 新增 monitor_sources 表 | v7.2.0 再做 |
| 新增 monitor_candidate_items 表 | v7.2.0 再做 |
| 新增 monitor_seen_urls 表 | v7.2.0 再做 |
| 增量监测（last_success_at） | v7.2.0 再做 |
| 标题相似度/关键词模糊匹配 | 本轮不做，避免误匹配 |
| 自动更新政策库 | 明确禁止 |
| 历史全量补录模式 | 先用时间范围选项覆盖，深度逻辑 v7.2.0 |
| 页面完全重写 | 只做增量修改 |
