"""三级匹配器：文号精确匹配 → 标题精确匹配 → 模糊匹配 → 网络检索"""

from rapidfuzz import fuzz, process

import database.db as db
from config import FUZZY_MATCH_HIGH, FUZZY_MATCH_LOW


def match_by_document_no(document_no: str) -> dict | None:
    """第一优先级：文号精确匹配"""
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
    """第二优先级：标题精确匹配"""
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


def match_by_fuzzy(query: str) -> dict | None:
    """第三优先级：模糊匹配，在全部文件标题中搜索"""
    if not query or len(query) < 2:
        return None

    all_docs = db.get_all_titles()
    if not all_docs:
        return None

    titles = [d["title"] for d in all_docs]

    # 使用 WRatio（加权综合比）对简称/全称/别名等场景效果更好
    result = process.extractOne(
        query, titles,
        scorer=fuzz.WRatio,
        score_cutoff=FUZZY_MATCH_LOW,
    )

    if result is None:
        return None

    best_title, score, idx = result
    doc = all_docs[idx]

    if score >= FUZZY_MATCH_HIGH:
        method = "模糊匹配"
        need_confirm = False
    else:
        method = "模糊匹配"
        need_confirm = True

    return {
        "matched_document_id": doc["id"],
        "matched_title": doc["title"],
        "matched_document_no": doc.get("document_no", ""),
        "match_method": method,
        "match_score": round(score, 1),
        "document_status": doc["status"],
        "need_manual_confirm": need_confirm,
    }


def match_reference(reference: dict) -> dict:
    """对单条引用依据执行三级匹配，返回匹配结果"""
    title = reference.get("title", "")
    document_no = reference.get("document_no", "")

    # L1: 文号精确匹配
    result = match_by_document_no(document_no)
    if result:
        return result

    # L2: 标题精确匹配
    result = match_by_title_exact(title)
    if result:
        return result

    # L3: 模糊匹配（用书名号内标题或整段文本）
    query = title if title else reference.get("text", "")
    result = match_by_fuzzy(query)
    if result:
        return result

    # 未匹配
    return {
        "matched_document_id": None,
        "matched_title": "",
        "matched_document_no": "",
        "match_method": "未匹配",
        "match_score": 0,
    }


def match_all_references(references: list[dict]) -> list[dict]:
    """对全部引用依据执行匹配，返回带匹配结果的列表
    匹配优先级：本地文件库优先，未匹配时尝试网络检索"""
    results = []
    for ref in references:
        match_result = match_reference(ref)
        # 如果本地未匹配，尝试网络检索
        if match_result["match_method"] == "未匹配":
            web_results = _search_web_for_ref(ref)
            match_result["web_results"] = web_results
        else:
            match_result["web_results"] = []
        results.append({**ref, **match_result})
    return results


def _search_web_for_ref(reference: dict) -> list[dict]:
    """对未匹配的引用，通过网络检索补充"""
    query = reference.get("title", "") or reference.get("text", "")
    if not query or len(query) < 3:
        return []

    try:
        from modules.web_search import search_policy_online
        results = search_policy_online(query, max_results=5)
        return results
    except Exception:
        return []
