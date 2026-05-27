"""全局配置"""

import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据目录
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
REVIEW_DOCS_DIR = os.path.join(DATA_DIR, "review_docs")
DB_PATH = os.path.join(DATA_DIR, "policy_library.db")

# 确保目录存在
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(REVIEW_DOCS_DIR, exist_ok=True)

# 文件状态枚举
DOC_STATUS_OPTIONS = [
    "现行有效", "已废止", "已失效", "被替代",
    "部分废止", "即将失效", "待核实", "不明",
]

# 文件类别枚举
DOC_CATEGORY_OPTIONS = [
    "法律", "行政法规", "地方性法规", "地方政府规章",
    "部门规章", "规范性文件", "政策文件",
    "技术标准", "规范", "通知", "指南", "其他",
]

# 适用地区枚举
REGION_OPTIONS = ["全国", "省", "市", "县", "其他"]

# 来源类型枚举
SOURCE_TYPE_OPTIONS = ["上传", "手工录入", "批量导入", "网络检索"]

# 传承关系类型枚举
RELATION_TYPE_OPTIONS = [
    "废止", "替代", "修订", "部分废止",
    "部分替代", "延续", "上位依据变化", "不确定",
]

# 关系确认程度枚举
RELATION_CONFIDENCE_OPTIONS = ["人工确认", "AI推测", "待核实"]

# 匹配方式枚举
MATCH_METHODS = ["文号精确匹配", "标题精确匹配", "模糊匹配", "未匹配"]

# 风险等级枚举
RISK_LEVEL_OPTIONS = ["高风险", "中风险", "低风险", "提醒", "正常"]

# 状态→风险等级映射
STATUS_TO_RISK = {
    "现行有效": "正常",
    "已废止": "高风险",
    "已失效": "高风险",
    "被替代": "中风险",
    "部分废止": "中风险",
    "即将失效": "低风险",
    "待核实": "提醒",
    "不明": "提醒",
}

# 模糊匹配阈值
FUZZY_MATCH_HIGH = 95    # >= 95 视为高置信度匹配
FUZZY_MATCH_LOW = 85     # >= 85 视为疑似匹配，低于此值视为未匹配

# 支持上传的文件类型
UPLOAD_EXTENSIONS = [".docx", ".pdf", ".xlsx", ".txt"]

# 文号正则模式（按具体程度从高到低排列）
DOCUMENT_NO_PATTERNS = [
    r"[A-Za-z一-鿿、]+规字〔\d{4}〕\d+号",   # 粤自然资规字〔2024〕6号
    r"[A-Za-z一-鿿、]+发〔\d{4}〕\d+号",     # 自然资发〔2024〕204号
    r"[A-Za-z一-鿿、]+办发〔\d{4}〕\d+号",   # 自然资办发〔2024〕8号
    r"[A-Za-z一-鿿、]+函〔\d{4}〕\d+号",     # 自然资函〔2024〕12号
    r"[A-Za-z一-鿿、]+〔\d{4}〕\d+号",       # 其他带年份括号的文号
    r"[A-Za-z一-鿿、]+令第\d+号",             # 自然资源部、农业农村部令第17号
    r"[A-Za-z一-鿿]+公告\d{4}年第\d+号",     # 广东省人大常委会公告2022年第113号
    r"国务院令第\d+号",                      # 国务院令第743号
]
# 注意：移除了过于宽泛的 第\d+号 模式，避免误识别
