"""修改规则库 / 纠错规则库 — 统一管理标题修正、文号修正、状态修正等规则"""

# ═══════════ 规则定义 ═══════════
RULES = [
    # ── 状态修正规则 ──
    {
        "rule_id": "STATUS_001",
        "rule_name": "编码有效不是文件状态",
        "rule_type": "状态修正",
        "match": {"field": "status", "equals": "编码有效"},
        "action": {
            "normalize_to": "待核实",
            "warning": "编码有效属于导入质量/编码校验结果，不应作为文件效力状态。已自动修正为'待核实'，请人工确认后手动设置为正确的效力状态。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "状态修正：编码有效不是文件状态，已修正为待核实",
    },
    {
        "rule_id": "STATUS_002",
        "rule_name": "非标准状态统一清理",
        "rule_type": "状态修正",
        "match": {"field": "status", "not_in_standard": True},
        "action": {
            "normalize_to": "待核实",
            "warning": "文件状态不在标准枚举中，已自动修正为'待核实'。",
        },
        "severity": "低",
        "auto_apply": True,
        "trigger_message": "状态修正：非标准状态已统一",
    },
    # ── 标题校验规则 ──
    {
        "rule_id": "TITLE_001",
        "rule_name": "空书名号标题无效",
        "rule_type": "标题校验",
        "match": {"field": "title", "equals": "《》"},
        "action": {
            "mark_quality": "标题异常",
            "block_import": True,
            "suggestion": "标题识别失败（空书名号），请手工补录有效文件名称。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "标题异常：空书名号标题无效",
    },
    {
        "rule_id": "TITLE_002",
        "rule_name": "空标题无效",
        "rule_type": "标题校验",
        "match": {"field": "title", "equals": ""},
        "action": {
            "mark_quality": "标题异常",
            "block_import": True,
            "suggestion": "标题为空，请手工填写有效文件名称。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "标题异常：空标题",
    },
    {
        "rule_id": "TITLE_003",
        "rule_name": "未识别标题",
        "rule_type": "标题校验",
        "match": {"field": "title", "equals": "未识别"},
        "action": {
            "mark_quality": "标题异常",
            "block_import": True,
            "suggestion": "标题未能识别，请手工补录。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "标题异常：未识别标题",
    },
    {
        "rule_id": "TITLE_004",
        "rule_name": "PDF解析提示误识别为标题",
        "rule_type": "标题校验",
        "match": {"field": "title", "contains_any": ["PDF共", "仅展示前", "仅显示前", "完整内容将在入库后存储", "完整内容将录入库后存储"]},
        "action": {
            "mark_quality": "标题异常",
            "block_import": True,
            "suggestion": "标题包含PDF解析提示，不能作为政策文件标题，请手工补录有效文件名称。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "标题异常：PDF解析提示误识别",
    },
    {
        "rule_id": "TITLE_005",
        "rule_name": "纯标点符号标题",
        "rule_type": "标题校验",
        "match": {"field": "title", "only_punctuation": True},
        "action": {
            "mark_quality": "标题异常",
            "block_import": True,
            "suggestion": "标题只含标点符号，请手工填写有效文件名称。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "标题异常：纯标点符号",
    },
    {
        "rule_id": "TITLE_006",
        "rule_name": "标题过短",
        "rule_type": "标题校验",
        "match": {"field": "title", "max_length": 3},
        "action": {
            "mark_quality": "标题异常",
            "block_import": True,
            "suggestion": "标题过短，请检查标题是否完整。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "标题异常：标题过短",
    },
    {
        "rule_id": "TITLE_007",
        "rule_name": "无效词作标题",
        "rule_type": "标题校验",
        "match": {"field": "title", "in_list": ["目录", "正文", "附件", "打印", "下载", "封面", "扉页", "摘要"]},
        "action": {
            "mark_quality": "标题异常",
            "block_import": True,
            "suggestion": "标题为无效词，非政策文件名称，请手工补录。",
        },
        "severity": "高",
        "auto_apply": True,
        "trigger_message": "标题异常：无效词作标题",
    },
    # ── 文号格式规则 ──
    {
        "rule_id": "DOCNO_001",
        "rule_name": "文号括号格式不规范",
        "rule_type": "文号修正",
        "match": {"field": "document_no", "contains_any": ["(202", ")202", "[202", "]202"]},
        "action": {
            "warning": "文号括号格式不规范（建议使用〔〕），但不影响文件有效性判断。",
        },
        "severity": "低",
        "auto_apply": False,
        "trigger_message": "文号格式：括号格式不规范",
    },
    # ── 废止/替代关键词规则 ──
    {
        "rule_id": "OBSOLETE_001",
        "rule_name": "废止关键词识别",
        "rule_type": "废止/替代关键词",
        "match": {"field": "text", "contains_any": ["废止", "予以废止", "同时废止", "宣布废止", "废止的部门规章", "已废止或者失效"]},
        "action": {
            "candidate_type": "废止公告",
            "warning": "正文包含废止关键词，建议加入废止监测候选池。",
        },
        "severity": "高",
        "auto_apply": False,
        "trigger_message": "废止关键词：检测到废止相关表述",
    },
    {
        "rule_id": "OBSOLETE_002",
        "rule_name": "失效关键词识别",
        "rule_type": "废止/替代关键词",
        "match": {"field": "text", "contains_any": ["失效", "已失效", "有效期届满", "不再执行", "停止执行"]},
        "action": {
            "candidate_type": "失效目录",
            "warning": "正文包含失效关键词，建议加入政策废止监测候选池。",
        },
        "severity": "高",
        "auto_apply": False,
        "trigger_message": "失效关键词：检测到失效相关表述",
    },
    # ── 审查建议模板规则 ──
    {
        "rule_id": "REVIEW_001",
        "rule_name": "已废止文件引用提醒",
        "rule_type": "审查意见模板",
        "match": {"field": "document_status", "equals": "已废止"},
        "action": {
            "template": "引用的文件「{title}」已被正式废止，不应作为现行有效依据继续引用。建议查证是否有替代文件或更新版本。",
        },
        "severity": "高",
        "auto_apply": False,
        "trigger_message": "审查建议：引用的文件已废止",
    },
    {
        "rule_id": "REVIEW_002",
        "rule_name": "已失效文件引用提醒",
        "rule_type": "审查意见模板",
        "match": {"field": "document_status", "equals": "已失效"},
        "action": {
            "template": "引用的文件「{title}」已失效，建议核实失效原因并查找现行有效替代文件。",
        },
        "severity": "高",
        "auto_apply": False,
        "trigger_message": "审查建议：引用的文件已失效",
    },
]


def get_rules(rule_type: str = "") -> list[dict]:
    """获取规则列表，可按类型筛选"""
    if not rule_type:
        return RULES
    return [r for r in RULES if r.get("rule_type") == rule_type]


def match_rule(rule: dict, data: dict) -> bool:
    """判断一条规则是否匹配给定的数据。

    Args:
        rule: 规则定义
        data: 待匹配数据，如 {"title": "...", "status": "...", "document_no": "..."}

    Returns:
        True 如果规则触发
    """
    match_config = rule.get("match", {})
    field = match_config.get("field", "")
    value = data.get(field, "")

    if not value:
        return False

    if "equals" in match_config and value == match_config["equals"]:
        return True

    if "contains" in match_config and match_config["contains"] in value:
        return True

    if "contains_any" in match_config:
        if any(kw in value for kw in match_config["contains_any"]):
            return True

    if "in_list" in match_config and value in match_config["in_list"]:
        return True

    if "max_length" in match_config and len(value) <= match_config["max_length"]:
        return True

    if "min_length" in match_config and len(value) >= match_config["min_length"]:
        return True

    if "only_punctuation" in match_config:
        import re
        stripped = re.sub(r"[《》〈〉\[\]【】\s\.,;:!?，。；：！？、""''（）()…—\\-／/]", "", value)
        if len(stripped) < 2:
            return True

    if "not_in_standard" in match_config:
        from modules.status_utils import STANDARD_STATUSES
        if value not in STANDARD_STATUSES:
            return True

    return False


def apply_rules(data: dict, rule_type: str = "") -> list[dict]:
    """对数据应用规则，返回所有触发的规则及其动作。

    Args:
        data: 要检查的数据字典
        rule_type: 可选，只应用指定类型的规则

    Returns:
        [{"rule": dict, "action": dict, "triggered": True}, ...]
    """
    rules = get_rules(rule_type)
    results = []
    for rule in rules:
        if match_rule(rule, data):
            results.append({
                "rule": rule,
                "action": rule.get("action", {}),
                "triggered": True,
            })
    return results


def detect_invalid_title(title: str) -> bool:
    """检测标题是否无效。

    使用规则库中的标题校验规则来判断。

    Returns:
        True 如果标题无效
    """
    if not title:
        return True
    title = title.strip()
    results = apply_rules({"title": title}, rule_type="标题校验")
    # 只要触发了任何标题校验规则且 rule 标记了 block_import，就是无效标题
    for r in results:
        if r["action"].get("block_import"):
            return True
    return False


def get_display_title(title: str, max_len: int = 50) -> str:
    """获取用于列表显示的标题。

    - 无效标题 → "【未识别标题，请补录】"
    - 过长标题 → 截断 + "..."
    - 正常标题 → 返回原值
    """
    if not title or not title.strip():
        return "【未识别标题，请补录】"

    title = title.strip()

    if detect_invalid_title(title):
        return "【未识别标题，请补录】"

    if len(title) > max_len:
        return title[:max_len] + "..."

    return title


def truncate_text(text: str, max_len: int = 50) -> str:
    """截断文本，超长加省略号"""
    if not text:
        return ""
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
