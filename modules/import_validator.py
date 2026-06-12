"""导入质量校验：标题识别检查、重复检查、导入候选判断"""

import re

# 政策文件常见关键词
POLICY_KEYWORDS = [
    "法", "条例", "办法", "规定", "通知", "意见", "决定", "公告",
    "方案", "指南", "规程", "规范", "标准", "细则",
    "管理办法", "实施办法", "工作方案", "技术规程",
]

# 无效标题词（不应作为政策文件标题）
INVALID_TITLE_WORDS = [
    "目录", "正文", "附件", "打印", "下载",
    "封面", "扉页", "摘要", "索引", "参考文献",
    "版权", "免责声明", "前言", "序言", "后记",
]

# PDF 解析提示关键词
PARSE_HINT_KEYWORDS = [
    "PDF共", "仅展示前", "仅显示前",
    "完整内容将在入库后存储", "完整内容将录入库后存储",
]

# 附件/材料清单排除词（不得作为政策文件主标题）
ATTACHMENT_TITLE_EXCLUDE_WORDS = [
    "附件", "附表", "附录", "目录",
    "材料名称", "提交条件", "提供条件", "示范文本",
    "申请材料", "申报材料", "申请书",
    "授权委托", "法人证明", "身份证明",
    "勘测定界", "规划审核意见", "规划选址意见",
    "用地预审意见", "用地预审",
    "清单", "表格", "填报说明",
    "建设项目用地申请表", "登记表", "审批表",
    "意见书", "证明书",
]

# 附件/材料清单条目编号前缀
ATTACHMENT_ITEM_PREFIXES = [
    "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩",
    "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、",
    "（一）", "（二）", "（三）", "（四）", "（五）",
    "(一)", "(二)", "(三)", "(四)", "(五)",
    "附件1", "附件2", "附件3", "附件4", "附件5",
    "附表1", "附表2", "附表3",
]


def _clean_title(title: str) -> str:
    """清洗标题：去首尾空白、去多余空格"""
    if not title:
        return ""
    title = title.strip()
    title = re.sub(r"\s+", " ", title)
    return title


def is_attachment_title(title: str) -> tuple[bool, str]:
    """判断标题是否为附件标题/材料清单条目/表格字段名。

    返回 (is_attachment, reason)
    """
    if not title:
        return False, ""

    title = title.strip()

    # 1. 以附件/附表/附录开头
    if re.match(r"^(附件|附表|附录|附件\d+|附表\d+|附录\d+)", title):
        return True, "以附件/附表/附录开头"

    # 2. 以材料相关词开头
    for word in ["材料名称", "提交条件", "提供条件", "示范文本",
                  "申请材料", "申报材料", "申请书"]:
        if title.startswith(word):
            return True, f"以'{word}'开头"

    # 3. 以编号前缀开头
    for prefix in ATTACHMENT_ITEM_PREFIXES:
        if title.startswith(prefix):
            return True, f"以编号'{prefix}'开头"

    # 4. 仅包含书名号短条目
    m = re.match(r"^[《〈](.+?)[》〉]$", title)
    if m:
        inner = m.group(1).strip()
        for word in ATTACHMENT_TITLE_EXCLUDE_WORDS:
            if word in inner:
                return True, f"书名号内容包含'{word}'"
        # 短条目且无政策关键词
        if len(inner) <= 40 and not any(kw in inner for kw in POLICY_KEYWORDS):
            return True, "短书名号条目，不包含政策关键词"

    # 5. 表单类结尾
    if re.search(r"(申请书|登记表|审批表|申请表|报告表|备案表|意见书|证明书)$", title):
        return True, "疑似表单/证明类文件"

    # 6. 包含附件排除词（全文匹配）
    for word in ["勘测定界", "规划审核意见", "规划选址意见",
                  "用地预审意见", "法人身份证明", "授权委托书"]:
        if word in title:
            return True, f"包含附件/材料特征词'{word}'"

    return False, ""


def validate_import_candidate(
    title: str = "",
    document_no: str = "",
    text: str = "",
    file_name: str = "",
) -> dict:
    """判断一个文件是否适合直接入库。

    返回:
        {
            "valid": True/False,
            "level": "可入库/待人工确认/不建议入库",
            "reason": "原因",
            "suggestion": "处理建议",
        }
    """
    title = _clean_title(title)
    document_no = (document_no or "").strip()

    # ── 规则1: title 为空 ──
    if not title:
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": "标题为空",
            "suggestion": "请手工填写有效文件名称后再入库",
        }

    # ── 规则2: title 只有《》、[]、空格、标点 ──
    stripped = re.sub(r"[《》〈〉\[\]【】\s\.,;:!?，。；：！？、""''（）()…—\\-/]", "", title)
    if len(stripped) < 2:
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": "标题只含标点符号",
            "suggestion": "请手工填写有效文件名称后再入库",
        }

    # ── 规则3: title 长度小于 4 ──
    if len(title) < 4:
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": f"标题过短（{len(title)}字）",
            "suggestion": "请检查标题是否完整，或手工填写",
        }

    # ── 规则4: title 是"未识别"或系统占位符 ──
    if title in ("未识别", "未识别标题", "无标题", "【未识别标题，请补录】"):
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": f"标题为系统占位符（'{title}'），未能自动识别",
            "suggestion": "请手工填写有效文件名称",
        }

    # ── 规则5: 包含解析提示关键词 ──
    for kw in PARSE_HINT_KEYWORDS:
        if kw in title:
            return {
                "valid": False,
                "level": "不建议入库",
                "reason": f"标题包含解析提示（含'{kw}'）",
                "suggestion": "解析提示不能作为标题，请手工填写",
            }

    # ── 规则9: title 是无效词 ──
    if title in INVALID_TITLE_WORDS:
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": f"标题为无效词（'{title}'）",
            "suggestion": "请手工填写有效文件名称",
        }

    # ── 规则10: title 过长 ──
    if len(title) > 120:
        return {
            "valid": False,
            "level": "待人工确认",
            "reason": f"标题过长（{len(title)}字，超过120字限制）",
            "suggestion": "请确认是否正文段落被误识别为标题，必要时手工修改",
        }

    # ── 规则11: 明显是正文段落 ──
    # 检查是否包含多个句子（句号/分号分隔）
    sentence_count = len(re.findall(r"[。；;]", title))
    if sentence_count >= 3:
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": "标题包含多个句子，可能是正文段落",
            "suggestion": "请手工提取有效文件名称",
        }
    # 包含大量逗号（5个以上）可能是段落
    comma_count = len(re.findall(r"[，,]", title))
    if comma_count >= 5 and len(title) > 50:
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": "标题含大量逗号，可能是正文段落",
            "suggestion": "请手工提取有效文件名称",
        }

    # ── 规则12: 文件名扩展名检查（优先于关键词检查）──
    if re.search(r"\.(pdf|docx?|xlsx?|txt|doc)$", title, re.IGNORECASE):
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": "标题为文件名（含扩展名），非政策文件标题",
            "suggestion": "请手工填写有效文件名称（去除扩展名和日期编号）",
        }

    # ── 规则13: 没有政策文件常见关键词且没有文号 ──
    has_policy_kw = any(kw in title for kw in POLICY_KEYWORDS)
    has_doc_no = bool(document_no)

    if not has_policy_kw and not has_doc_no:
        return {
            "valid": False,
            "level": "待人工确认",
            "reason": "标题中未找到政策文件常见关键词且无文号",
            "suggestion": "请确认标题是否正确，或手工填写有效文件名称",
        }

    # ── 规则14: 附件标题检查 ──
    is_att, att_reason = is_attachment_title(title)
    if is_att:
        return {
            "valid": False,
            "level": "不建议入库",
            "reason": f"疑似附件/材料条目标题: {att_reason}",
            "suggestion": "该标题可能不是政策文件主标题，请手工确认并填写正确的政策文件名称",
        }

    # ── 规则15: 正文内容检查（仅当明确提供了正文时触发）──
    if text and len(text.strip()) > 0:
        text_clean = text.strip()
        # 正文过短（<20字符）— 可能是空文件或纯图片
        if len(text_clean) < 20:
            return {
                "valid": False,
                "level": "不建议入库",
                "reason": "文件正文过短（可能为纯图片或空文件）",
                "suggestion": "请确认文件内容是否完整",
            }

    # ── 规则16: 无标题、无文号、无发文单位，且正文中无政策关键词 ──
    if not has_doc_no and not has_policy_kw:
        if text:
            text_upper = text[:2000]
            # 在正文中查找政策关键词
            text_has_policy = any(
                kw in text_upper for kw in
                ["法", "条例", "办法", "规定", "通知", "意见", "决定", "公告",
                 "方案", "指南", "规程", "规范", "标准", "细则",
                 "关于", "印发", "废止", "失效", "施行", "实施"]
            )
            if not text_has_policy:
                return {
                    "valid": False,
                    "level": "不建议入库",
                    "reason": "无标题、无文号，正文中也无政策关键词，可能不是政策文件",
                    "suggestion": "请确认该文件是否属于政策文件，如不是则不应入库",
                }

    # ── 规则17: 检查是否为表格清单类文件 ──
    if text and len(text) > 100:
        # 检查是否大量出现表格特征
        lines = text.split("\n")
        tab_count = sum(1 for l in lines if "\t" in l or "    " in l)
        table_patterns = sum(1 for l in lines if re.match(r"^\s*(序号|编号|项目|名称|数量|金额|备注)\s*[\t|]", l))
        if tab_count > 20 or table_patterns >= 5:
            return {
                "valid": False,
                "level": "待人工确认",
                "reason": "文本包含大量表格特征，可能为表格清单",
                "suggestion": "请确认是否为政策文件，表格清单类文件不建议作为政策入库",
            }

    # ── 综合判断 ──
    if has_doc_no:
        # 有文号 + 标题有效 → 可入库
        return {
            "valid": True,
            "level": "可入库",
            "reason": "标题有效且有文号",
            "suggestion": "",
        }
    else:
        # 标题有效 + 无文号 → 可入库但待验证
        return {
            "valid": True,
            "level": "可入库",
            "reason": "标题有效但无文号",
            "suggestion": "建议后续补充文号",
        }


def clean_filename_for_title(file_name: str) -> str:
    """从文件名提取可能的标题，清洗无意义词。

    清洗规则：
    1. 去掉扩展名
    2. 去掉日期编号
    3. 去掉"扫描件""附件""最终版""盖章版""复制"等无意义词
    """
    if not file_name:
        return ""

    name = file_name.strip()

    # 1. 去掉扩展名
    name = re.sub(r"\.(pdf|docx?|xlsx?|txt|doc)$", "", name, flags=re.IGNORECASE)

    # 2. 去掉日期编号（如 20240115, 2024-01-15, 2024年1号）
    name = re.sub(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?", "", name)
    name = re.sub(r"\d{8}", "", name)
    name = re.sub(r"[（(]\d{4}[）)]", "", name)
    name = re.sub(r"第\d+号", "", name)

    # 3. 去掉无意义词
    noise_words = [
        "扫描件", "附件", "最终版", "盖章版", "复制", "副本",
        "定稿", "送审稿", "征求意见稿", "修改稿", "初稿",
        "（1）", "（2）", "（3）", "(1)", "(2)", "(3)",
        "修订版", "新版", "旧版", "打印版", "电子版",
        "【定稿】", "【最终】", "【扫描】",
    ]
    for w in noise_words:
        name = name.replace(w, "")

    # 4. 清理多余空格和标点
    name = re.sub(r"\s+", "", name)
    name = name.strip("_-—－ （）()[]【】《》")

    return name


def looks_like_policy_filename(name: str) -> bool:
    """检查清洗后的文件名是否像一个政策文件标题"""
    if not name or len(name) < 4:
        return False
    if len(name) > 120:
        return False
    if re.match(r"^[\d\s\.\-_]+$", name):
        return False
    if name in INVALID_TITLE_WORDS:
        return False
    # 包含文件名特有模式
    if re.search(r"\.(pdf|doc|txt)", name, re.IGNORECASE):
        return False
    return True
