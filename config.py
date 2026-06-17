"""全局配置"""

import os

# 应用版本信息（用于首页/侧边栏展示，也用于上传解析缓存失效）
# 版本号以 version.py 为准，此处保留用于向后兼容
from version import APP_VERSION, APP_UPDATE_DATE, APP_UPDATE_SUMMARY
APP_RELEASE_DATE = APP_UPDATE_DATE
APP_VERSION_NOTE = APP_UPDATE_SUMMARY

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 品牌素材目录
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

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
SOURCE_TYPE_OPTIONS = ["上传", "手工录入", "批量导入", "公开网页导入"]

# 新旧关系类型枚举
RELATION_TYPE_OPTIONS = [
    "废止", "替代", "修订", "部分废止",
    "部分替代", "延续", "上位依据变化", "不确定",
]

# 关系确认程度枚举
RELATION_CONFIDENCE_OPTIONS = ["人工确认", "AI推测", "待核实"]

# 匹配方式枚举
MATCH_METHODS = ["文号精确匹配", "标题精确匹配", "标题内嵌匹配", "模糊匹配", "未匹配"]

# 风险等级枚举
RISK_LEVEL_OPTIONS = ["严重问题", "高风险", "中风险", "低风险", "提醒", "正常"]

# 常见文号前缀白名单（自然资源领域）
# 白名单只用于低风险格式提醒，不用于强制纠错
KNOWN_DOC_NO_PREFIXES = [
    "自然资发",
    "自然资规",
    "自然资办发",
    "自然资办函",
    "自然资函",
    "国土资发",
    "国土资规",
    "国土资厅发",
    "国土资厅函",
    "粤自然资发",
    "粤自然资规字",
    "粤自然资函",
    "粤自然资办函",
    "粤府",
    "粤府办",
    "粤府函",
    "清府",
    "清府办",
    "清自然资",
]

# 状态→风险等级映射
STATUS_TO_RISK = {
    "现行有效": "正常",
    "已废止": "严重问题",
    "已失效": "严重问题",
    "被替代": "高风险",
    "部分废止": "中风险",
    "即将失效": "低风险",
    "待核实": "提醒",
    "不明": "提醒",
}

# 安全配置
ENABLE_WEB_IMPORT = True       # 保留公开政策网页导入
ENABLE_WEB_SEARCH = False      # 禁止根据待审查文档自动联网搜索
ENABLE_EXTERNAL_AI = False     # 禁止外部 AI 分析真实文件
LOCAL_ONLY = True
SAVE_REVIEW_TEXT = False
SAVE_REVIEW_FILE = False

# 文件保存和下载配置
SAVE_POLICY_FILE = True
ALLOW_POLICY_DOWNLOAD = True
SAVE_REPORT_FILE = True
ALLOW_REPORT_DOWNLOAD = True
MAX_UPLOAD_SIZE_MB = 50
MAX_TOTAL_STORAGE_GB = 5

# 策略文件保存目录
POLICY_FILES_DIR = os.path.join(DATA_DIR, "uploads", "policy_files")
REVIEW_FILES_DIR = os.path.join(DATA_DIR, "uploads", "review_files")
REPORTS_DIR = os.path.join(DATA_DIR, "exports", "review_reports")
TEMP_DIR = os.path.join(DATA_DIR, "temp")

os.makedirs(POLICY_FILES_DIR, exist_ok=True)
os.makedirs(REVIEW_FILES_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# 模糊匹配阈值
FUZZY_MATCH_HIGH = 95    # >= 95 视为高置信度匹配
FUZZY_MATCH_LOW = 85     # >= 85 视为疑似匹配，低于此值视为未匹配

# 支持上传的文件类型
UPLOAD_EXTENSIONS = [".docx", ".pdf", ".xlsx", ".txt"]

# 文号正则模式（按具体程度从高到低排列）
# 括号支持：标准〔〕、半角()、全角（）、半角[]、全角【】
_B = r"[〔\(（\[\【]"   # 左括号
_E = r"[〕\)）\]\】]"   # 右括号
_Y = r"\d{4}"           # 年份

# 注意：部分模式在数字和"号"之间插入 \s* 以兼容PDF提取的空格（如"粤自然资规字〔2024〕1 号"）
DOCUMENT_NO_PATTERNS = [
    r"[A-Za-z一-鿿、]+规字" + _B + _Y + _E + r"\d+\s*号",   # 粤自然资规字〔2024〕6号
    r"[A-Za-z一-鿿、]+发" + _B + _Y + _E + r"\d+\s*号",     # 自然资发〔2024〕204号
    r"[A-Za-z一-鿿、]+办发" + _B + _Y + _E + r"\d+\s*号",   # 自然资办发〔2024〕8号
    r"[A-Za-z一-鿿、]+函" + _B + _Y + _E + r"\d+\s*号",     # 自然资函〔2024〕12号
    r"[A-Za-z一-鿿、]+" + _B + _Y + _E + r"\d+\s*号",       # 其他带年份括号的文号
    r"[A-Za-z一-鿿、]+令第\s*\d+\s*号",         # 自然资源部、农业农村部令第17号
    r"[A-Za-z一-鿿]+公告\d{4}年第\s*\d+\s*号", # 广东省人大常委会公告2022年第113号
    r"国务院令第\s*\d+\s*号",                   # 国务院令第743号
    # 技术标准编号：TD/T 1036—2013, GB/T 12345-2020, HJ 1234—2021, NY/T 1234-2021
    r"[A-Z]{2,}/[A-Z]+\s*\d{4}[—\-—]\d{4}",
    r"[A-Z]{2,}\s+\d{4}[—\-—]\d{4}",
    r"[A-Z]{2,}/[A-Z]+\s*\d{4}",
    r"GB/?T?\s*\d{4,}[.\-—]\d{4}",
]
# 注意：移除了过于宽泛的 第\d+号 模式，避免误识别

# 业务类型关键词字典
BUSINESS_TYPE_KEYWORDS = {
    "增减挂钩类": [
        "增减挂钩", "城乡建设用地增减挂钩", "节余指标", "拆旧复垦", "建新区", "拆旧区", "挂钩周转指标"
    ],
    "成片开发类": [
        "成片开发", "土地征收成片开发", "成片开发方案", "成片开发范围", "开发片区"
    ],
    "全域土地综合整治类": [
        "全域土地综合整治", "全域整治", "农用地整理", "建设用地整理", "乡村生态保护修复", "全域土地整治"
    ],
    "耕地保护类": [
        "耕地保护", "耕地保有量", "耕地占补平衡", "耕地进出平衡", "耕地恢复", "耕地质量", "耕地保护目标"
    ],
    "永久基本农田类": [
        "永久基本农田", "基本农田", "永久基本农田保护红线", "永久基本农田核实处置", "永久基本农田补划"
    ],
    "占补平衡类": [
        "占补平衡", "补充耕地", "垦造水田", "水田指标", "耕地储备指标", "补充耕地指标"
    ],
    "设施农用地类": [
        "设施农用地", "农业设施", "生产设施", "附属设施", "养殖设施", "种植设施"
    ],
    "临时用地类": [
        "临时用地", "临时使用土地", "复垦方案", "临时用地审批", "临时用地期限"
    ],
    "土地征收类": [
        "土地征收", "征收土地", "征地补偿", "征地程序", "征地公告", "征收农用地"
    ],
    "村庄规划类": [
        "村庄规划", "实用性村庄规划", "村庄建设边界", "乡村规划", "村庄分类"
    ],
    "国土空间规划类": [
        "国土空间规划", "三区三线", "城镇开发边界", "生态保护红线", "国土空间用途管制", "详细规划"
    ],
    "生态修复类": [
        "生态修复", "国土空间生态修复", "矿山修复", "山水林田湖草沙", "生态保护修复"
    ],
    "土地整治类": [
        "土地整治", "高标准农田", "垦造水田", "农用地整理", "土地开发整理", "提质改造"
    ],
    "用地报批类": [
        "建设用地报批", "农用地转用", "用地预审", "建设用地审批", "用地报件", "报批材料"
    ],
    "执法监察类": [
        "土地执法", "自然资源执法", "违法用地", "卫片执法", "执法监察", "违法图斑"
    ],
}

BUSINESS_TYPE_OPTIONS = list(BUSINESS_TYPE_KEYWORDS.keys())

# 文件重要级别选项
IMPORTANCE_LEVEL_OPTIONS = ["核心", "重要", "一般", "参考", "待评估"]
IMPORTANCE_LEVEL_DEFAULT = "一般"

# 敏感级别选项
SENSITIVITY_LEVEL_OPTIONS = ["公开", "内部", "敏感", "涉密禁止上传"]

# ═══════════════════════════════════════════
#  批量下载配置
# ═══════════════════════════════════════════
ALLOW_PUBLIC_DOWNLOAD = True
ALLOW_INTERNAL_DOWNLOAD = True
ALLOW_SENSITIVE_DOWNLOAD = False
BATCH_DOWNLOAD_DIR = os.path.join(DATA_DIR, "temp", "downloads")

os.makedirs(BATCH_DOWNLOAD_DIR, exist_ok=True)

# 本地文件夹批量导入默认路径
DEFAULT_LOCAL_IMPORT_DIR = r"D:\桌面\新政策文件"

# ═══════════════════════════════════════════
#  标题识别排除词和附件标记
# ═══════════════════════════════════════════

# 不得作为政策文件主标题的排除词（附件/材料清单/表格类）
ATTACHMENT_TITLE_EXCLUDE_WORDS = [
    "附件", "附表", "附录", "目录",
    "材料名称", "提交条件", "提供条件", "示范文本",
    "申请材料", "申报材料", "申请书",
    "授权委托", "法人证明", "身份证明",
    "勘测定界", "规划审核意见", "规划选址意见",
    "用地预审意见", "用地预审",
    "清单", "表格", "填报说明",
    "建设项目用地申请表",
]

# 附件/材料清单条目开头标记
ATTACHMENT_ITEM_PREFIXES = [
    "①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩",
    "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、",
    "（一）", "（二）", "（三）", "（四）", "（五）",
    "(一)", "(二)", "(三)", "(四)", "(五)",
    "1.", "2.", "3.", "4.", "5.",
    "附件1", "附件2", "附件3", "附件4", "附件5",
    "附表1", "附表2", "附表3",
    "附录1", "附录2", "附录3",
]

# 政策文件标题关键词（红头文件标题通常包含）
POLICY_TITLE_KEYWORDS = [
    "关于", "印发", "通知", "决定", "公告", "意见",
    "办法", "规定", "方案", "条例", "细则", "规范",
    "规程", "标准", "指南",
]

# 发文机关常见后缀
ISSUING_AUTHORITY_SUFFIXES = ["部", "厅", "局", "委", "办", "院", "署", "会"]

# ═══════════════════════════════════════════
#  废止/失效依据库配置
# ═══════════════════════════════════════════
ENABLE_POLICY_MONITOR = True
ENABLE_AUTO_UPDATE_LIBRARY = False  # 候选结果不能自动改正式库
POLICY_MONITOR_MODE = "manual"  # 第一版只做手动检查
POLICY_MONITOR_MAX_PAGES = 3
POLICY_MONITOR_MAX_ITEMS_PER_SOURCE = 50

OFFICIAL_POLICY_SOURCES = [
    {
        "source_name": "自然资源部-政策",
        "domain": "mnr.gov.cn",
        "url": "https://www.mnr.gov.cn/",
        "region": "全国",
        "parser_type": "mnr",
    },
    {
        "source_name": "广东省自然资源厅-政策法规",
        "domain": "nr.gd.gov.cn",
        "url": "https://nr.gd.gov.cn/",
        "region": "广东省",
        "parser_type": "gd_nr",
    },
]

# 自然资源部允许的子域名列表
MNR_ALLOWED_DOMAINS = [
    "mnr.gov.cn",
    "www.mnr.gov.cn",
    "f.mnr.gov.cn",
    "gk.mnr.gov.cn",
    "gi.mnr.gov.cn",
]

# 监测种子链接
POLICY_MONITOR_SEED_URLS = [
    "https://www.mnr.gov.cn/",
    "https://f.mnr.gov.cn/",
    "https://gk.mnr.gov.cn/",
    "https://gi.mnr.gov.cn/",
    "https://f.mnr.gov.cn/202606/t20260605_2931308.html",
]

# 监测关键词（增强版）
MONITOR_KEYWORDS = [
    "废止",
    "失效",
    "已废止",
    "已失效",
    "废止或者失效",
    "已废止或者失效",
    "已废止或者失效的规范性文件目录",
    "废止的部门规章",
    "部门规章的决定",
    "规范性文件目录",
    "不再执行",
    "停止执行",
    "同时废止",
    "予以废止",
    "有效期届满",
    "重新公布",
    "修订",
    "修改",
    "代替",
    "替代",
]

# 候选类型
MONITOR_CANDIDATE_TYPES = ["废止公告", "失效目录", "替代修订", "新政策", "其他"]

# 政策法规库关键词搜索配置
POLICY_MONITOR_KEYWORDS = [
    "废止", "失效", "已废止", "已失效",
    "废止或者失效", "规范性文件目录",
    "废止的部门规章", "部门规章的决定",
    "予以废止", "同时废止", "不再执行",
    "停止执行", "有效期届满", "修改", "修订", "代替", "替代"
]

# 自然资源部站内搜索 URL 模板
SEARCH_URL_TEMPLATE = "https://www.mnr.gov.cn/s?searchWord={keyword}&pageSize=20&pageNum=1"

# 测试链接列表
POLICY_MONITOR_TEST_URLS = [
    "https://f.mnr.gov.cn/202606/t20260605_2931308.html",
]

# 候选状态
MONITOR_CANDIDATE_STATUSES = [
    "待抓取", "已抓取待确认", "疑似废止", "疑似失效",
    "疑似替代", "疑似重复", "已确认入库", "已忽略", "抓取失败",
]

# ═══════════════════════════════════════════
#  v7.1.0 新增：监测时间范围配置
# ═══════════════════════════════════════════

# 监测时间范围选项
MONITOR_TIME_RANGE_OPTIONS = [
    "近一个月",
    "近半年",
    "近一年",
    "全量补录",
]

# 时间范围 → 内部搜索页数兼容转换
# 全量补录使用较多页数覆盖历史数据
TIME_RANGE_TO_PAGES = {
    "近一个月": 1,
    "近半年": 2,
    "近一年": 3,
    "全量补录": 5,
}

# 时间范围 → 天数（未来增量监测使用）
TIME_RANGE_TO_DAYS = {
    "近一个月": 30,
    "近半年": 182,
    "近一年": 365,
    "全量补录": 0,
}
