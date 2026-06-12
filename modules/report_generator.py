"""审查报告生成"""

from datetime import datetime
import database.db as db
from modules.excel_io import export_review_results_to_excel


def generate_review_summary(task_id: int) -> str:
    """生成审查摘要文字"""
    task = db.get_review_task(task_id)
    results = db.get_review_results(task_id)
    if not task:
        return "未找到审查任务"

    total = len(results)
    severe = sum(1 for r in results if r["risk_level"] == "严重问题")
    high = sum(1 for r in results if r["risk_level"] == "高风险")
    medium = sum(1 for r in results if r["risk_level"] == "中风险")
    low = sum(1 for r in results if r["risk_level"] == "低风险")
    normal = sum(1 for r in results if r["risk_level"] == "正常")
    remind = sum(1 for r in results if r["risk_level"] == "提醒")

    lines = [
        f"审查文档：{task.get('uploaded_file_name', '未命名')}",
        f"审查时间：{task.get('created_at', '')}",
        f"本次共识别引用依据 {total} 项。",
        f"其中：",
        f"- 现行有效/正常 {normal} 项；",
        f"- 严重问题（已废止/已失效/文号不一致）{severe} 项；",
        f"- 高风险（被替代且存在替代文件）{high} 项；",
        f"- 中风险（部分废止/待确认）{medium} 项；",
        f"- 低风险（即将失效/格式提醒）{low} 项；",
        f"- 提醒（未收录/模糊匹配）{remind} 项。",
    ]
    if severe > 0 or high > 0:
        lines.append("")
        lines.append("总体判断：该文档存在严重或高风险政策依据问题，必须修改后再提交审查。")
    elif medium > 0:
        lines.append("")
        lines.append("总体判断：该文档存在部分政策依据需要更新，建议修改后再提交审查。")
    else:
        lines.append("")
        lines.append("总体判断：该文档引用的政策依据基本现行有效。")

    return "\n".join(lines)


def export_report(task_id: int, report_type: str = "xlsx") -> bytes:
    """导出审查报告"""
    if report_type == "xlsx":
        results = db.get_review_results(task_id)
        return export_review_results_to_excel(results)
    raise ValueError(f"不支持的导出格式: {report_type}")
