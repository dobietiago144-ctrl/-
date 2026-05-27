"""元数据提取：从政策文件文本开头快速提取标题、文号、日期等"""

import re
from config import DOCUMENT_NO_PATTERNS

MAX_SCAN_CHARS = 3000

# 已知的政府网站标签名
_META_LABELS = {"标题", "文号", "发文字号", "机构", "正文", "全部", "高级检索",
                "名称", "发布机构", "发文单位", "业务类型", "废止记录",
                "效力级别", "时效状态", "发布时间", "成文日期", "发布日期",
                "实施日期", "来源", "下载", "一", "来", "名", "称", "文", "号"}


def _extract_label_value(text: str, label: str, max_skip: int = 3) -> str | None:
    """查找标签后的值，支持标签分行和多行间隔。
    max_skip: 最多跳过的非值行数"""
    # 先处理合并后的文本
    merged = text
    for old, new in [("文\n号", "文号"), ("名\n称", "名称"), ("发\n布", "发布"),
                     ("机\n构", "机构"), ("日\n期", "日期"), ("效\n力", "效力"),
                     ("级\n别", "级别")]:
        merged = merged.replace(old, new)

    # 找到标签位置
    idx = merged.find(label)
    if idx < 0:
        return None

    # 取标签后几行的内容，逐行检查
    tail = merged[idx + len(label):idx + len(label) + 300]
    tail_lines = [l.strip() for l in tail.split("\n") if l.strip()]

    skipped = 0
    for line in tail_lines:
        if line in _META_LABELS or len(line) < 2:
            skipped += 1
            if skipped > max_skip:
                break
            continue
        # 找到了看起来是值的行
        return line
    return None


def classify_document(title: str, document_no: str, page_text: str = "") -> str:
    """根据文号、标题和页面元数据自动归类文件"""
    # 0. 页面"效力级别"最权威
    level = _extract_label_value(page_text, "效力级别", max_skip=4)
    if level:
        level_map = {
            "法律": "法律",
            "行政法规": "行政法规",
            "地方性法规": "地方性法规",
            "地方政府规章": "地方政府规章",
            "部门规章": "部门规章",
            "部门规范性文件": "规范性文件",
            "规范性文件": "规范性文件",
            "技术标准": "技术标准",
            "团体标准": "技术标准",
        }
        for k, v in level_map.items():
            if k in level:
                return v

    # 1. 文号模式
    if document_no:
        no = document_no
        if "主席令" in no:
            return "法律"
        if "国务院令" in no:
            return "行政法规"
        if re.search(r"(省|市|自治区).*人大常委会.*公告", no) or re.search(r"省.*第\d+号", no):
            return "地方性法规"
        if re.search(r"省(政府|人民)令", no):
            return "地方政府规章"
        if re.search(r"(部|厅|局|委|署)令第", no):
            return "部门规章"
        if re.search(r"[〔\(（]\d{4}[〕\)）]\d+号", no):
            # 发文字号：规字→可能是地方政府规章或规范性文件
            if "规字" in no:
                if re.search(r"(省|市|自治区)", title or ""):
                    return "规范性文件"  # 省级部门的规字文件通常为规范性文件
                return "规范性文件"
            if "发" in no or "办发" in no or "函" in no:
                return "规范性文件"
            return "规范性文件"
        if "GB/" in no or "GB " in no or "GB/T" in no:
            return "技术标准"

    # 2. 标题模式
    if title:
        if title.endswith("法") and "办法" not in title and "方法" not in title:
            return "法律"
        if title.endswith("条例") and "省" in title:
            return "地方性法规"
        if title.endswith("条例"):
            return "行政法规"
        if title.endswith("规定") or title.endswith("办法") or title.endswith("细则"):
            if "省" in title:
                return "规范性文件"
            return "部门规章"
        if "通知" in title:
            return "通知"
        if "标准" in title or "规范" in title or "通则" in title:
            return "技术标准"

    return "其他"


def extract_title(text: str) -> str:
    """提取文件标题"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return ""

    # 1. 从"名称"或"标题"标签取值
    for lbl in ["名称", "标题"]:
        val = _extract_label_value(text, lbl)
        if val and len(val) >= 8 and ("通知" in val or "办法" in val or "规定" in val or "关于" in val):
            return val[:120]

    # 2. "关于印发《...》" 格式（标题行特征：含"印发"+"书名号"）
    for line in lines:
        if re.search(r"关于印发[《〈].+?[》〉]", line):
            return line[:120]

    # 3. 独立短标题行（如"节约集约利用土地规定"）——优先于书名号匹配
    for line in lines:
        if 6 <= len(line) <= 50 and any(line.endswith(kw) for kw in
            ["规定", "办法", "条例", "规则", "标准", "细则", "方案", "法"]):
            if not any(s in line for s in ["下载", "http", "附件", "版权所有"]):
                return line[:120]

    # 4. 有书名号且看起来是标题的短行（排除正文长句）
    for line in lines:
        if re.search(r"[《〈].+?[》〉]", line) and 10 <= len(line) <= 100:
            if any(kw in line for kw in ["通知", "办法", "规定", "条例", "意见", "方案"]):
                return line[:120]

    # 5. 回退: 第一个书名号行（排除含"第X条"的正文行）
    for line in lines:
        m = re.search(r"[《〈](.+?)[》〉]", line)
        if m and len(m.group(1)) >= 3:
            if not re.search(r"第[一二三四五六七八九十\d]+条", line):
                return line[:120]

    return lines[0][:80]


def extract_document_no(text: str) -> str:
    """提取文号"""
    # 1. 从"文号"标签取
    val = _extract_label_value(text, "文号") or _extract_label_value(text, "发文字号")
    if val and re.search(r"[〔\(（]\d{4}[〕\)）]", val):
        m = re.search(r".*?([\w一-鿿]+[〔\(（]\d{4}[〕\)）]\d+号?)", val)
        if m:
            return m.group(1).strip()
        return val.strip()

    # 2. 全文正则
    for pattern in DOCUMENT_NO_PATTERNS:
        m = re.search(pattern, text)
        if m:
            no = m.group(0).strip()
            # 去掉前面的杂字符和前面的单个"日"字（常来自"X月X日"的尾巴）
            no = re.sub(r"^[^\w一-鿿〔\(（]+", "", no)
            no = re.sub(r"^日(?=[一-鿿]+(?:令|发|函|公告|[〔\(（]))", "", no)
            return no
    return ""


def extract_issuing_authority(text: str) -> str:
    """提取发文单位"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # 1. "发布机构" 标签取值
    val = _extract_label_value(text, "发布机构") or _extract_label_value(text, "发文单位")
    if val:
        # 尝试匹配机构名模式
        m = re.search(r"([一-鿿]{2,10}(?:部|厅|局|委|办|院|署))", val)
        if m:
            return m.group(1)
        if re.search(r"(部|厅|局|委|办|院|署|中心)$", val) and 2 <= len(val) <= 10:
            return val

    # 2. 在"发布机构"标签后几行内找机构名
    for lbl in ["发布机构", "发文单位"]:
        idx = text.find(lbl)
        if idx >= 0:
            tail = text[idx + len(lbl):idx + len(lbl) + 300]
            # 找最短的机构名（排除文档编号行和标题行）
            candidates = re.findall(r"\b([一-鿿]{2,8}(?:部|厅|局|委|办|院))\b", tail)
            for c in candidates:
                if c not in _META_LABELS and "规" not in c and "号" not in c:
                    return c

    # 3. 在全文头部找"印发"附近的机构名
    for m in re.finditer(r"([一-鿿]{2,8}(?:部|厅|局|委|办|院))", text[:800]):
        c = m.group(0)
        pos = m.start()
        ctx = text[max(0, pos - 40):pos + len(c) + 5]
        if "印发" in ctx or ("发布" in ctx and "发布日期" not in ctx):
            return c

    # 4. 取头部出现的第一个短机构名
    candidates = re.findall(r"\b([一-鿿]{2,8}(?:部|厅|局|委|办|院))\b", text[:800])
    for c in candidates:
        if c not in _META_LABELS and len(c) <= 6:
            return c

    # 5. 兜底：从页面分类行提取，如 "中华人民共和国自然资源部规章" → "自然资源部"
    first_line = text.split("\n")[0].strip()
    m = re.match(r"中华人民共和国(.{2,8}(?:部|厅|局|委|办|院))", first_line)
    if m:
        return m.group(1)
    m = re.search(r"([一-鿿]{2,8}(?:部|厅|局|委|办|院))(?:规章|法规|文件)", first_line)
    if m:
        return m.group(1)

    return ""


def extract_dates(text: str) -> dict:
    """提取日期信息"""
    result = {"publish_date": "", "effective_date": ""}

    # 1. 从标签取
    for lbl in ["发布日期", "发布时间", "成文日期"]:
        val = _extract_label_value(text, lbl)
        if val:
            m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", val)
            if m:
                y, mo, d = m.groups()
                result["publish_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                break

    for lbl in ["实施日期", "施行日期", "生效日期"]:
        val = _extract_label_value(text, lbl)
        if val:
            m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", val)
            if m:
                y, mo, d = m.groups()
                result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                break

    # 2. 全文日期列表
    dates = []
    for m in re.finditer(r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?", text[:MAX_SCAN_CHARS]):
        y, mo, d = m.groups()
        dates.append(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")
        if len(dates) >= 5:
            break

    if not result["publish_date"] and dates:
        result["publish_date"] = dates[0]
    if not result["effective_date"] and len(dates) > 1:
        result["effective_date"] = dates[1]

    # 3. "自...施行"句式覆盖
    m = re.search(r"自(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+(?:施行|实施|执行|生效)", text)
    if m:
        y, mo, d = m.groups()
        result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    return result


def _chinese_to_num(s: str) -> int:
    """中文数字转阿拉伯数字（支持'五'→5, '十'→10, '十二'→12 等）"""
    cn = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}
    s = s.strip()
    if s in cn:
        return cn[s]
    if len(s) == 2 and s[0] == "十":
        return 10 + cn.get(s[1], 0)
    if len(s) == 2 and s[1] == "十":
        return cn.get(s[0], 1) * 10
    if len(s) == 3 and s[1] == "十":
        return cn.get(s[0], 1) * 10 + cn.get(s[2], 0)
    return 0


def extract_expiry(text: str, dates: dict | None = None) -> str:
    """提取有效期/失效日期，支持从有效期年限推算具体日期"""
    # 1. 显式日期表达式
    m = re.search(r"(?:失效日期|有效期至|至)\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # 2. "有效期X年" → 根据发布日期/实施日期推算
    m = re.search(r"有效期\s*(?:为|是)?\s*(\d+|[一二三四五六七八九十]+)\s*年", text)
    if m:
        years_str = m.group(1)
        try:
            years = int(years_str)
        except ValueError:
            years = _chinese_to_num(years_str)
        if years > 0 and dates:
            base = dates.get("effective_date") or dates.get("publish_date") or ""
            if base and re.match(r"\d{4}-\d{2}-\d{2}", base):
                y, mo, d = int(base[:4]), int(base[5:7]), int(base[8:10])
                y += years
                return f"{y:04d}-{mo:02d}-{d:02d}"
        return f"有效期{years}年"

    # 3. "试行"类：试行期通常2-5年，无法精确推算则不填
    return ""


def infer_status(text: str, dates: dict, expiry_date: str) -> str:
    """根据日期逻辑和文本内容推断文件状态"""
    today = (2026, 5, 27)  # 当前日期

    # 0. 页面"时效状态"标签最权威（现行有效/已废止/已失效等）
    ts = _extract_label_value(text, "时效状态", max_skip=2)
    if ts:
        if "废止" in ts:
            return "已废止"
        if "失效" in ts:
            return "已失效"
        if "有效" in ts or "施行" in ts:
            return "现行有效"

    # 1. 有明确失效日期且已过期 → 已失效
    if expiry_date and re.match(r"\d{4}-\d{2}-\d{2}", expiry_date):
        y, mo, d = int(expiry_date[:4]), int(expiry_date[5:7]), int(expiry_date[8:10])
        if (y, mo, d) < today:
            return "已失效"

    # 2. 检查废止相关措辞（限制在同一行内匹配，且"自"后必须跟日期/发布/施行等，避免误匹配"自然资源部"等词）
    if re.search(r"(?:本办法?已(?:经)?废止|本规定已(?:经)?废止|予以废止|宣布废止|自(?:\d{4}|发布|施行|实施)[^，。\n]{0,200}?废止)", text[:2000]):
        return "已废止"

    # 3. 有发布日期或实施日期 → 现行有效
    if dates.get("publish_date") or dates.get("effective_date"):
        return "现行有效"

    return "待核实"


def extract_all_metadata(text: str) -> dict:
    """从文本开头快速提取所有元数据"""
    prefix = text[:MAX_SCAN_CHARS]
    dates = extract_dates(prefix)
    expiry = extract_expiry(prefix, dates)
    status = infer_status(prefix, dates, expiry)
    return {
        "title": extract_title(prefix),
        "document_no": extract_document_no(prefix) or None,
        "issuing_authority": extract_issuing_authority(prefix),
        "publish_date": dates.get("publish_date", ""),
        "effective_date": dates.get("effective_date", ""),
        "expiry_date": expiry,
        "status": status,
    }
