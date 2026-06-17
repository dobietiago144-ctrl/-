"""引用提取：从待审查文档中识别政策文件引用"""

import re
from config import DOCUMENT_NO_PATTERNS


BASIS_SECTION_KEYWORDS = [
    "编制依据", "政策依据", "法律法规依据", "技术依据",
    "规范性文件依据", "参考文件", "相关标准", "相关规范",
    "标准依据", "法律依据", "法规依据", "规范性依据",
    "依据文件", "引用标准", "技术标准依据",
    "规范性引用文件", "引用文件", "参考标准", "规范性引用",
]


def find_basis_section(text: str) -> str:
    """定位编制依据章节，返回该章节文本"""
    lines = text.split("\n")
    in_section = False
    section_lines = []

    pattern = re.compile(
        r"^\s*(?:[\(（]?\d+[\)）]?[\.\、\s]?)?\s*("
        + "|".join(BASIS_SECTION_KEYWORDS)
        + r")"
    )
    other = re.compile(
        r"^\s*(?:[\(（]?\d+[\)）]?[\.\、\s]?)?\s*"
        r"(?:项目|工程|前言|概述|总则|一[、.]|二[、.]|三[、.]|四[、.]|五[、.])"
    )

    for line in lines:
        if pattern.match(line):
            in_section = True
            section_lines.append(line)
        elif in_section:
            if other.match(line) and not re.match(r"^\s*\d+[\.\、\s)]", line):
                break
            section_lines.append(line)
    return "\n".join(section_lines) if section_lines else text


def extract_book_title_refs(text: str) -> list[dict]:
    """提取书名号引用，在同一句内关联文号"""
    results = []
    seen_keys = set()  # 按 title + document_no 组合去重

    # 按句子分割（。；！？\n），避免跨句误关联文号
    sentences = re.split(r"[。；！？\n]+", text)

    for sentence in sentences:
        # 使用 finditer 获取每个书名号引用的位置
        title_matches = list(re.finditer(r"[《〈]([^》〉]+?)[》〉]", sentence))
        if not title_matches:
            continue

        # 从该句提取所有文号
        doc_nos_in_sentence = []
        for ptn in DOCUMENT_NO_PATTERNS:
            doc_nos_in_sentence.extend(re.findall(ptn, sentence))

        for m in title_matches:
            title = m.group(1).strip()
            if not title or len(title) < 2:
                continue
            title_pos = m.start()

            # 在句内找到书名号后的第一个文号
            associated_no = ""
            after_title = sentence[title_pos:]
            for ptn in DOCUMENT_NO_PATTERNS:
                dm = re.search(ptn, after_title)
                if dm:
                    associated_no = dm.group(0)
                    break
            if not associated_no and doc_nos_in_sentence:
                associated_no = doc_nos_in_sentence[-1]

            # 按 title + document_no 组合去重，避免同名不同文号的条目被错误合并
            key = (title.replace(" ", "").replace("　", ""),
                   associated_no.replace(" ", "").replace("　", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            results.append({
                "text": f"《{title}》",
                "title": title,
                "document_no": associated_no,
                "source": "书名号提取",
                "confidence": "高",
            })

    return results


def extract_document_no_refs(text: str, already_covered: set) -> list[dict]:
    """提取文中出现的文号，排除已被书名号引用覆盖的"""
    results = []
    seen = set()

    for pattern in DOCUMENT_NO_PATTERNS:
        for m in re.finditer(pattern, text):
            doc_no = m.group(0)
            doc_no = doc_no.replace(" ", "").replace("　", "")  # 去除PDF提取引入的空格
            if doc_no in seen or doc_no in already_covered:
                continue
            # 跳过包含已覆盖文号的匹配（正则可能贪婪捕获过多上下文）
            if any(cn in doc_no for cn in already_covered):
                continue
            seen.add(doc_no)

            # 按句子判断是否已有书名号
            sent_start = max(0, max(
                text.rfind("。", 0, m.start()),
                text.rfind("；", 0, m.start()),
                text.rfind("\n", 0, m.start()),
            ))
            sent_end = min(len(text), min(
                (pos for pos in [text.find("。", m.end()), text.find("；", m.end()), text.find("\n", m.end())] if pos >= 0),
                default=len(text),
            ))
            sentence = text[sent_start:sent_end]

            if re.search(r"[《〈].+?[》〉]", sentence):
                continue

            results.append({
                "text": doc_no,
                "title": "",
                "document_no": doc_no,
                "source": "文号提取",
                "confidence": "高",
            })

    return results


def extract_keyword_refs(text: str, already_covered_titles: set) -> list[dict]:
    """提取含政策关键词但未被书名号覆盖的引用句"""
    kw_pattern = re.compile(
        r"(?:按照|根据|依据|参照|执行|遵照|符合)"
        r".{0,30}(?:办法|规定|规程|指南|条例|通知|标准|规范|细则|纲要|规划|方案|意见|决定|公告)"
    )

    results = []
    seen = set()

    for m in kw_pattern.finditer(text):
        ref_text = m.group(0).strip()
        if len(ref_text) < 6 or len(ref_text) > 150:
            continue
        # 跳过含书名号的内容（开闭书号或仅开书号都跳过）
        if re.search(r"[《〈]", ref_text):
            continue
        key = ref_text.replace(" ", "")
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "text": ref_text,
            "title": "",
            "document_no": "",
            "source": "关键词提取",
            "confidence": "中",
        })

    return results


def extract_all_references(text: str) -> list[dict]:
    """从待审查文档中提取所有引用依据，去重并合并"""
    basis_text = find_basis_section(text)
    combined = basis_text + "\n" + text

    # L1: 书名号引用（同时提取关联文号）
    book_refs = extract_book_title_refs(combined)

    # 收集所有已覆盖的文号
    covered_doc_nos = set()
    for r in book_refs:
        if r["document_no"]:
            covered_doc_nos.add(r["document_no"])

    # L2: 独立的文号引用
    doc_no_refs = extract_document_no_refs(combined, covered_doc_nos)

    # L3: 关键词补充，排除已覆盖的
    book_title_set = {r["title"].replace(" ", "") for r in book_refs}
    kw_refs = extract_keyword_refs(combined, book_title_set)
    # 过滤含已覆盖文号的关键词引用 + 过滤含文号模式的引用（已被L1/L2覆盖）
    kw_refs = [
        r for r in kw_refs
        if not any(dn in r["text"] for dn in covered_doc_nos)
        and not any(re.search(ptn, r["text"]) for ptn in DOCUMENT_NO_PATTERNS)
    ]

    all_refs = book_refs + doc_no_refs + kw_refs

    # 最终去重
    final = []
    seen_keys = set()
    for r in all_refs:
        key = r["text"].replace(" ", "").replace("　", "")
        if key in seen_keys:
            continue
        # 跳过是其他条目子串的
        is_sub = any(key != ok and key in ok for ok in seen_keys)
        if is_sub:
            continue
        seen_keys.add(key)
        final.append(r)

    return final
