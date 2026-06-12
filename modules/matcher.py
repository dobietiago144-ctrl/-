"""双轨匹配器：文号匹配 + 标题匹配 并行执行，交叉验证"""

import re
from rapidfuzz import fuzz, process

import database.db as db
from config import FUZZY_MATCH_HIGH, FUZZY_MATCH_LOW


def match_by_document_no(document_no: str) -> dict | None:
    """文号精确匹配"""
    if not document_no:
        return None
    doc = db.get_document_by_no(document_no)
    if doc:
        return {
            "matched_document_id": doc["id"],
            "matched_title": doc["title"],
            "matched_document_no": doc["document_no"],
            "match_method": "文号精确匹配",
            "match_score": 100.0,
            "document_status": doc["status"],
        }
    return None


def match_by_title_exact(title: str) -> dict | None:
    """标题精确匹配"""
    if not title:
        return None
    doc = db.get_document_by_title(title)
    if doc:
        return {
            "matched_document_id": doc["id"],
            "matched_title": doc["title"],
            "matched_document_no": doc.get("document_no", ""),
            "match_method": "标题精确匹配",
            "match_score": 100.0,
            "document_status": doc["status"],
        }
    return None


def match_by_title_embedded(title: str) -> dict | None:
    """标题内嵌匹配：文件库标题包含《输入标题》，或去掉外壳后能匹配。

    规则：
    1. 如果文件库标题中包含《输入标题》
    2. 或者去掉"关于印发"、"的通知"等外壳后能匹配
    3. 视为高置信度匹配，匹配分数100
    """
    if not title or len(title) < 2:
        return None

    all_docs = db.get_all_titles()
    if not all_docs:
        return None

    clean_title = title.strip()

    for doc in all_docs:
        doc_title = doc["title"]

        # 规则1: 文件库标题直接包含《输入标题》
        if f"《{clean_title}》" in doc_title:
            return {
                "matched_document_id": doc["id"],
                "matched_title": doc_title,
                "matched_document_no": doc.get("document_no", ""),
                "match_method": "标题内嵌匹配",
                "match_score": 100.0,
                "document_status": doc["status"],
            }

        # 规则2: 去掉外壳后比较
        # 常见外壳模式: "XXX关于印发《Y》的通知", "XXX关于发布《Y》的公告" 等
        embedded_title = _extract_embedded_title(doc_title)
        if embedded_title and embedded_title == clean_title:
            return {
                "matched_document_id": doc["id"],
                "matched_title": doc_title,
                "matched_document_no": doc.get("document_no", ""),
                "match_method": "标题内嵌匹配",
                "match_score": 100.0,
                "document_status": doc["status"],
            }

    return None


def _extract_embedded_title(full_title: str) -> str | None:
    """从完整文件名称中提取内嵌标题。

    例如:
    '自然资源部关于印发《城镇开发边界管理办法（试行）》的通知'
    → '城镇开发边界管理办法（试行）'
    """
    # 匹配书名号内的标题
    m = re.search(r"[《〈]([^》〉]+?)[》〉]", full_title)
    if m:
        return m.group(1).strip()
    return None


def match_by_fuzzy(query: str) -> dict | None:
    """模糊匹配，在全部文件标题中搜索。只能作为提醒，不得直接判定严重问题。"""
    if not query or len(query) < 2:
        return None

    all_docs = db.get_all_titles()
    if not all_docs:
        return None

    titles = [d["title"] for d in all_docs]

    result = process.extractOne(
        query, titles,
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_MATCH_LOW,
    )

    if result is None:
        return None

    best_title, score, idx = result
    doc = all_docs[idx]

    return {
        "matched_document_id": doc["id"],
        "matched_title": doc["title"],
        "matched_document_no": doc.get("document_no", ""),
        "match_method": "模糊匹配",
        "match_score": round(score, 1),
        "document_status": doc["status"],
        "need_manual_confirm": True,
    }


def match_reference(reference: dict) -> dict:
    """对单条引用执行双轨匹配：
    1. 同时执行 title_match 和 no_match
    2. 交叉验证，判断是否一致
    3. 标题内嵌匹配作为高置信度匹配
    """
    title = reference.get("title", "")
    document_no = reference.get("document_no", "")

    result = _dual_track_match(title, document_no)

    # 如果双轨没有结论，尝试模糊匹配
    if result["match_method"] == "未匹配":
        query = title if title else reference.get("text", "")
        fuzzy_result = match_by_fuzzy(query)
        if fuzzy_result:
            result = fuzzy_result

    return result


def _dual_track_match(title: str, document_no: str) -> dict:
    """双轨匹配核心：
    - track A: 按文件名称匹配（精确 → 内嵌）
    - track B: 按文号匹配
    然后交叉验证。
    """
    # Track A: 标题匹配
    title_match = match_by_title_exact(title)
    if not title_match:
        title_match = match_by_title_embedded(title)

    # Track B: 文号匹配
    no_match = match_by_document_no(document_no)

    # 情况1: 两个都有结果
    if title_match and no_match:
        if title_match["matched_document_id"] == no_match["matched_document_id"]:
            # ID一致，名称和文号对应，使用标题匹配结果（更精确）
            return title_match
        else:
            # ID不一致：文件名称与文号不匹配，严重问题
            return {
                "matched_document_id": no_match["matched_document_id"],
                "matched_title": no_match["matched_title"],
                "matched_document_no": no_match["matched_document_no"],
                "match_method": "文号精确匹配",
                "match_score": 100.0,
                "document_status": no_match["document_status"],
                "title_no_mismatch": True,
                "mismatch_title_match": title_match,
                "mismatch_no_match": no_match,
            }

    # 情况2: 只有标题匹配，但报告中有文号
    if title_match and document_no:
        return title_match

    # 情况3: 只有标题匹配，报告中无文号
    if title_match:
        return title_match

    # 情况4: 只有文号匹配，但报告中有标题
    if no_match and title:
        # 检查报告标题是否和 no_match 文件标题一致或高度相关
        official_title = no_match.get("matched_title", "")
        related = _check_title_relation(title, official_title)
        if related:
            return no_match
        else:
            return {
                "matched_document_id": no_match["matched_document_id"],
                "matched_title": no_match["matched_title"],
                "matched_document_no": no_match["matched_document_no"],
                "match_method": "文号精确匹配",
                "match_score": 100.0,
                "document_status": no_match["document_status"],
                "title_no_suspect": True,
                "reported_title": title,
            }

    # 情况5: 只有文号匹配
    if no_match:
        return no_match

    # 未匹配
    return {
        "matched_document_id": None,
        "matched_title": "",
        "matched_document_no": "",
        "match_method": "未匹配",
        "match_score": 0,
    }


def _check_title_relation(reported_title: str, official_title: str) -> bool:
    """检查报告标题是否与正式文件标题一致或高度相关。"""
    if not reported_title or not official_title:
        return False

    rt = reported_title.strip().replace(" ", "").replace("　", "")
    ot = official_title.strip().replace(" ", "").replace("　", "")

    # 完全一致
    if rt == ot:
        return True

    # 一个包含另一个
    if rt in ot or ot in rt:
        return True

    # 去掉外壳后比较
    embedded = _extract_embedded_title(official_title)
    if embedded and embedded.replace(" ", "").replace("　", "") == rt:
        return True

    # 模糊比较
    score = fuzz.WRatio(rt, ot)
    return score >= 90


def match_all_references(references: list[dict]) -> list[dict]:
    """对全部引用依据执行双轨匹配"""
    results = []
    for ref in references:
        match_result = match_reference(ref)
        results.append({**ref, **match_result})
    return results
