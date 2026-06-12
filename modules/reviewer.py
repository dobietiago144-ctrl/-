"""审查模块：根据双轨匹配结果判断风险等级、查找替代文件、生成修改建议"""

import re
from config import STATUS_TO_RISK, RISK_LEVEL_OPTIONS, DOCUMENT_NO_PATTERNS, KNOWN_DOC_NO_PREFIXES
import database.db as db


_DOC_NO_PARTS_RE = re.compile(
    r"([\w一-鿿、]+?)[〔\(（\[\【](\d{4})[〕\)）\]\】]\s*(\d+)\s*号?"
)


def parse_document_no_parts(doc_no: str) -> dict | None:
    """将文号解析为四个部分。

    返回:
        {"prefix": str, "year": str, "number": str, "raw": str,
         "bracket_format_ok": bool}
    解析失败返回 None。
    """
    if not doc_no:
        return None

    m = _DOC_NO_PARTS_RE.search(doc_no)
    if not m:
        return None

    prefix = m.group(1)
    year_str = m.group(2)
    number = m.group(3)
    raw = m.group(0)

    bracket_content = "〔" + year_str + "〕"
    bracket_format_ok = bracket_content in raw

    return {
        "prefix": prefix,
        "year": year_str,
        "number": number,
        "raw": raw,
        "bracket_format_ok": bracket_format_ok,
    }


def compare_document_no_parts(input_no: str, official_no: str) -> dict:
    """对比报告文号和文件库正式文号，逐部分比较。

    比较规则：
    1. prefix 不一致：严重问题，文号前缀不一致
    2. year 不一致：严重问题，文号年份不一致
    3. number 不一致：严重问题，文号序号不一致
    4. 只有括号格式不规范：低风险格式提醒
    5. 全部一致：正常

    格式提醒不能覆盖真实性问题。
    """
    result = {
        "prefix_match": True,
        "year_match": True,
        "number_match": True,
        "bracket_format_ok": True,
        "issue_type": "正常",
        "risk_level": "正常",
        "suggestion": "",
        "parts_input": None,
        "parts_official": None,
    }

    parts_input = parse_document_no_parts(input_no)
    parts_official = parse_document_no_parts(official_no)

    result["parts_input"] = parts_input
    result["parts_official"] = parts_official

    if not parts_input or not parts_official:
        if input_no.strip() != official_no.strip():
            result["issue_type"] = "文号不一致"
            result["risk_level"] = "严重问题"
            result["prefix_match"] = False
            result["year_match"] = False
            result["number_match"] = False
            result["suggestion"] = (
                "建议将文号修改为「" + official_no + "」。"
            )
        return result

    # 逐部分比较
    if parts_input["prefix"] != parts_official["prefix"]:
        result["prefix_match"] = False
    if parts_input["year"] != parts_official["year"]:
        result["year_match"] = False
    if parts_input["number"] != parts_official["number"]:
        result["number_match"] = False

    result["bracket_format_ok"] = parts_input["bracket_format_ok"]

    # 优先级: 前缀 > 年份 > 序号 > 括号格式
    # 格式提醒不能覆盖真实性问题
    if not result["prefix_match"]:
        result["issue_type"] = "文号前缀不一致"
        result["risk_level"] = "严重问题"
        result["suggestion"] = (
            "报告文号前缀为「" + parts_input["prefix"] + "」，"
            "文件库正式文号前缀为「" + parts_official["prefix"] + "」，两者不一致。"
            "建议将文号修改为「" + official_no + "」。"
        )
        return result

    if not result["year_match"]:
        result["issue_type"] = "文号年份不一致"
        result["risk_level"] = "严重问题"
        result["suggestion"] = (
            "报告文号年份为「" + parts_input["year"] + "」，"
            "文件库正式文号年份为「" + parts_official["year"] + "」，两者不一致。"
            "建议将文号修改为「" + official_no + "」。"
        )
        return result

    if not result["number_match"]:
        result["issue_type"] = "文号序号不一致"
        result["risk_level"] = "严重问题"
        result["suggestion"] = (
            "建议将「" + input_no + "」修改为「" + official_no + "」。"
        )
        return result

    if not result["bracket_format_ok"]:
        result["issue_type"] = "文号括号格式不规范"
        result["risk_level"] = "低风险"
        corrected = input_no
        for left, right in [("(", ")"), ("（", "）"), ("[", "]"), ("【", "】")]:
            corrected = corrected.replace(left, "〔").replace(right, "〕")
        result["suggestion"] = "括号格式不规范，建议使用 " + corrected + "。"
        return result

    result["issue_type"] = "正常"
    result["risk_level"] = "正常"
    result["suggestion"] = ""
    return result


def validate_document_no_format(doc_no: str) -> dict:
    """校验文号格式是否合法。只检查括号、年份、序号、号字等格式是否规范。"""
    if not doc_no:
        return {"valid": True, "issue": ""}

    m = _DOC_NO_PARTS_RE.search(doc_no)
    if not m:
        return {"valid": True, "issue": ""}

    prefix = m.group(1)
    year = int(m.group(2))
    full_match = m.group(0)
    issues = []

    if not full_match.endswith("号"):
        issues.append("文号末尾缺少「号」字")

    has_standard_bracket = "〔" in full_match and "〕" in full_match
    if not has_standard_bracket:
        corrected = full_match
        for left, right in [("(", ")"), ("（", "）"), ("[", "]"), ("【", "】")]:
            corrected = corrected.replace(left, "〔").replace(right, "〕")
        issues.append("括号格式不规范，建议使用 " + corrected)

    if year > 2027:
        issues.append("文号年份 " + str(year) + " 尚未到达，疑似有误")
    elif year < 1980:
        issues.append("文号年份 " + str(year) + " 异常偏早，疑似有误")

    prefix_in_whitelist = any(
        prefix == known or prefix.startswith(known)
        for known in KNOWN_DOC_NO_PREFIXES
    )
    if not prefix_in_whitelist:
        issues.append(
            "文号前缀「" + prefix + "」未在常见文号前缀库中找到，请人工核查其准确性"
        )

    if issues:
        return {"valid": False, "issue": "；".join(issues)}
    return {"valid": True, "issue": ""}


def assess_risk(match_result: dict) -> dict:
    """根据匹配结果评估风险等级（只基于文件状态）"""
    risk_level = "提醒"
    judgment = ""
    need_confirm = match_result.get("need_manual_confirm", False)

    if match_result["match_method"] == "未匹配":
        risk_level = "提醒"
        judgment = "文件库中未找到该依据，建议人工核查是否需要补充入库"
        need_confirm = True
    else:
        status = match_result.get("document_status", "")
        risk_level = STATUS_TO_RISK.get(status, "提醒")
        judgment = "匹配到文件库记录，当前状态为「" + status + "」"

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
        rep = replacements[0]
        return {
            "suggested_document_id": rep["new_document_id"],
            "suggested_title": rep.get("title", ""),
        }
    return {"suggested_document_id": None, "suggested_title": ""}


def generate_suggestion(risk_level: str, suggested_title: str, doc_status: str) -> str:
    """生成修改建议文字"""
    if risk_level == "严重问题":
        if doc_status in ("已废止", "已失效"):
            if suggested_title:
                return "该文件已" + doc_status.lstrip("已") + "，建议替换为《" + suggested_title + "》"
            return "该文件已" + doc_status.lstrip("已") + "，文件库中未找到替代文件，建议人工查找现行有效文件替换"
        return ""
    elif risk_level == "高风险":
        if suggested_title:
            desc = doc_status.lstrip("已")
            return "该文件已" + desc + "，建议替换为《" + suggested_title + "》"
        else:
            desc = doc_status.lstrip("已")
            return "该文件已" + desc + "，请查找现行有效文件替换"
    elif risk_level == "中风险":
        if suggested_title:
            return "建议核查是否应替换或参照《" + suggested_title + "》"
        return "文件状态为「" + doc_status + "」，建议人工核查是否需要更新"
    elif risk_level == "低风险":
        return "该文件即将失效，请关注后续更新"
    elif risk_level == "提醒":
        return "建议补充文件库记录或人工确认"
    else:
        return ""


def review_single_reference(matched_ref: dict) -> dict:
    """对单条引用执行完整审查。

    审查优先级：
    1. 双轨匹配交叉验证：文件名称和文号是否指向同一文件
    2. 文号逐部分比较（prefix/year/number）
    3. 文件是否废止、失效、被替代
    4. 是否存在新版本
    5. 格式是否规范（仅提醒）
    6. 是否未入库
    """
    match_method = matched_ref.get("match_method", "未匹配")
    input_title = matched_ref.get("title", "")
    input_doc_no = matched_ref.get("document_no", "")
    matched_doc_no = matched_ref.get("matched_document_no", "")
    matched_title = matched_ref.get("matched_title", "")

    judgement_parts = []
    suggestion_parts = []
    final_risk = "正常"
    need_confirm = False
    problem_type = ""
    is_core = 0

    # === 优先级0: 双轨匹配交叉验证 ===
    title_no_mismatch = matched_ref.get("title_no_mismatch", False)
    title_no_suspect = matched_ref.get("title_no_suspect", False)

    if title_no_mismatch:
        # 文件名称与文号不匹配：严重问题
        mismatch_info = matched_ref.get("mismatch_title_match", {})
        mismatch_no = matched_ref.get("mismatch_no_match", {})
        judgement_parts.append(
            "严重问题：文件名称「" + input_title + "」指向《" + mismatch_info.get("matched_title", "") + "》，"
            "但文号「" + input_doc_no + "」对应《" + mismatch_no.get("matched_title", "") + "》，"
            "报告引用的文件名称与文号不匹配"
        )
        final_risk = "严重问题"
        problem_type = "文件名称与文号不匹配"
        is_core = 1
        suggestion_parts.append(
            "请核实报告引用的正确文件名称和文号。"
            "可能正确文件为：《" + mismatch_info.get("matched_title", "") + "》"
            " 或 《" + mismatch_no.get("matched_title", "") + "》"
        )

    elif title_no_suspect:
        # 只有文号匹配，但报告中有标题，标题与正式文件标题不一致
        reported_title = matched_ref.get("reported_title", "")
        judgement_parts.append(
            "文号「" + input_doc_no + "」对应文件《" + matched_title + "》，"
            "但报告中引用的名称为「" + reported_title + "」"
        )
        if final_risk == "正常":
            final_risk = "中风险"
        problem_type = "文号对应文件与报告名称疑似不一致"
        need_confirm = True

    # === 优先级1: 文号逐部分比较 ===
    doc_no_comparison = None
    if match_method != "未匹配" and input_doc_no and matched_doc_no:
        doc_no_comparison = compare_document_no_parts(input_doc_no, matched_doc_no)

    if doc_no_comparison and doc_no_comparison["issue_type"] != "正常":
        issue_type = doc_no_comparison["issue_type"]
        risk_level_val = doc_no_comparison["risk_level"]
        suggestion = doc_no_comparison["suggestion"]

        if issue_type == "文号序号不一致":
            judgement_parts.append(
                "文件名称匹配成功，但报告引用文号（" + input_doc_no + "）"
                "与文件库正式文号（" + matched_doc_no + "）序号不一致"
            )
            final_risk = risk_level_val
            problem_type = "文号序号不一致"
            is_core = 1
            suggestion_parts.append(suggestion)

        elif issue_type == "文号年份不一致":
            judgement_parts.append(
                "文件名称匹配成功，但报告引用文号（" + input_doc_no + "）"
                "与文件库正式文号（" + matched_doc_no + "）年份不一致"
            )
            final_risk = risk_level_val
            problem_type = "文号年份不一致"
            is_core = 1
            suggestion_parts.append(suggestion)

        elif issue_type == "文号前缀不一致":
            judgement_parts.append(
                "文件名称匹配成功，但报告引用文号（" + input_doc_no + "）"
                "与文件库正式文号（" + matched_doc_no + "）前缀不一致"
            )
            final_risk = risk_level_val
            problem_type = "文号前缀不一致"
            is_core = 1
            suggestion_parts.append(suggestion)

        elif issue_type == "文号括号格式不规范":
            judgement_parts.append("文号括号格式不规范")
            suggestion_parts.append(suggestion)
            if final_risk == "正常":
                final_risk = "低风险"
            if not problem_type:
                problem_type = "文号括号格式不规范"

    # === 优先级2-3: 文件状态风险评估和替代文件 ===
    risk = assess_risk(matched_ref)
    replacement = find_suggested_replacement(
        matched_ref.get("matched_document_id"),
        risk["risk_level"],
    )

    if match_method != "未匹配" and risk["risk_level"] not in ("正常", "提醒"):
        judgement_parts.append(risk["judgment_basis"])
        if risk["risk_level"] == "严重问题":
            if final_risk not in ("严重问题",):
                final_risk = "严重问题"
            if not problem_type:
                problem_type = "文件状态异常"
            is_core = 1
        elif risk["risk_level"] == "高风险" and final_risk not in ("严重问题", "高风险"):
            final_risk = "高风险"
        elif risk["risk_level"] == "中风险" and final_risk not in ("严重问题", "高风险", "中风险"):
            final_risk = "中风险"
        if not problem_type:
            problem_type = "文件状态异常"

    status_suggestion = generate_suggestion(
        risk["risk_level"],
        replacement["suggested_title"],
        matched_ref.get("document_status", ""),
    )
    if status_suggestion:
        suggestion_parts.append(status_suggestion)

    if risk.get("need_manual_confirm"):
        need_confirm = True

    # === 优先级4: 文号格式校验（仅提醒，不改变 risk_level） ===
    if input_doc_no:
        fmt_check = validate_document_no_format(input_doc_no)
        if not fmt_check["valid"]:
            judgement_parts.append("文号格式问题：" + fmt_check["issue"])
            # 格式问题只做低风险提醒，不影响已有风险判断
            if final_risk == "正常":
                final_risk = "低风险"

    # === 未匹配时的处理 ===
    if match_method == "未匹配":
        judgement_parts.append(risk["judgment_basis"])
        final_risk = "提醒"
        problem_type = "文件库未收录"
        suggestion_parts.append(generate_suggestion("提醒", "", ""))
        need_confirm = True

    # === 模糊匹配只能作为提醒 ===
    if match_method == "模糊匹配":
        final_risk = "提醒"
        problem_type = "模糊匹配，需人工确认"
        need_confirm = True

    # === 汇总 ===
    judgement = "；".join(judgement_parts)
    suggestion = "；".join([s for s in suggestion_parts if s])

    if not judgement:
        judgement = "文件名称和文号匹配一致，文件状态正常。"
    if not problem_type:
        problem_type = "正常"

    # 确定置信度
    score = matched_ref.get("match_score", 0)
    if score >= 100:
        confidence = "高"
    elif score >= 95:
        confidence = "高"
    elif score >= 85:
        confidence = "中"
    elif score > 0:
        confidence = "低"
    else:
        confidence = "无"

    return {
        "original_reference": matched_ref.get("text", ""),
        "recognized_title": input_title,
        "recognized_document_no": input_doc_no,
        "matched_document_id": matched_ref.get("matched_document_id"),
        "matched_title": matched_title,
        "matched_document_no": matched_doc_no,
        "official_title": matched_title,
        "official_document_no": matched_doc_no,
        "match_method": match_method,
        "match_score": matched_ref.get("match_score", 0),
        "document_status": matched_ref.get("document_status", ""),
        "risk_level": final_risk,
        "problem_type": problem_type,
        "judgment_basis": judgement,
        "suggested_document_id": replacement["suggested_document_id"],
        "suggested_title": replacement["suggested_title"],
        "suggestion": suggestion,
        "confidence": confidence,
        "occurrence_count": 1,
        "location": "",
        "is_core_issue": is_core,
        "need_manual_confirm": 1 if need_confirm else 0,
    }


def review_all(matched_refs: list[dict]) -> list[dict]:
    """批量审查全部引用"""
    return [review_single_reference(ref) for ref in matched_refs]


def validate_document_metadata(text: str) -> list[dict]:
    """校验文档自身的元数据一致性。

    警告：此函数会对待审查报告全文做元数据校验，容易把报告中引用的
    政策文号当成报告自身文号而误报。默认不在审查页面展示，
    仅作为调试信息/高级检查使用。
    """
    from modules.metadata_extractor import extract_title, extract_document_no, extract_dates

    issues = []
    title = extract_title(text)
    doc_no = extract_document_no(text)
    dates = extract_dates(text)

    if doc_no:
        fmt = validate_document_no_format(doc_no)
        if not fmt["valid"]:
            issues.append({
                "field": "文号格式",
                "issue": fmt["issue"],
                "severity": "warning",
            })

    if doc_no and dates:
        m = re.search(r"[〔\(（](\d{4})[〕\)）]", doc_no)
        if m:
            doc_year = m.group(1)
            for date_key, date_label in [("publish_date", "发布日期"), ("effective_date", "实施日期")]:
                date_val = dates.get(date_key, "")
                if date_val and date_val[:4] != doc_year:
                    issues.append({
                        "field": "年份不一致",
                        "issue": "文号年份（" + doc_year + "）与" + date_label + "（" + date_val[:4] + "）不一致",
                        "severity": "warning",
                    })

    if doc_no and title:
        m = re.search(r"[〔\(（](\d{4})[〕\)）]", doc_no)
        if m:
            doc_year = int(m.group(1))
            title_years = re.findall(r"(?<!\d)(\d{4})(?!\d)", title)
            for ty in title_years:
                ty_int = int(ty)
                if ty_int != doc_year and 1980 <= ty_int <= 2027:
                    issues.append({
                        "field": "年份不一致",
                        "issue": "文号年份（" + str(doc_year) + "）与标题中出现的年份（" + str(ty_int) + "）不一致",
                        "severity": "warning",
                    })

    if not doc_no:
        issues.append({
            "field": "文号缺失",
            "issue": "未从文档中识别到文号，请确认文档内容是否完整",
            "severity": "warning",
        })

    return issues
