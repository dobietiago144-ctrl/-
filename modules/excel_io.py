"""Excel 批量导入导出"""

import io
import os
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

from config import DOC_STATUS_OPTIONS, DOC_CATEGORY_OPTIONS, REGION_OPTIONS
import database.db as db

# 导入模板表头
IMPORT_HEADERS = [
    "文件名称", "文号", "发文单位", "发布日期", "实施日期",
    "失效日期", "文件状态", "适用地区", "文件类别", "关键词",
    "废止依据", "替代文件", "原文链接", "备注",
]

# 导出表头
EXPORT_HEADERS = [
    "ID", "文件名称", "文号", "发文单位", "发布日期", "实施日期",
    "失效日期", "文件状态", "适用地区", "文件类别", "关键词",
    "摘要", "来源类型", "原文链接", "是否确认", "备注",
    "创建时间", "更新时间",
]


def generate_import_template() -> bytes:
    """生成导入模板 Excel，供用户下载"""
    wb = Workbook()
    ws = wb.active
    ws.title = "政策文件导入模板"

    # 写表头
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col, h in enumerate(IMPORT_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # 写入示例数据
    example = [
        "XX管理办法", "自然资发〔2024〕10号", "自然资源部",
        "2024-01-15", "2024-03-01", "", "现行有效",
        "全国", "部门规章", "耕地保护,占补平衡", "", "", "", "",
    ]
    for col, val in enumerate(example, 1):
        ws.cell(row=2, column=col, value=val)

    # 设置列宽
    widths = [30, 22, 16, 12, 12, 12, 12, 10, 12, 20, 30, 30, 30, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    # 添加数据验证说明页
    ws2 = wb.create_sheet("填写说明")
    notes = [
        ["字段", "说明", "可选值"],
        ["文件名称", "必填，政策文件正式名称", ""],
        ["文号", "如 自然资发〔2024〕10号", ""],
        ["发文单位", "发文机关", ""],
        ["发布日期", "格式 YYYY-MM-DD", ""],
        ["实施日期", "格式 YYYY-MM-DD", ""],
        ["失效日期", "格式 YYYY-MM-DD，不确定可留空", ""],
        ["文件状态", "从可选值中选择", "、".join(DOC_STATUS_OPTIONS)],
        ["适用地区", "全国/省/市/县", "、".join(REGION_OPTIONS)],
        ["文件类别", "从可选值中选择", "、".join(DOC_CATEGORY_OPTIONS)],
        ["关键词", "多个关键词用逗号分隔", ""],
        ["废止依据", "说明废止该文件的新文件或依据", ""],
        ["替代文件", "替代本文件的新文件名称", ""],
        ["原文链接", "政府网站原文链接", ""],
        ["备注", "其他补充信息", ""],
    ]
    for r, row_data in enumerate(notes, 1):
        for c, val in enumerate(row_data, 1):
            cell = ws2.cell(row=r, column=c, value=val)
            if r == 1:
                cell.font = Font(bold=True)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def parse_import_excel(file_path: str) -> dict:
    """解析导入 Excel，返回 {success: [...], errors: [...]}"""
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        return {"success": [], "errors": [f"Excel 读取失败: {str(e)}"]}

    # 列名映射（容错）
    col_map = {}
    for i, h in enumerate(IMPORT_HEADERS):
        if h in df.columns:
            col_map[h] = h
        # 尝试模糊匹配
        for col in df.columns:
            if col.strip() == h or h in col:
                col_map[h] = col
                break

    successes = []
    errors = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel 行号（含表头）
        try:
            title = str(row.get(col_map.get("文件名称", ""), "")).strip()
            if not title or title == "nan":
                errors.append(f"第{row_num}行：文件名称不能为空")
                continue

            doc_no = str(row.get(col_map.get("文号", ""), "")).strip()
            if doc_no and doc_no != "nan":
                # 检查文号是否重复
                existing = db.get_document_by_no(doc_no)
                if existing:
                    errors.append(f"第{row_num}行：文号「{doc_no}」已存在（《{existing['title']}》），请检查")
                    continue

            # 校验文件状态
            status = str(row.get(col_map.get("文件状态", ""), "")).strip()
            if status and status != "nan" and status not in DOC_STATUS_OPTIONS:
                errors.append(f"第{row_num}行：文件状态「{status}」不在预设列表中")
                continue

            data = {
                "title": title,
                "document_no": doc_no if doc_no != "nan" else "",
                "issuing_authority": _safe_str(row, col_map, "发文单位"),
                "publish_date": _safe_str(row, col_map, "发布日期"),
                "effective_date": _safe_str(row, col_map, "实施日期"),
                "expiry_date": _safe_str(row, col_map, "失效日期"),
                "status": status if status != "nan" else "待核实",
                "region": _safe_str(row, col_map, "适用地区"),
                "category": _safe_str(row, col_map, "文件类别"),
                "keywords": _safe_str(row, col_map, "关键词"),
                "source_type": "批量导入",
                "source_url": _safe_str(row, col_map, "原文链接"),
                "notes": _safe_str(row, col_map, "备注"),
                "confirmed": 1,
            }
            doc_id = db.create_document(data)
            successes.append({"id": doc_id, "title": title})

            # 如果有替代文件/废止依据，后续可在此处理关系
            alt_file = _safe_str(row, col_map, "替代文件")
            abolish_basis = _safe_str(row, col_map, "废止依据")

        except Exception as e:
            errors.append(f"第{row_num}行：{str(e)}")

    return {"success": successes, "errors": errors}


def _safe_str(row, col_map: dict, key: str) -> str:
    """安全获取字符串值"""
    col = col_map.get(key, "")
    if not col or col not in row.index:
        return ""
    val = str(row[col]).strip()
    return "" if val == "nan" else val


def export_documents_to_excel(documents: list[dict]) -> bytes:
    """导出政策文件库为 Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "政策文件库"

    # 写表头
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col, h in enumerate(EXPORT_HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # 写数据
    field_map = {
        "ID": "id", "文件名称": "title", "文号": "document_no",
        "发文单位": "issuing_authority", "发布日期": "publish_date",
        "实施日期": "effective_date", "失效日期": "expiry_date",
        "文件状态": "status", "适用地区": "region", "文件类别": "category",
        "关键词": "keywords", "摘要": "summary",
        "来源类型": "source_type", "原文链接": "source_url",
        "是否确认": "confirmed", "备注": "notes",
        "创建时间": "created_at", "更新时间": "updated_at",
    }
    for r, doc in enumerate(documents, 2):
        for c, header in enumerate(EXPORT_HEADERS, 1):
            val = doc.get(field_map.get(header, ""), "")
            if header == "是否确认":
                val = "是" if val == 1 else "否"
            ws.cell(row=r, column=c, value=val)

    # 列宽
    for i in range(1, len(EXPORT_HEADERS) + 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = 16

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def export_relations_to_excel(relations: list[dict]) -> bytes:
    """导出传承关系为 Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "传承关系表"

    headers = [
        "ID", "旧文件", "旧文件文号", "关系类型", "新文件", "新文件文号",
        "关系依据", "关系日期", "影响范围", "确认程度", "备注",
    ]
    fields = [
        "id", "old_title", "old_document_no", "relation_type",
        "new_title", "new_document_no", "relation_basis", "relation_date",
        "affected_scope", "confidence", "notes",
    ]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill

    for r, rel in enumerate(relations, 2):
        for c, f in enumerate(fields, 1):
            ws.cell(row=r, column=c, value=rel.get(f, ""))

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def export_review_results_to_excel(results: list[dict]) -> bytes:
    """导出审查结果为 Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "审查结果"

    headers = [
        "序号", "原文引用", "文号", "匹配文件", "匹配方式", "匹配分数",
        "文件状态", "风险等级", "判断依据", "建议替换文件", "修改建议",
        "是否需要人工确认",
    ]
    fields = [
        None, "original_reference", "matched_document_no", "matched_title",
        "match_method", "match_score", "document_status", "risk_level",
        "judgment_basis", "suggested_title", "suggestion", "need_manual_confirm",
    ]

    # 表头样式
    header_font = Font(bold=True, color="FFFFFF")
    high_fill = PatternFill(start_color="FF6B6B", end_color="FF6B6B", fill_type="solid")
    mid_fill = PatternFill(start_color="FFD93D", end_color="FFD93D", fill_type="solid")
    low_fill = PatternFill(start_color="A8D8EA", end_color="A8D8EA", fill_type="solid")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill

    for r, res in enumerate(results, 2):
        for c, f in enumerate(fields, 1):
            if f is None:
                val = r - 1  # 序号
            elif f == "match_score":
                val = res.get(f, 0) or 0
            elif f == "need_manual_confirm":
                val = "是" if res.get(f, 0) else "否"
            else:
                val = res.get(f, "")
            cell = ws.cell(row=r, column=c, value=val)
            # 风险等级着色
            if c == 8:  # 风险等级列
                risk = str(val)
                if risk == "高风险":
                    cell.fill = high_fill
                elif risk == "中风险":
                    cell.fill = mid_fill

    # 列宽
    for i in range(1, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = 18

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()
