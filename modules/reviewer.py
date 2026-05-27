"""审查模块：根据匹配结果判断风险等级、查找替代文件、生成修改建议"""

from config import STATUS_TO_RISK, RISK_LEVEL_OPTIONS
import database.db as db


def assess_risk(match_result: dict) -> dict:
    """根据匹配结果评估风险等级"""
    risk_level = "提醒"
    judgment = ""
    need_confirm = match_result.get("need_manual_confirm", False)
    web_results = match_result.get("web_results", [])

    if match_result["match_method"] == "未匹配":
        if web_results:
            risk_level = "提醒"
            sources = [r.get("source", "") for r in web_results[:3]]
            judgment = f"文件库中未找到该依据，网络检索发现 {len(web_results)} 条相关结果（{', '.join(sources)}），建议人工核实后入库"
            need_confirm = True
        else:
            risk_level = "提醒"
            judgment = "文件库中未找到该依据，网络检索也未发现结果，建议人工核查是否需要补充入库"
            need_confirm = True
    else:
        status = match_result.get("document_status", "")
        risk_level = STATUS_TO_RISK.get(status, "提醒")
        judgment = f"匹配到文件库记录，当前状态为「{status}」"

    return {
        "risk_level": risk_level,
        "judgment_basis": judgment,
        "need_manual_confirm": need_confirm,
    }


def find_suggested_replacement(matched_doc_id: int | None, risk_level: str) -> dict:
    """查找建议替换文件"""
    if matched_doc_id is None or risk_level in ("正常", "提醒"):
        return {"suggested_document_id": None, "suggested_title": ""}

    replacements = db.find_replacement(matched_doc_id)
    if replacements:
        rep = replacements[0]  # 取第一个替代文件
        return {
            "suggested_document_id": rep["new_document_id"],
            "suggested_title": rep.get("title", ""),
        }
    return {"suggested_document_id": None, "suggested_title": ""}


def generate_suggestion(risk_level: str, suggested_title: str, doc_status: str) -> str:
    """生成修改建议文字"""
    if risk_level == "高风险":
        if suggested_title:
            desc = doc_status.lstrip("已")
            return f"该文件已{desc}，建议替换为《{suggested_title}》"
            desc = doc_status.lstrip("已")
            return f"该文件已{desc}，请查找现行有效文件替换"
    elif risk_level == "中风险":
        if suggested_title:
            return f"建议核查是否应替换或参照《{suggested_title}》"
        return f"文件状态为「{doc_status}」，建议人工核查是否需要更新"
    elif risk_level == "低风险":
        return "该文件即将失效，请关注后续更新"
    elif risk_level == "提醒":
        return "建议补充文件库记录或人工确认"
    else:
        return ""


def review_single_reference(matched_ref: dict) -> dict:
    """对单条引用执行完整审查，返回审查结果"""
    # 风险评估
    risk = assess_risk(matched_ref)

    # 替代文件查找
    replacement = find_suggested_replacement(
        matched_ref.get("matched_document_id"),
        risk["risk_level"],
    )

    # 生成建议
    suggestion = generate_suggestion(
        risk["risk_level"],
        replacement["suggested_title"],
        matched_ref.get("document_status", ""),
    )

    return {
        "original_reference": matched_ref.get("text", ""),
        "matched_document_id": matched_ref.get("matched_document_id"),
        "matched_title": matched_ref.get("matched_title", ""),
        "matched_document_no": matched_ref.get("matched_document_no", ""),
        "match_method": matched_ref.get("match_method", "未匹配"),
        "match_score": matched_ref.get("match_score", 0),
        "document_status": matched_ref.get("document_status", ""),
        "risk_level": risk["risk_level"],
        "judgment_basis": risk["judgment_basis"],
        "suggested_document_id": replacement["suggested_document_id"],
        "suggested_title": replacement["suggested_title"],
        "suggestion": suggestion,
        "need_manual_confirm": 1 if risk["need_manual_confirm"] else 0,
    }


def review_all(matched_refs: list[dict]) -> list[dict]:
    """批量审查全部引用"""
    return [review_single_reference(ref) for ref in matched_refs]
