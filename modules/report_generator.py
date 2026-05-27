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
        f"- 现行有效 {normal} 项；",
        f"- 已废止/已失效 {high} 项；",
        f"- 存在新版替代/部分废止 {medium} 项；",
        f"- 待人工核查/提醒 {remind} 项。",
    ]
    if high > 0 or medium > 0:
        lines.append("")
        lines.append("总体判断：该文档存在政策依据更新不及时问题，建议对高风险和中风险依据进行修改后再提交审查。")
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
