"""元数据提取：从政策文件文本开头快速提取标题、文号、日期等

重构要点：
1. 主标题识别优先级：红头文件首页标题 > 结构化字段 > 正文独立标题 > 文件名兜底
2. 附件标题/材料清单条目不得作为主标题
3. 文号识别与主标题绑定，优先首页红头文号
4. 发布日期 ≠ 现行有效，默认状态为"待核实"
5. 标题候选评分机制
"""

import re
from config import (
    DOCUMENT_NO_PATTERNS, ATTACHMENT_TITLE_EXCLUDE_WORDS,
    ATTACHMENT_ITEM_PREFIXES, POLICY_TITLE_KEYWORDS, ISSUING_AUTHORITY_SUFFIXES,
)

MAX_SCAN_CHARS = 3000
FRONT_PAGE_CHARS = 1500  # 前2页约1500字符

# 已知的政府网站标签名
_META_LABELS = {"标题", "文号", "发文字号", "机构", "正文", "全部", "高级检索",
                "名称", "发布机构", "发文单位", "业务类型", "废止记录",
                "效力级别", "时效状态", "发布时间", "成文日期", "发布日期",
                "实施日期", "来源", "下载", "一", "来", "名", "称", "文", "号"}


# 常见扫描/OCR异常字符修复（尤其是红头PDF文字层把“临”误抽为“｜｜乞/｜｜伤/｜｜伍”等）
def _fix_common_ocr_errors(text: str) -> str:
    """修复政策PDF文字层中的常见OCR/编码噪声。

    说明：很多扫描红头文件的文字层会把“临时用地”中的“临”识别为
    “｜｜乞”“｜｜伤”“｜｜伍”“｜｜由”“｜｜古”等，导致标题和正文关键词错乱。
    这里只做低风险替换：仅当异常符号后面紧跟“时用地/时使用/时建设”等短语时替换为“临”。
    """
    if not text:
        return ""

    fixed = text

    # 统一常见竖线变体，便于后续匹配；不直接删除，避免误伤表格。
    # 仅修复“临时...”相关短语。
    fixed = re.sub(r"[｜|丨]{1,4}\s*[乞伤伍由古仡屹]?(?=\s*时(?:用地|使用|建设|办公|生活|工棚|期限|审批|管理|信息|申请))", "临", fixed)
    fixed = re.sub(r"[｜|丨]{1,4}\s*(?=\s*时(?:用地|使用|建设|办公|生活|工棚|期限|审批|管理|信息|申请))", "临", fixed)

    # 常见错误组合直接替换。
    for bad in ["｜｜乞时", "｜｜伤时", "｜｜伍时", "｜｜由时", "｜｜古时", "||乞时", "||伤时", "||伍时", "||由时", "||古时"]:
        fixed = fixed.replace(bad, "临时")

    # OCR/排版造成的空格：临 时用地 → 临时用地。
    fixed = re.sub(r"临\s+时", "临时", fixed)

    # 标点轻度归一，便于标题判断。
    fixed = fixed.replace("°", "。").replace("｀", "、").replace("-、", "一、")
    return fixed


def _normalize_title_text(title: str) -> str:
    """对已提取标题做最终清洗。"""
    if not title:
        return ""
    title = _fix_common_ocr_errors(title)
    title = re.sub(r"\s+", "", title)
    title = title.strip(" ，。；;、：:《》〈〉\t\n")
    return title


def _normalize_filename_for_metadata(file_name: str | None) -> str:
    """清洗文件名中的括号/空格，供文号和到期日期兜底识别。"""
    if not file_name:
        return ""
    name = file_name
    name = name.replace("[", "〔").replace("]", "〕")
    name = re.sub(r"\s+", "", name)
    return name


def _extract_expiry_from_filename(file_name: str | None) -> str:
    """从文件名中提取“到期/失效”日期兜底。

    支持：2026.11到期、2026-11到期、2026年11月到期、2026.11.04到期。
    月份级日期只返回 YYYY-MM，避免伪造具体日。
    """
    name = _normalize_filename_for_metadata(file_name)
    if not name:
        return ""

    m = re.search(r"(\d{4})[.\-/年](\d{1,2})(?:[.\-/月](\d{1,2})日?)?\s*(?:到期|失效)", name)
    if not m:
        return ""
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if d:
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return f"{int(y):04d}-{int(mo):02d}"


def _looks_like_body_operation_date(text: str, start: int, end: int) -> bool:
    """判断日期是否只是正文里的业务节点日期，而非文件发布日期/施行日期。"""
    ctx = text[max(0, start - 80):min(len(text), end + 120)]
    # 典型："自2022年3月1日起，县（市）自然资源主管部门应当...传至临时用地信息系统完成系统配号"
    if re.search(r"信息系统|系统配号|上传|传至|填报|报送|批准后\s*\d+\s*个工作日", ctx):
        return True
    if re.search(r"应当|负责|督促|完成|更新", ctx) and not re.search(r"(本文件|本通知|本办法|自发布|自印发|自下发|施行|实施|执行|生效|印发|发布)", ctx):
        return True
    return False

def _clear_business_only_date(text: str, date_str: str, field: str) -> bool:
    """已抽出的日期二次校验：如果该日期只出现在业务节点句中，则清空。

    典型误判：正文“自2022年3月1日起，县（市）自然资源主管部门应当在临时用地批准后20个工作日内，
    将资料传至临时用地信息系统……”不是发布日期/实施日期。
    """
    if not date_str or not re.match(r"\d{4}-\d{2}-\d{2}$", date_str):
        return False
    y, mo, d = date_str.split("-")
    mo_i, d_i = str(int(mo)), str(int(d))
    patterns = [
        rf"{y}\s*年\s*{mo_i}\s*月\s*{d_i}\s*日",
        rf"{y}\s*[-/.]\s*0?{mo_i}\s*[-/.]\s*0?{d_i}",
    ]
    found_any = False
    has_release_context = False
    has_business_context = False
    for pat in patterns:
        for m in re.finditer(pat, text):
            found_any = True
            ctx = text[max(0, m.start() - 100):min(len(text), m.end() + 140)]
            if _looks_like_body_operation_date(text, m.start(), m.end()):
                has_business_context = True
            # 发布日期必须有明确落款/发布/印发/成文语境；实施日期必须有本文件/本通知级别的施行/实施语境。
            if field == "publish_date" and re.search(r"(成文日期|发布日期|发布时间|发文日期|印发|发布|下发|办公室|^[^\n]{0,20}(?:部|厅|局|委|办|院|署|会)\s*$)", ctx, re.M):
                # 排除“向社会公开/公开批准信息”这种业务公开语境。
                if not re.search(r"(信息系统|系统配号|批准后|传至|上传|填报|报送|向社会公开|公开临时用地批准信息)", ctx):
                    has_release_context = True
            if field == "effective_date" and re.search(r"(本文件|本通知|本办法|本规定|本条例).{0,30}(施行|实施|执行|生效)|自.{0,20}起.{0,20}(施行|实施|执行|生效)", ctx):
                if not re.search(r"(信息系统|系统配号|批准后|传至|上传|填报|报送)", ctx):
                    has_release_context = True
    # 找到了该日期，但只呈现业务节点语境，没有发布/施行语境 → 清空。
    return found_any and has_business_context and not has_release_context


def _extract_label_value(text: str, label: str, max_skip: int = 3) -> str | None:
    """查找标签后的值，支持标签分行和多行间隔。"""
    merged = text
    for old, new in [("文\n号", "文号"), ("名\n称", "名称"), ("发\n布", "发布"),
                     ("机\n构", "机构"), ("日\n期", "日期"), ("效\n力", "效力"),
                     ("级\n别", "级别")]:
        merged = merged.replace(old, new)

    idx = merged.find(label)
    if idx < 0:
        return None

    tail = merged[idx + len(label):idx + len(label) + 300]
    tail_lines = [l.strip() for l in tail.split("\n") if l.strip()]

    skipped = 0
    for line in tail_lines:
        if line in _META_LABELS or len(line) < 2:
            skipped += 1
            if skipped > max_skip:
                break
            continue
        return line
    return None


# ═══════════════════════════════════════════════════════════
#  附件/材料清单标题检测
# ═══════════════════════════════════════════════════════════

def is_attachment_or_form_title(line: str) -> bool:
    """判断一行文本是否为附件标题/材料清单条目/表格字段名。
    如果是，不能作为政策文件主标题。

    检测特征：
    1. 以"附件""附表""附录"开头
    2. 以编号前缀开头：①②③、一、、（一）、1.
    3. 内容包含材料清单/申请表特征词
    4. 出现在附件/材料相关关键词附近
    """
    if not line or not line.strip():
        return False

    line = line.strip()

    # 1. 以附件/附表/附录开头
    if re.match(r"^(附件|附表|附录|附件\d+|附表\d+|附录\d+)", line):
        return True

    # 2. 以材料相关词开头
    if re.match(r"^(材料名称|提交条件|提供条件|示范文本|申请材料|申报材料)", line):
        return True

    # 3. 以编号前缀开头
    for prefix in ATTACHMENT_ITEM_PREFIXES:
        if line.startswith(prefix):
            return True

    # 4. 仅包含书名号短条目（如单独的《……》），且内容类似附件条目
    m = re.match(r"^[《〈](.+?)[》〉]$", line)
    if m:
        inner = m.group(1)
        for word in ATTACHMENT_TITLE_EXCLUDE_WORDS:
            if word in inner:
                return True
        # 短条目且不包含政策文件关键词
        if len(inner) <= 40 and not any(kw in inner for kw in POLICY_TITLE_KEYWORDS):
            # 可能只是附件条目名
            return True

    # 5. 以申请书/登记表等结尾（表单类）
    if re.search(r"(申请书|登记表|审批表|申请表|报告表|备案表|意见书|证明书)$", line):
        return True

    return False


def _is_in_attachment_area(line_idx: int, total_lines: int, text: str) -> bool:
    """判断某行是否在附件/材料清单区域。
    检查该行附近是否有附件标记。
    """
    lines = text.split("\n")
    start = max(0, line_idx - 5)
    end = min(len(lines), line_idx + 5)
    nearby = "\n".join(lines[start:end])

    attachment_markers = [
        "附件", "附表", "材料清单", "申报材料", "申请材料",
        "附件目录", "材料名称", "提交条件",
    ]
    for marker in attachment_markers:
        if marker in nearby:
            return True
    return False


# ═══════════════════════════════════════════════════════════
#  多行标题合并（需求三：PDF红头标题跨行合并）
# ═══════════════════════════════════════════════════════════

def _compact_text(s: str) -> str:
    """用于定位的紧凑文本：去掉空白和常见版式符号差异。"""
    if not s:
        return ""
    s = re.sub(r"\s+", "", s)
    return s.replace("（", "(").replace("）", ")").replace("[", "〔").replace("]", "〕")


def _find_doc_no_line_idx(lines: list[str], primary_doc_no: str) -> int:
    """在保留断行的文本中定位主文号所在行，兼容 PDF 抽取出的空格。"""
    if not primary_doc_no:
        return -1
    target = _compact_text(primary_doc_no)
    for i, line in enumerate(lines):
        compact_line = _compact_text(line)
        if target and target in compact_line:
            return i
        # 兜底：有些正则清洗后会丢掉前缀，逐个文号标准化比对
        for no in _find_all_document_nos(line):
            if _compact_text(no) == target:
                return i
    return -1


def _is_recipient_line(line: str) -> bool:
    """收文对象行，例如“各地级以上市自然资源主管部门：”。"""
    return bool(re.match(r"^(各地|各市|各县|各区|各省|各有关|各设区|各镇|各有关单位|各直属|各部门).{0,40}[：:]?$", line.strip()))


def _looks_like_redhead_title(title: str) -> bool:
    """判断合并后的文本是否像政策文件主标题。"""
    if not title:
        return False
    title = title.strip(" ，。；;、：:《》〈〉\t\n")
    if not (8 <= len(title) <= 120):
        return False
    if is_attachment_or_form_title(title):
        return False
    # 正文句子、引用文件说明不能当主标题
    if re.match(r"^(为|根据|依据|按照|参照|遵照|落实|贯彻|现就|同时|对于|涉及)", title):
        return False
    if "。" in title or "；" in title or "，" in title:
        return False
    if re.match(r"^(一|二|三|四|五|六|七|八|九|十)[、.．]", title):
        return False
    if re.match(r"^（[一二三四五六七八九十]+）", title):
        return False
    # 主标题通常含“关于”，并以通知/意见/办法等收束；“严格规范”这类动宾片段不能单独算完整标题
    if "关于" in title and re.search(r"(通知|决定|公告|意见|办法|规定|方案|细则|条例|标准|批复|函)$", title):
        return True
    if re.search(r"(办法|规定|条例|细则|方案|标准|指南|规范)$", title) and "。" not in title:
        return True
    return False


def _merge_title_fragments(text: str, lines: list[str], primary_doc_no: str) -> list[dict]:
    """合并 PDF 中跨行的红头主标题。

    修复点：不能用 text.find(primary_doc_no) 定位，因为 PDF 常把“1号”抽成“1 号”。
    这里改为在逐行文本中做“去空格后的文号匹配”，然后只取“主文号之后、收文对象之前”
    的连续短行作为主标题候选，避免正文引用文件抢占标题。
    """
    if not primary_doc_no:
        return []

    no_line_idx = _find_doc_no_line_idx(lines, primary_doc_no)
    if no_line_idx < 0:
        return []

    results: list[dict] = []

    meta_label_pattern = re.compile(r"^(文号|发布机构|发布日期|实施日期|标题|名称|来源|全文|正文)$")
    doc_no_like = re.compile(r"[〔\(（]\s*\d{4}\s*[〕\)）]\s*\d+\s*号")

    # 1. 最可靠：主文号之后，到收文对象之前的连续标题区
    fragment_lines: list[str] = []
    for li in range(no_line_idx + 1, min(len(lines), no_line_idx + 8)):
        line = lines[li].strip()
        if not line:
            if fragment_lines:
                break
            continue
        if _is_recipient_line(line):
            break
        if meta_label_pattern.match(line):
            break
        if is_attachment_or_form_title(line) or re.match(r"^(附件|附表|附录)\d*", line):
            break
        if doc_no_like.search(line):
            break
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^(一|二|三|四|五|六|七|八|九|十)[、.．]", line):
            break
        if re.match(r"^（[一二三四五六七八九十]+）", line):
            break
        if len(line) > 70:
            break
        # 红头“广东省自然资源厅文件”通常在文号上方，不应进入文号后的标题区；若偶发进入也排除
        if re.match(r"^[一-鿿]{2,20}文件$", line):
            continue
        fragment_lines.append(line)

    # 按 1~4 行尝试合并，优先完整合并结果
    for end in range(min(4, len(fragment_lines)), 0, -1):
        merged = "".join(fragment_lines[:end]).strip()
        if _looks_like_redhead_title(merged):
            results.append({
                "title": merged[:120],
                "source": "首页红头（文号后跨行合并）",
                "score": 180 + end * 5,
                "reason": f"主文号后、收文对象前，由{end}行合并",
                "page_approx": 1,
                "is_main_title": True,
                "is_attachment": False,
            })
            break

    # 2. 兜底：有的 PDF 文号与标题顺序错乱，再查文号附近上下 6 行的连续窗口
    start = max(0, no_line_idx - 3)
    end = min(len(lines), no_line_idx + 7)
    nearby = []
    for li in range(start, end):
        line = lines[li].strip()
        if not line or _is_recipient_line(line) or doc_no_like.search(line):
            nearby.append("")
            continue
        if re.match(r"^[一-鿿]{2,20}文件$", line):
            nearby.append("")
            continue
        if is_attachment_or_form_title(line) or re.match(r"^(附件|附表|附录)\d*", line):
            nearby.append("")
            continue
        if len(line) > 70 or meta_label_pattern.match(line):
            nearby.append("")
            continue
        nearby.append(line)

    for i in range(len(nearby)):
        for j in range(min(len(nearby), i + 4), i, -1):
            parts = nearby[i:j]
            if not parts or any(not p for p in parts):
                continue
            merged = "".join(parts).strip()
            if _looks_like_redhead_title(merged) and not any(c["title"] == merged for c in results):
                results.append({
                    "title": merged[:120],
                    "source": "首页红头（文号附近合并）",
                    "score": 145 + len(parts) * 5,
                    "reason": f"主文号附近由{len(parts)}行合并",
                    "page_approx": 1,
                    "is_main_title": True,
                    "is_attachment": False,
                })
                break

    return results


# ═══════════════════════════════════════════════════════════
#  标题候选评分机制
# ═══════════════════════════════════════════════════════════

def extract_title_candidates(text: str, file_name: str = None) -> list[dict]:
    """提取标题候选列表，按得分排序。

    返回:
        [{title, source, score, reason, page_approx, is_main_title, is_attachment}]
    """
    if not text:
        return []

    # 先修复扫描PDF文字层中的常见OCR噪声，否则标题会出现“｜｜乞时用地”等乱码。
    text = _fix_common_ocr_errors(text)
    file_name_for_fallback = _normalize_filename_for_metadata(file_name) if file_name else file_name

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return []

    total_chars = len(text)
    candidates = []

    # 预处理：过滤解析提示行
    parse_hint_patterns = [
        "PDF共", "仅展示前", "仅显示前",
        "完整内容将在入库后存储", "完整内容将录入库后存储",
    ]

    def _is_front_area(idx: int) -> bool:
        """判断是否在前2页区域（约前1500字符）"""
        char_pos = sum(len(lines[i]) + 1 for i in range(min(idx, len(lines))))
        return char_pos < FRONT_PAGE_CHARS

    # ── 候选来源1：红头文件首页标题 ──
    for i, line in enumerate(lines):
        # 跳过解析提示
        if any(h in line for h in parse_hint_patterns):
            continue

        # 跳过附件/材料条目
        if is_attachment_or_form_title(line):
            continue

        # 包含"关于...印发《...》...通知"的完整标题行
        if re.search(r"关于.*印发[《〈].+?[》〉].*?(?:通知|决定|公告|意见)", line):
            score = 50  # 基础分：在前2页
            if _is_front_area(i):
                score += 40  # 包含"关于...通知"结构
            score += 30  # 靠近主文号（会在后续精算）
            if len(line) >= 15 and len(line) <= 120:
                score += 10

            candidates.append({
                "title": line[:120],
                "source": "首页红头",
                "score": score,
                "reason": "出现在首页，包含关于+印发+通知等关键词",
                "page_approx": 1 if _is_front_area(i) else 2,
                "is_main_title": True,
                "is_attachment": False,
            })

        # "XXX关于..." 格式（无书名号但含政策关键词）
        elif re.match(r"^[一-鿿]{2,12}(?:部|厅|局|委|办|院|署|会)?关于.+?(?:通知|决定|公告|意见|办法|规定)", line):
            if not is_attachment_or_form_title(line):
                score = 50 if _is_front_area(i) else 30
                score += 40  # 包含"关于...通知/决定"结构
                if len(line) >= 15 and len(line) <= 120:
                    score += 10

                candidates.append({
                    "title": line[:120],
                    "source": "首页红头",
                    "score": score,
                    "reason": "以发文机关+关于...格式开头",
                    "page_approx": 1 if _is_front_area(i) else 2,
                    "is_main_title": True,
                    "is_attachment": False,
                })

    # ── 候选来源2：结构化字段标题 ──
    for lbl in ["名称", "标题"]:
        val = _extract_label_value(text, lbl)
        if val and len(val) >= 8:
            if not is_attachment_or_form_title(val):
                if any(kw in val for kw in POLICY_TITLE_KEYWORDS):
                    candidates.append({
                        "title": val[:120],
                        "source": "结构化字段",
                        "score": 85,
                        "reason": f"从'{lbl}'标签提取，包含政策关键词",
                        "page_approx": 1,
                        "is_main_title": True,
                        "is_attachment": False,
                    })

    # ── 候选来源3：正文前部独立标题行 ──
    title_keywords = ["规定", "办法", "条例", "规则", "标准", "细则", "方案", "法",
                      "规范", "规程", "指南", "通知", "意见", "决定"]
    invalid_words = {"目录", "正文", "附件", "打印", "下载",
                     "封面", "扉页", "摘要", "索引", "参考文献", "版权"}

    for i, line in enumerate(lines):
        if any(h in line for h in parse_hint_patterns):
            continue
        if not (6 <= len(line) <= 120):
            continue
        if any(s in line for s in ["下载", "http", "版权所有", "ICS", "点击此处"]):
            continue
        if line in invalid_words:
            continue
        if is_attachment_or_form_title(line):
            continue
        if re.match(r"^[A-Z]{2,}[/\s]", line):
            continue

        # 已在候选1中处理过的红头格式跳过
        if re.search(r"关于.*印发[《〈].+?[》〉].*?(?:通知|决定|公告|意见)", line):
            continue
        if re.match(r"^[一-鿿]{2,12}(?:部|厅|局|委|办|院|署|会)?关于.+?(?:通知|决定|公告|意见|办法|规定)", line):
            continue

        # 以政策关键词结尾的标题行
        line_for_check = re.sub(r"[（(][^)）]*[)）]$", "", line)
        if any(line_for_check.endswith(kw) for kw in title_keywords):
            score = 50 if _is_front_area(i) else 30
            score += 20  # 政策关键词结尾
            if len(line) >= 10 and len(line) <= 80:
                score += 10

            # 扣分：在附件区域
            if _is_in_attachment_area(i, len(lines), text):
                score -= 60

            if score > 0:
                candidates.append({
                    "title": line[:120],
                    "source": "正文标题",
                    "score": score,
                    "reason": "政策关键词结尾的独立标题行",
                    "page_approx": 1 if _is_front_area(i) else 2,
                    "is_main_title": not _is_in_attachment_area(i, len(lines), text),
                    "is_attachment": _is_in_attachment_area(i, len(lines), text),
                })

    # ── 候选来源4：书名号内文本（扣除附件条目） ──
    for i, line in enumerate(lines):
        if any(h in line for h in parse_hint_patterns):
            continue
        if is_attachment_or_form_title(line):
            continue

        m = re.search(r"[《〈](.+?)[》〉]", line)
        if m:
            inner = m.group(1).strip()
            if 3 <= len(inner) <= 80:
                if not is_attachment_or_form_title(inner):
                    # 检查是否在附件区域
                    in_attachment = _is_in_attachment_area(i, len(lines), text)
                    is_main = not in_attachment and not is_attachment_or_form_title(inner)

                    score = 20
                    if _is_front_area(i):
                        score += 20
                    if any(kw in inner for kw in POLICY_TITLE_KEYWORDS):
                        score += 15
                    if in_attachment:
                        score -= 60
                    if len(inner) <= 15 and not any(kw in inner for kw in POLICY_TITLE_KEYWORDS):
                        score -= 50  # 短条目且无政策关键词

                    if score > 0:
                        candidates.append({
                            "title": inner[:120],
                            "source": "附件标题" if in_attachment or not is_main else "正文标题",
                            "score": score,
                            "reason": "从书名号中提取" + ("（附件区域）" if in_attachment else ""),
                            "page_approx": 1 if _is_front_area(i) else 2,
                            "is_main_title": is_main,
                            "is_attachment": in_attachment,
                        })

    # ── 候选来源5：文件名兜底（最低优先级） ──
    if file_name:
        clean_name = _clean_filename_for_title(file_name_for_fallback)
        if clean_name and len(clean_name) >= 4:
            candidates.append({
                "title": clean_name[:120],
                "source": "文件名兜底",
                "score": 15,
                "reason": "无法从正文识别标题，使用文件名",
                "page_approx": 0,
                "is_main_title": False,  # 文件名兜底不算主标题
                "is_attachment": False,
            })

    # ── 候选来源1.5：多行标题合并（需求三）──
    primary_no = _find_primary_doc_no(text, lines)
    merged_candidates = _merge_title_fragments(text, lines, primary_no)
    for mc in merged_candidates:
        # 去重：已存在相同标题的候选则跳过
        if not any(c["title"] == mc["title"] for c in candidates):
            candidates.append(mc)

    # ── 精算：靠近主文号加分 ──
    # 先从全文提取所有文号
    all_doc_nos = _find_all_document_nos(text)
    # primary_no 已在上面计算

    for cand in candidates:
        if primary_no and primary_no in text[:FRONT_PAGE_CHARS]:
            # 检查标题和文号是否相近（在前500字符内共同出现）
            title_pos = text.find(cand["title"])
            no_pos = text.find(primary_no)
            if title_pos >= 0 and no_pos >= 0 and abs(title_pos - no_pos) < 500:
                cand["score"] += 30
                cand["reason"] += "；靠近主文号"
            # 检查是否靠近发文单位
            authority = _find_front_authority(text[:FRONT_PAGE_CHARS])
            if authority and authority in text[max(0, title_pos - 200):title_pos + 200]:
                cand["score"] += 20
                cand["reason"] += "；靠近发文单位"

        # 需求三：多行合并标题优先于单行半截标题
        if cand.get("source") == "首页红头（多行合并）":
            cand["score"] += 20  # 完整合并标题加分
        elif cand.get("source") == "首页红头":
            # 如果存在多行合并候选，单行半截标题扣分
            if any(c.get("source") == "首页红头（多行合并）" for c in candidates):
                cand["score"] -= 10

        # 需求三：正文段落中带《》的引用文件标记为"引用文件"
        if cand.get("source") == "正文标题" and re.search(r"[《〈].+?[》〉]", cand.get("title", "")):
            title_in_text = cand["title"]
            pos_in_text = text.find(title_in_text)
            if pos_in_text >= 0:
                ctx = text[max(0, pos_in_text - 50):pos_in_text]
                if re.search(r"[。；，]", ctx):  # 前有正文标点，说明是段落中的引用
                    cand["is_main_title"] = False
                    cand["source"] = "引用文件"
                    cand["score"] -= 40

        # 需求三：第2页之后的标题若非结构化字段，不得作为主标题
        if cand.get("page_approx", 1) > 2:
            if cand.get("source") not in ("结构化字段", "文件名兜底"):
                cand["is_main_title"] = False
                cand["score"] -= 30

    # ── 最终清洗标题文本并去重 ──
    cleaned_candidates = []
    seen_titles = set()
    for cand in candidates:
        cand["title"] = _normalize_title_text(cand.get("title", ""))
        if not cand["title"]:
            continue
        # 清洗后如果仍含明显OCR残留，降权但不直接删除，便于人工兜底。
        if re.search(r"[｜|丨]{2,}|乞时|伤时|伍时|由时|古时", cand["title"]):
            cand["score"] -= 40
            cand["reason"] += "；疑似OCR残留"
        key = cand["title"]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        cleaned_candidates.append(cand)
    candidates = cleaned_candidates

    # ── 排序：得分降序，is_main_title 优先 ──
    candidates.sort(key=lambda x: (x["is_main_title"], x["score"]), reverse=True)
    return candidates


# ═══════════════════════════════════════════════════════════
#  标题提取（基于候选评分机制）
# ═══════════════════════════════════════════════════════════

def extract_title(text: str, file_name: str = None) -> str:
    """提取文件标题。使用候选评分机制，优先红头文件标题。"""
    candidates = extract_title_candidates(text, file_name)
    if not candidates:
        return ""

    # 取最高分且 is_main_title=True 的候选
    main_candidates = [c for c in candidates if c["is_main_title"]]
    if main_candidates:
        best = main_candidates[0]
        if best["score"] >= 50:
            return best["title"]
        # 得分低但仍是主标题候选，返回但后续应该标记
        return best["title"]

    # 次选：得分最高的非附件候选
    non_attachment = [c for c in candidates if not c["is_attachment"]]
    if non_attachment:
        return non_attachment[0]["title"]

    # 最后兜底
    return candidates[0]["title"] if candidates else ""


def extract_title_with_meta(text: str, file_name: str = None) -> dict:
    """提取标题并返回完整的候选信息。

    返回:
        {title, candidates, best_score, title_source, confidence, needs_manual_review}
    """
    candidates = extract_title_candidates(text, file_name)
    if not candidates:
        return {
            "title": "",
            "candidates": [],
            "best_score": 0,
            "title_source": "无",
            "confidence": "低",
            "needs_manual_review": True,
        }

    best = candidates[0]
    score = best["score"]
    is_main = best["is_main_title"]

    # 置信度判断
    if score >= 90 and is_main:
        confidence = "高"
        needs_review = False
    elif score >= 70:
        confidence = "中"
        needs_review = False
    else:
        confidence = "低"
        needs_review = True

    # 文件名兜底始终需要人工确认
    if best["source"] == "文件名兜底":
        confidence = "低"
        needs_review = True

    return {
        "title": best["title"],
        "candidates": candidates[:5],  # 最多返回5个候选
        "best_score": score,
        "title_source": best["source"],
        "confidence": confidence,
        "needs_manual_review": needs_review,
    }


# ═══════════════════════════════════════════════════════════
#  文号识别（绑定主标题）
# ═══════════════════════════════════════════════════════════

def _find_all_document_nos(text: str) -> list[str]:
    """从文本中找出所有符合文号格式的字符串。"""
    text_merged = re.sub(r"([A-Z]{2,}/[A-Z]*)\s*\n\s*(\d{4}[—\-]\d{4})", r"\1 \2", text)
    found = []
    seen = set()

    for pattern in DOCUMENT_NO_PATTERNS:
        for m in re.finditer(pattern, text_merged):
            no = m.group(0).strip()
            no = re.sub(r"^[^\w一-鿿〔\(（]+", "", no)
            no = re.sub(r"^日(?=[一-鿿]+(?:令|发|函|公告|[〔\(（]))", "", no)
            no = no.replace("\n", "").replace("\r", "")
            no = no.replace(" ", "").replace("　", "")  # 去除PDF提取引入的空格（半角/全角）
            # 去掉前面可能附带的引用上下文词
            for prefix_word in ["根据", "依据", "参照", "按照", "遵照", "落实", "详见", "参见"]:
                if no.startswith(prefix_word):
                    no = no[len(prefix_word):]
                    break
            if no and no not in seen:
                seen.add(no)
                found.append(no)

    return found


def _find_primary_doc_no(text: str, lines: list[str] = None) -> str:
    """找首页主文号（与发文机关和主标题位置最近的文号）。"""
    if lines is None:
        lines = [l.strip() for l in text.split("\n") if l.strip()]

    front_text = text[:FRONT_PAGE_CHARS]
    all_nos = _find_all_document_nos(front_text)
    if not all_nos:
        # 扩大到全文
        all_nos = _find_all_document_nos(text[:MAX_SCAN_CHARS])
    if not all_nos:
        return ""

    # 只有一个文号时直接返回
    if len(all_nos) == 1:
        return all_nos[0]

    # 多个文号时，选与发文机关/红头标题最近的
    authority = _find_front_authority(front_text)

    best_no = all_nos[0]
    best_score = 0

    for no in all_nos:
        score = 0
        pos = front_text.find(no)
        if pos < 0:
            pos = text.find(no)

        # 在前2页 +50
        if 0 <= pos < FRONT_PAGE_CHARS:
            score += 50

        # 在首页前部（发文机关附近）+30
        if authority and authority in front_text:
            auth_pos = front_text.find(authority)
            if auth_pos >= 0 and pos >= 0 and abs(pos - auth_pos) < 500:
                score += 30

        # 不与"根据""依据""参照"等引用词相邻 -20
        if pos >= 0:
            ctx_before = text[max(0, pos - 30):pos]
            if re.search(r"(根据|依据|参照|按照|遵照|落实)", ctx_before):
                score -= 20

        # 不在附件区域
        if "附件" in text[max(0, pos - 100):pos]:
            score -= 40

        if score > best_score:
            best_score = score
            best_no = no

    return best_no


def extract_primary_document_no(text: str, title_candidates: list[dict] = None) -> dict:
    """提取主文号，同时收集引用文号列表。

    返回:
        {primary_document_no, referenced_document_nos, source, score}
    """
    all_nos = _find_all_document_nos(text[:MAX_SCAN_CHARS])
    if not all_nos:
        return {
            "primary_document_no": "",
            "referenced_document_nos": [],
            "all_document_nos": [],
            "source": "无",
        }

    primary = _find_primary_doc_no(text)
    referenced = [n for n in all_nos if n != primary] if primary else all_nos

    # 判断来源
    if primary and primary in text[:FRONT_PAGE_CHARS]:
        source = "首页文号"
    elif primary:
        source = "正文文号"
    else:
        source = "未识别"

    return {
        "primary_document_no": primary,
        "referenced_document_nos": referenced,
        "all_document_nos": all_nos,
        "source": source,
    }


def extract_document_no(text: str) -> str:
    """提取文号（优先首页主文号）。"""
    result = extract_primary_document_no(text)
    return result["primary_document_no"]


# ═══════════════════════════════════════════════════════════
#  发文单位识别（优先首页红头）
# ═══════════════════════════════════════════════════════════

def _find_front_authority(text: str) -> str:
    """从首页文本中找到发文单位。"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return ""

    suffix_pattern = "|".join(ISSUING_AUTHORITY_SUFFIXES)
    authority_re = re.compile(rf"([一-鿿]{{2,12}}(?:{suffix_pattern}))")

    # 1. "XXX厅文件"/"XXX部文件" → 提取机关名
    for line in lines[:8]:
        m = re.match(r"^([一-鿿]{2,12}(?:部|厅|局|委|办|院|署|会))文件$", line)
        if m:
            return m.group(1)

    # 2. 首页前部独立的机构名行
    for line in lines[:10]:
        line = line.strip()
        # 排除收文对象行（"各地级以上市……"）
        if re.match(r"^(各地|各市|各县|各省|各有关|各设区)", line):
            continue
        m = authority_re.match(line)
        if m and len(line) <= 16:
            # 排除附件/引用中的机构名
            if not is_attachment_or_form_title(line):
                return m.group(1)

    # 3. 在首页文本中找"印发"/"发布"附近的机构名
    for m in authority_re.finditer(text[:FRONT_PAGE_CHARS]):
        c = m.group(0)
        pos = m.start()
        ctx = text[max(0, pos - 40):pos + len(c) + 10]
        if "印发" in ctx or "发布" in ctx or "文件" in ctx:
            # 排除收文对象
            before = text[max(0, pos - 20):pos]
            if not re.search(r"(各地|各市|各县|各省|收文)", before):
                return c

    return ""


def extract_issuing_authority(text: str) -> str:
    """提取发文单位。优先首页红头文件中的发文机关。"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # 1. 首页红头文件机构名
    authority = _find_front_authority(text[:FRONT_PAGE_CHARS])
    if authority:
        return authority

    # 2. "发布机构"/"发文单位"标签
    for lbl in ["发布机构", "发文单位"]:
        val = _extract_label_value(text, lbl)
        if val:
            m = re.search(rf"([一-鿿]{{2,10}}(?:{'|'.join(ISSUING_AUTHORITY_SUFFIXES)}))", val)
            if m:
                return m.group(1)
            if re.search(rf"({'|'.join(ISSUING_AUTHORITY_SUFFIXES)}|中心)$", val) and 2 <= len(val) <= 10:
                return val

    # 3. 标准文档格式：机构名独占一行，下一行是"发布"
    for i, line in enumerate(lines):
        if line == "发布" and i > 0:
            prev = lines[i - 1]
            prev_clean = prev.replace("中国人民共和国", "中华人民共和国")
            m = re.search(rf"([一-鿿]{{2,12}}(?:{'|'.join(ISSUING_AUTHORITY_SUFFIXES)}))", prev_clean)
            if m:
                return m.group(1)
            if 4 <= len(prev) <= 20:
                return prev

    # 4. 在全文头部找"印发"/"发布"附近的机构名
    suffix_pat = "|".join(ISSUING_AUTHORITY_SUFFIXES)
    for m in re.finditer(rf"([一-鿿]{{2,8}}(?:{suffix_pat}))", text[:800]):
        c = m.group(0)
        pos = m.start()
        ctx = text[max(0, pos - 40):pos + len(c) + 5]
        if ("印发" in ctx or "发布" in ctx) and not re.search(r"(各地|各市|各县|收文)", ctx[:40]):
            return c

    # 5. 取头部出现的第一个短机构名（排除收文对象）
    for m in re.finditer(rf"\b([一-鿿]{{2,8}}(?:{suffix_pat}))\b", text[:800]):
        c = m.group(0)
        if c not in _META_LABELS and len(c) <= 6:
            return c

    return ""


# ═══════════════════════════════════════════════════════════
#  日期识别（避免附件日期）
# ═══════════════════════════════════════════════════════════

def extract_dates(text: str) -> dict:
    """提取日期信息。优先首页落款日期和文号附近日期，避免附件/引用日期。"""
    text = _fix_common_ocr_errors(text)
    result = {"publish_date": "", "effective_date": ""}

    date_re = re.compile(r"(\d{4})\s*[年/\-.—―－—\-]\s*(\d{1,2})\s*[月/\-.—―－—\-]\s*(\d{1,2})\s*日?")

    # 仅扫描正文前部（避免附件区域日期）
    front_text = text[:FRONT_PAGE_CHARS]

    # 1. 从标签取（最可靠）
    for lbl in ["发布日期", "发布时间", "成文日期"]:
        val = _extract_label_value(front_text, lbl)
        if val:
            m = date_re.search(val)
            if m:
                y, mo, d = m.groups()
                result["publish_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                break

    for lbl in ["实施日期", "施行日期", "生效日期"]:
        val = _extract_label_value(front_text, lbl)
        if val:
            m = date_re.search(val)
            if m:
                y, mo, d = m.groups()
                result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                break

    # 2. "发布"行日期（仅在前部文本）
    if not result["publish_date"]:
        for m in re.finditer(r"(\d{4})\s*[年/\-.——\-]\s*(\d{1,2})\s*[月/\-.——\-]\s*(\d{1,2})\s*日?\s*(?:发布|印发)", front_text):
            if _looks_like_body_operation_date(front_text, m.start(), m.end()):
                continue
            y, mo, d = m.groups()
            result["publish_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            break

    # 3. "实施"行日期
    if not result["effective_date"]:
        for m in re.finditer(r"(\d{4})\s*[年/\-.——\-]\s*(\d{1,2})\s*[月/\-.——\-]\s*(\d{1,2})\s*日?\s*(?:实施|施行|执行|生效)", front_text):
            if _looks_like_body_operation_date(front_text, m.start(), m.end()):
                continue
            y, mo, d = m.groups()
            result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            break

    # 4. 前部日期列表（兜底，取第一个不被附件污染的日期）
    if not result["publish_date"] or not result["effective_date"]:
        publish_dates = []
        effective_dates = []
        for m in date_re.finditer(front_text):
            y, mo, d = m.groups()
            date_str = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            ctx_near = front_text[max(0, m.start() - 60):m.end() + 80]
            ctx_version = front_text[max(0, m.start() - 5):m.end() + 5]
            if re.search(r"(修订版|年版|版本|修正)", ctx_version):
                continue
            if _looks_like_body_operation_date(front_text, m.start(), m.end()):
                continue
            # 只有上下文明确指向发布日期/印发日期时，才作为发布日期兜底。
            # 另外兼容传统PDF：标题/文号后紧跟一行独立日期（通常位于首页前500字）。
            line_start = front_text.rfind("\n", 0, m.start()) + 1
            line_end = front_text.find("\n", m.end())
            if line_end < 0:
                line_end = len(front_text)
            date_line = front_text[line_start:line_end].strip()
            standalone_front_date = (m.start() < 500 and re.fullmatch(r"\d{4}\s*[年/\-.—―－—\-]\s*\d{1,2}\s*[月/\-.—―－—\-]\s*\d{1,2}\s*日?", date_line or ""))
            if re.search(r"(发布日期|发布时间|成文日期|印发|发布|下发|发文日期|办公室)", ctx_near) or standalone_front_date:
                publish_dates.append(date_str)
            # 只有明确指向施行/执行/生效时，才作为实施日期兜底。
            if re.search(r"(自.{0,12}起.{0,8}(?:施行|实施|执行|生效)|(?:施行|实施|执行|生效))", ctx_near):
                effective_dates.append(date_str)

        if not result["publish_date"] and publish_dates:
            result["publish_date"] = publish_dates[0]
        if not result["effective_date"] and effective_dates:
            result["effective_date"] = effective_dates[0]

    # 5. "自...施行"句式
    m = re.search(r"自\s*(\d{4})\s*[年/\-.——\-]\s*(\d{1,2})\s*[月/\-.——\-]\s*(\d{1,2})\s*日?\s*(?:起)?\s*(?:施行|实施|执行|生效)", front_text)
    if m and not _looks_like_body_operation_date(front_text, m.start(), m.end()):
        y, mo, d = m.groups()
        result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # 6. 文末日期扫描（需求四：部分PDF落款日期在最后一页）
    if not result["publish_date"] or not result["effective_date"]:
        tail_text = text[-1500:] if len(text) > FRONT_PAGE_CHARS + 500 else ""
        if tail_text:
            # 6a. 发文机关 + 日期格式（如 "广东省自然资源厅 2024年1月8日"）
            authority_date_re = re.compile(
                r"([一-鿿]{2,12}(?:部|厅|局|委|办|院|署|会))\s*"
                r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
            )
            for m_date in authority_date_re.finditer(tail_text):
                ctx_start = max(0, tail_text.rfind("\n", 0, m_date.start()))
                ctx_before = tail_text[ctx_start:m_date.start()]
                # 排除收文对象行
                if re.search(r"(各地|各市|各县|各省|收文)", ctx_before):
                    continue
                y, mo, d = m_date.group(2), m_date.group(3), m_date.group(4)
                if not result["publish_date"]:
                    result["publish_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                elif not result["effective_date"]:
                    result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                break

            # 6b. "办公室 ... 印发" 格式
            if not result["publish_date"]:
                m_pub = re.search(
                    r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(?:印发|发布)",
                    tail_text
                )
                if m_pub:
                    y, mo, d = m_pub.groups()
                    result["publish_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

            # 6c. 兜底：从 tail_text 取日期时必须有明确发布/印发/落款上下文。
            # 不再取“第一个日期”，避免把正文中的系统上线日期（如“自2022年3月1日起……”）误判为发布日期。
            if not result["publish_date"]:
                for m_date in date_re.finditer(tail_text):
                    y, mo, d = m_date.groups()
                    date_str = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                    ctx_near = tail_text[max(0, m_date.start() - 80):m_date.end() + 80]
                    if re.search(r"(修订版|年版|版本|修正|有效期)", ctx_near):
                        continue
                    if _looks_like_body_operation_date(tail_text, m_date.start(), m_date.end()):
                        continue
                    if not re.search(r"(印发|发布|下发|成文日期|发文日期|办公室|自然资源部\s*$)", ctx_near):
                        continue
                    result["publish_date"] = date_str
                    break

    # 7. 最终二次校验：清理正文业务节点日期误判
    for _field in ("publish_date", "effective_date"):
        if _clear_business_only_date(text, result.get(_field, ""), _field):
            result[_field] = ""

    return result


# ═══════════════════════════════════════════════════════════
#  过期日期提取
# ═══════════════════════════════════════════════════════════

def _chinese_to_num(s: str) -> int:
    """中文数字转阿拉伯数字。"""
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
    """提取有效期/失效日期。"""
    text = _fix_common_ocr_errors(text)
    # 1. 显式日期表达式
    m = re.search(r"(?:失效日期|有效期至|至)\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # 2. "有效期X年"推算
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

    # 3. "本通知自印发之日起执行，有效期五年" 等无明确日期的有效期表述
    m = re.search(r"自印发之日.*?起.*?(?:施行|执行|实施).*?有效期\s*(?:为|是)?\s*(\d+|[一二三四五六七八九十]+)\s*年", text)
    if m:
        years_str = m.group(1)
        try:
            years = int(years_str)
        except ValueError:
            years = _chinese_to_num(years_str)
        if years > 0:
            return f"有效期{years}年（自印发之日起）"

    return ""


# ═══════════════════════════════════════════════════════════
#  状态推断（关键修改：默认"待核实"）
# ═══════════════════════════════════════════════════════════

def infer_status(text: str, dates: dict, expiry_date: str) -> str:
    """根据日期逻辑和文本内容推断文件状态。

    重要变更：
    - 不再根据"有发布日期"自动判定为"现行有效"
    - 默认返回"待核实"
    - 仅在有明确证据（网页时效状态标签、明确废止措辞、已过期失效日期）时才判定具体状态
    """
    text = _fix_common_ocr_errors(text)
    today = (2026, 6, 8)  # 当前日期

    # 1. 页面"时效状态"标签最权威
    ts = _extract_label_value(text, "时效状态", max_skip=2)
    if ts:
        if "废止" in ts:
            return "已废止"
        if "失效" in ts:
            return "已失效"
        if "有效" in ts or "施行" in ts:
            return "现行有效"

    # 2. 有明确失效日期且已过期 → 已失效
    if expiry_date and re.match(r"\d{4}-\d{2}-\d{2}", expiry_date):
        y, mo, d = int(expiry_date[:4]), int(expiry_date[5:7]), int(expiry_date[8:10])
        if (y, mo, d) < today:
            return "已失效"

    # 3. 检查废止相关措辞
    if re.search(r"(?:本办法?已(?:经)?废止|本规定已(?:经)?废止|予以废止|宣布废止|自(?:\d{4}|发布|施行|实施)[^，。\n]{0,200}?废止)", text[:2000]):
        return "已废止"

    # 4. 【关键变更】默认返回"待核实"，不再因有日期就返回"现行有效"
    # 有发布日期≠现行有效
    return "待核实"


# ═══════════════════════════════════════════════════════════
#  综合提取
# ═══════════════════════════════════════════════════════════

def extract_all_metadata(text: str, file_name: str = None) -> dict:
    """从文本提取所有元数据。使用新的候选评分机制。"""
    text = _fix_common_ocr_errors(text or "")
    prefix = text[:MAX_SCAN_CHARS]
    dates = extract_dates(text)  # 传入全文，允许扫描文末日期（需求四）
    expiry = extract_expiry(text, dates)

    # 文件名中带“2026.11到期”等信息时，作为失效日期兜底；避免把正文中的系统上线日期误算成到期日。
    filename_expiry = _extract_expiry_from_filename(file_name)
    if filename_expiry:
        expiry = filename_expiry

    status = infer_status(prefix, dates, expiry)

    # 使用新的标题提取（带候选信息）
    title_meta = extract_title_with_meta(text, file_name)

    # 使用新的文号提取
    doc_no_result = extract_primary_document_no(text)
    if (not doc_no_result.get("primary_document_no")) and file_name:
        name_no = _find_primary_doc_no(_normalize_filename_for_metadata(file_name))
        if name_no:
            doc_no_result = {
                "primary_document_no": name_no,
                "referenced_document_nos": [],
                "all_document_nos": [name_no],
                "source": "文件名文号",
            }

    # 收集附件标题和引用文件
    attachment_titles = _extract_attachment_titles(text)
    notes_parts = []
    if attachment_titles:
        notes_parts.append("附件/材料条目：\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(attachment_titles, 1)))
    if doc_no_result.get("referenced_document_nos"):
        notes_parts.append("引用文号：\n" + "\n".join(doc_no_result["referenced_document_nos"]))

    return {
        "title": title_meta["title"],
        "document_no": doc_no_result.get("primary_document_no") or None,
        "issuing_authority": extract_issuing_authority(prefix),
        "publish_date": dates.get("publish_date", ""),
        "effective_date": dates.get("effective_date", ""),
        "expiry_date": expiry,
        "status": status,
        # 新增元数据字段
        "title_source": title_meta.get("title_source", ""),
        "title_confidence": title_meta.get("confidence", "低"),
        "title_score": title_meta.get("best_score", 0),
        "title_candidates": title_meta.get("candidates", []),
        "title_needs_review": title_meta.get("needs_manual_review", True),
        "document_no_source": doc_no_result.get("source", ""),
        "referenced_document_nos": doc_no_result.get("referenced_document_nos", []),
        "all_document_nos": doc_no_result.get("all_document_nos", []),
        "attachment_titles": attachment_titles,
        "notes_suggestion": "\n\n".join(notes_parts) if notes_parts else "",
    }


def _extract_attachment_titles(text: str) -> list[str]:
    """从正文中提取附件/材料清单条目标题（不作为主标题）。"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    attachments = []

    in_attachment_section = False
    for line in lines:
        # 检测是否进入附件区域
        if re.match(r"^(附件|附表|附录|附件\d+|附表\d+)", line):
            in_attachment_section = True
            # 同行可能有附件标题
            rest = re.sub(r"^(附件|附表|附录)\d*[：:\s]*", "", line).strip()
            if rest and len(rest) >= 4 and not rest.startswith("（"):
                attachments.append(rest)
            continue

        if re.search(r"(材料清单|附件目录|申报材料|申请材料)", line):
            in_attachment_section = True
            continue

        # 在附件区域内，编号开头的条目
        if in_attachment_section:
            if is_attachment_or_form_title(line):
                # 提取实际标题（去除编号前缀）
                clean = re.sub(r"^[①②③④⑤⑥⑦⑧⑨⑩\s]+", "", line)
                clean = re.sub(r"^[（(][一二三四五六七八九十\d]+[）)]\s*", "", clean)
                clean = re.sub(r"^\d+[.、]\s*", "", clean)
                if clean and len(clean) >= 4:
                    attachments.append(clean)
                continue

            # 书名号条目
            m = re.search(r"[《〈](.+?)[》〉]", line)
            if m:
                inner = m.group(1).strip()
                if is_attachment_or_form_title(inner) or len(inner) <= 50:
                    attachments.append(inner)

    return attachments


# ═══════════════════════════════════════════════════════════
#  文件名清洗（辅助）
# ═══════════════════════════════════════════════════════════

def _clean_filename_for_title(file_name: str) -> str:
    """从文件名清洗出可能的标题。"""
    if not file_name:
        return ""
    name = _fix_common_ocr_errors(file_name.strip())
    # 去扩展名
    name = re.sub(r"\.(pdf|docx?|xlsx?|txt|doc)$", "", name, flags=re.IGNORECASE)
    # 去日期编号
    name = re.sub(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?", "", name)
    name = re.sub(r"\d{8}", "", name)
    name = re.sub(r"[（(]\d{4}[）)]", "", name)
    # 去无意义词
    noise_words = ["扫描件", "附件", "最终版", "盖章版", "复制", "副本",
                   "定稿", "送审稿", "征求意见稿", "修改稿", "初稿",
                   "修订版", "新版", "旧版", "打印版", "电子版"]
    for w in noise_words:
        name = name.replace(w, "")
    name = re.sub(r"\s+", "", name)
    name = name.strip("_-—－ （）()[]【】《》")
    return name


# ═══════════════════════════════════════════════════════════
#  文件分类（保持不变）
# ═══════════════════════════════════════════════════════════

def classify_document(title: str, document_no: str, page_text: str = "") -> str:
    """根据文号、标题和页面元数据自动归类文件。"""
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
            if "规字" in no:
                return "规范性文件"
            if "发" in no or "办发" in no or "函" in no:
                return "规范性文件"
            return "规范性文件"
        if "GB/" in no or "GB " in no or "GB/T" in no:
            return "技术标准"

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
