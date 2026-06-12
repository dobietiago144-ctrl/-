"""文件状态规范化工具 — 统一状态口径，消除非标准状态"""

from config import DOC_STATUS_OPTIONS

# 非标准 → 标准状态映射
_STATUS_MAP = {
    "编码有效": "现行有效",
    "有效": "现行有效",
    "现行": "现行有效",
    "正在执行": "现行有效",
    "待验证": "待核实",
    "待确认": "待核实",
    "待校验": "待核实",
    "过期": "已失效",
    "失效": "已失效",
    "已过期": "已失效",
    "废止": "已废止",
    "已废": "已废止",
    "替代": "被替代",
    "已替代": "被替代",
    "不明白": "待核实",
    "未知": "不明",
    "": "待核实",
}

STANDARD_STATUSES = set(DOC_STATUS_OPTIONS)


def normalize_document_status(status: str) -> str:
    """将非标准状态映射为标准状态。

    Args:
        status: 原始状态字符串

    Returns:
        标准状态字符串，默认返回 "待核实"
    """
    if not status:
        return "待核实"

    status = status.strip()

    # 已经是标准状态，直接返回
    if status in STANDARD_STATUSES:
        return status

    # 查映射表
    if status in _STATUS_MAP:
        return _STATUS_MAP[status]

    # 模糊匹配兜底
    for non_std, std in _STATUS_MAP.items():
        if non_std in status:
            return std

    return "待核实"


def get_migration_sql() -> list[str]:
    """返回清理历史非标准状态的 SQL 语句列表。"""
    return [
        "UPDATE documents SET status = '现行有效' WHERE status IN ('编码有效', '有效', '现行', '正在执行');",
        "UPDATE documents SET status = '待核实' WHERE status IN ('待验证', '待确认', '待校验', '不明白', '', NULL) OR status IS NULL;",
        "UPDATE documents SET status = '已失效' WHERE status IN ('过期', '失效', '已过期');",
        "UPDATE documents SET status = '已废止' WHERE status IN ('废止', '已废');",
        "UPDATE documents SET status = '被替代' WHERE status IN ('替代', '已替代');",
        "UPDATE documents SET status = '不明' WHERE status IN ('未知');",
        "UPDATE documents SET status = '待核实' WHERE status NOT IN ('现行有效','已废止','已失效','被替代','部分废止','即将失效','待核实','不明');",
    ]
