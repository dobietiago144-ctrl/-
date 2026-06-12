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
#  标题候选评分机制
# ═══════════════════════════════════════════════════════════

def extract_title_candidates(text: str, file_name: str = None) -> list[dict]:
    """提取标题候选列表，按得分排序。

    返回:
        [{title, source, score, reason, page_approx, is_main_title, is_attachment}]
    """
    if not text:
        return []

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
        clean_name = _clean_filename_for_title(file_name)
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

    # ── 精算：靠近主文号加分 ──
    # 先从全文提取所有文号
    all_doc_nos = _find_all_document_nos(text)
    primary_no = _find_primary_doc_no(text, lines)

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
        for m in re.finditer(r"(\d{4})\s*[年/\-.——\-]\s*(\d{1,2})\s*[月/\-.——\-]\s*(\d{1,2})\s*日?\s*(?:发布|施行|实施)", front_text):
            y, mo, d = m.groups()
            result["publish_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            break

    # 3. "实施"行日期
    if not result["effective_date"]:
        for m in re.finditer(r"(\d{4})\s*[年/\-.——\-]\s*(\d{1,2})\s*[月/\-.——\-]\s*(\d{1,2})\s*日?\s*(?:实施|施行|执行|生效)", front_text):
            y, mo, d = m.groups()
            result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            break

    # 4. 前部日期列表（兜底，取第一个不被附件污染的日期）
    if not result["publish_date"] or not result["effective_date"]:
        dates = []
        for m in date_re.finditer(front_text):
            y, mo, d = m.groups()
            date_str = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            # 排除标题中紧邻的版本年份（如"2018年修订版"紧挨着日期时跳过）
            ctx_near = front_text[max(0, m.start() - 5):m.end() + 5]
            if re.search(r"(修订版|年版|版本|修正)", ctx_near):
                continue
            dates.append(date_str)
            if len(dates) >= 5:
                break

        if not result["publish_date"] and dates:
            result["publish_date"] = dates[0]
        if not result["effective_date"] and len(dates) > 1:
            result["effective_date"] = dates[1]

    # 5. "自...施行"句式
    m = re.search(r"自\s*(\d{4})\s*[年/\-.——\-]\s*(\d{1,2})\s*[月/\-.——\-]\s*(\d{1,2})\s*日?\s*(?:施行|实施|执行|生效)", front_text)
    if m:
        y, mo, d = m.groups()
        result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

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
    prefix = text[:MAX_SCAN_CHARS]
    dates = extract_dates(prefix)
    expiry = extract_expiry(prefix, dates)
    status = infer_status(prefix, dates, expiry)

    # 使用新的标题提取（带候选信息）
    title_meta = extract_title_with_meta(text, file_name)

    # 使用新的文号提取
    doc_no_result = extract_primary_document_no(text)

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
    name = file_name.strip()
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
