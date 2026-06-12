"""文档解析：从 Word/PDF/TXT/Excel/URL 中提取文本"""

import os
import re
import tempfile
from docx import Document
import requests


def decode_response_content(response) -> str:
    """稳定解码网页内容，解决中文政府网站乱码问题。

    优先级：
    1. HTTP header Content-Type 中的 charset
    2. HTML meta charset
    3. requests apparent_encoding
    4. 自动尝试 utf-8、gb18030、gbk
    5. 中文乱码检测 + 换编码重试

    Returns:
        解码后的 HTML 文本
    """
    content = response.content  # 原始 bytes

    if not content:
        return ""

    # 中文字符比例检测
    charset_quality = {}
    encodings_to_try = []

    # 1. 从 HTTP header Content-Type 识别 charset
    content_type = response.headers.get("Content-Type", "")
    ct_match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
    if ct_match:
        enc = ct_match.group(1).lower().strip().strip('"').strip("'")
        m = {"gb2312": "gb18030", "gbk": "gb18030"}
        encodings_to_try.append(m.get(enc, enc))

    # 2. 尝试从 HTML meta 中识别（先快速解码头部）
    try:
        head_sample = content[:2048].decode("utf-8", errors="replace")
        meta_match = re.search(
            r'<meta[^>]+charset=["\']?([^"\'\s;>]+)',
            head_sample, re.IGNORECASE
        )
        if meta_match:
            enc = meta_match.group(1).lower().strip()
            m = {"gb2312": "gb18030", "gbk": "gb18030"}
            encodings_to_try.append(m.get(enc, enc))
    except Exception:
        pass

    # 3. requests apparent_encoding
    try:
        apparent = response.apparent_encoding
        if apparent:
            apparent = apparent.lower()
            m = {"gb2312": "gb18030", "gbk": "gb18030"}
            encodings_to_try.append(m.get(apparent, apparent))
    except Exception:
        pass

    # 4. 默认编码尝试
    encodings_to_try.extend(["utf-8", "gb18030", "gbk"])

    # 去重但保持顺序
    seen = set()
    candidate_encodings = []
    for enc in encodings_to_try:
        if enc and enc not in seen:
            seen.add(enc)
            candidate_encodings.append(enc)

    best_html = ""
    best_score = -1

    for encoding in candidate_encodings:
        try:
            decoded = content.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            try:
                decoded = content.decode(encoding, errors="replace")
            except Exception:
                continue

        # 评分
        score = _evaluate_chinese_quality(decoded)
        if score > best_score:
            best_score = score
            best_html = decoded
            if score >= 90:
                return best_html

    if best_html:
        return best_html

    return content.decode("utf-8", errors="replace")


def _evaluate_chinese_quality(text: str) -> int:
    """评估文本中文质量，返回 0-100 分。"""
    if not text:
        return 0

    total = len(text)
    chinese_chars = len(re.findall(r"[一-鿿]", text))
    replacement_chars = text.count("�")
    # 西欧乱码字符：高ASCII单字节的连续出现
    mojibake_pattern = re.findall(r"[èæåäöüéêëîïôœ]{2,}", text)
    mojibake_chars = sum(len(m) for m in mojibake_pattern)

    # 乱码检测
    if total > 0 and replacement_chars > total * 0.1:
        return 5
    if total > 0 and mojibake_chars > total * 0.05:
        return 10

    # 中文字符比例
    chinese_ratio = chinese_chars / max(total, 1)
    if chinese_ratio > 0.15:
        return 95
    elif chinese_ratio > 0.05:
        return 75
    elif chinese_ratio > 0.01:
        return 50

    # 短文本且没有乱码标记 → 给高分
    if total < 50 and replacement_chars == 0 and mojibake_chars == 0:
        return 90

    if replacement_chars == 0 and mojibake_chars == 0:
        return 70
    return 30


def parse_docx(file_path: str) -> str:
    """解析 Word .docx 文件"""
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    paragraphs.append(cell.text.strip())
    return "\n".join(paragraphs)


def parse_pdf(file_path: str, max_pages: int = 0, use_blocks: bool = True) -> str:
    """解析 PDF 文件。max_pages=0 表示全部页面。

    参数:
        use_blocks: True 时使用 PyMuPDF blocks 模式提取，按 y/x 坐标排序，
                    保持首页红头文件文字顺序。False 时使用简单 page.get_text()。
    返回纯文本，不包含解析提示。"""
    import fitz  # PyMuPDF
    doc = fitz.open(file_path)
    pages = []
    for i, page in enumerate(doc):
        if max_pages > 0 and i >= max_pages:
            break

        if use_blocks:
            # blocks 模式：按 y、x 坐标排序，保持阅读顺序
            blocks = page.get_text("blocks")
            # 排序：先按 y 坐标（上→下），同 y 按 x 坐标（左→右）
            blocks_sorted = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))
            page_text = "\n".join(b[4].strip() for b in blocks_sorted if b[4].strip())
        else:
            page_text = page.get_text()

        if page_text.strip():
            pages.append(page_text.strip())

    total = doc.page_count
    doc.close()
    return "\n".join(pages)


def parse_file_with_structure(file_path: str, pdf_max_pages: int = 0) -> dict:
    """结构化解析文件，供批量导入和元数据识别使用。

    返回:
        {
            "file_type": ".pdf / .docx / .txt / .xlsx",
            "front_text": "前几页/前部文本，用于识别标题、文号、发文单位",
            "full_text": "全文文本",
            "pages": [{"page": 1, "text": "..."}, ...],
            "total_pages": int,
            "parse_warning": str,
            "parse_info": {"parser": "fitz/docx/txt/xlsx", "ext": str},
        }
    """
    import os
    import fitz

    ext = os.path.splitext(file_path)[1].lower()
    result = {
        "file_type": ext,
        "front_text": "",
        "full_text": "",
        "pages": [],
        "total_pages": 0,
        "parse_warning": "",
        "parse_info": {"parser": "", "ext": ext},
    }

    if ext == ".pdf":
        result["parse_info"]["parser"] = "fitz"
        doc = fitz.open(file_path)
        total = doc.page_count
        result["total_pages"] = total
        max_p = pdf_max_pages if pdf_max_pages > 0 else total
        parsed = min(total, max_p)

        if max_p > 0 and total > max_p:
            result["parse_warning"] = f"PDF共{total}页，仅展示前{max_p}页概要，完整内容将在入库后存储"
        result["parse_info"]["total_pages"] = total
        result["parse_info"]["parsed_pages"] = parsed

        all_page_texts = []
        front_texts = []
        for i, page in enumerate(doc):
            if i >= max_p:
                break
            blocks = page.get_text("blocks")
            blocks_sorted = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))
            page_text = "\n".join(b[4].strip() for b in blocks_sorted if b[4].strip())

            result["pages"].append({"page": i + 1, "text": page_text})
            all_page_texts.append(page_text)
            if i < 2:  # 前2页用于元数据识别
                front_texts.append(page_text)
        doc.close()

        result["full_text"] = "\n".join(all_page_texts)
        result["front_text"] = "\n".join(front_texts)

    elif ext == ".docx":
        result["parse_info"]["parser"] = "docx"
        full = parse_docx(file_path)
        result["full_text"] = full
        result["total_pages"] = 1
        result["parse_info"]["char_count"] = len(full)
        # 取前 5000 字符作为 front_text，用于元数据识别
        result["front_text"] = full[:5000]
        result["pages"] = [{"page": 1, "text": full}]

    elif ext == ".txt":
        result["parse_info"]["parser"] = "txt"
        full = parse_txt(file_path)
        result["full_text"] = full
        result["total_pages"] = 1
        result["parse_info"]["char_count"] = len(full)
        result["front_text"] = full[:5000]
        result["pages"] = [{"page": 1, "text": full}]

    elif ext in (".xlsx", ".xls"):
        result["parse_info"]["parser"] = "xlsx"
        full = parse_excel(file_path)
        result["full_text"] = full
        result["total_pages"] = 1
        result["parse_info"]["char_count"] = len(full)
        result["front_text"] = full[:5000]
        result["pages"] = [{"page": 1, "text": full}]

    elif ext == ".doc":
        raise ValueError(
            f"不支持 .doc 格式: {os.path.basename(file_path)}。"
            f"请使用 Word 将文件另存为 .docx 格式后再上传。"
        )

    else:
        raise ValueError(
            f"不支持的文件类型 '{ext}': {os.path.basename(file_path)}。"
            f"支持的格式: .pdf, .docx, .txt, .xlsx, .xls"
        )

    return result


def get_pdf_page_info(file_path: str, max_pages: int = 0) -> dict:
    """获取 PDF 页数信息，不解析内容。
    返回 {"total_pages": int, "parsed_pages": int, "parse_warning": str}
    """
    import fitz
    doc = fitz.open(file_path)
    total = doc.page_count
    doc.close()
    parsed = min(total, max_pages) if max_pages > 0 else total
    warning = ""
    if max_pages > 0 and total > max_pages:
        warning = f"PDF共{total}页，仅展示前{max_pages}页概要，完整内容将在入库后存储"
    return {"total_pages": total, "parsed_pages": parsed, "parse_warning": warning}


def parse_txt(file_path: str) -> str:
    """解析 TXT 文件，自动尝试常见编码"""
    for encoding in ["utf-8", "gbk", "gb2312", "utf-16", "latin-1"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_excel(file_path: str) -> str:
    """解析 Excel 文件（.xlsx / .xls），将所有单元格内容拼接为文本"""
    import pandas as pd
    xls = pd.ExcelFile(file_path)
    parts = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        for _, row in df.iterrows():
            line = " ".join([str(v) for v in row if pd.notna(v)])
            if line.strip():
                parts.append(line.strip())
    return "\n".join(parts)


def parse_file(file_path: str, pdf_max_pages: int = 0) -> str:
    """根据扩展名自动选择合适的解析器。
    pdf_max_pages: PDF 文件最多解析页数，0=全部（上传预览时建议 15）"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".doc":
        raise ValueError("不支持 .doc 格式，请转换为 .docx 后上传")
    elif ext == ".docx":
        return parse_docx(file_path)
    elif ext == ".pdf":
        return parse_pdf(file_path, max_pages=pdf_max_pages)
    elif ext == ".txt":
        return parse_txt(file_path)
    elif ext in (".xlsx", ".xls"):
        return parse_excel(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {ext}")


def get_supported_types() -> list[str]:
    """返回支持的文件扩展名列表（用于 file_uploader）。不支持 .doc，仅支持 .docx"""
    return ["docx", "pdf", "txt", "xlsx", "xls"]


def _is_safe_url(url: str) -> tuple[bool, str]:
    """检查 URL 是否安全可访问。
    返回 (is_safe, error_message)
    """
    from urllib.parse import urlparse
    import ipaddress

    parsed = urlparse(url)

    # 1. 只允许 http 和 https
    if parsed.scheme not in ("http", "https"):
        return False, "仅支持 http/https 链接，不支持 file://、ftp:// 等协议"

    hostname = (parsed.hostname or "").lower()

    # 2. 必须有有效主机名
    if not hostname:
        return False, "无法识别链接中的主机名"

    # 3. 禁止 localhost / 127.0.0.1 / 0.0.0.0
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
        return False, "禁止访问本地地址"

    # 4. 禁止 ::1 (IPv6 localhost)
    if hostname == "::1":
        return False, "禁止访问本地地址"

    # 5. 检查是否为内网 IP
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private:
            return False, "禁止访问内网地址"
        if ip.is_loopback:
            return False, "禁止访问本地回环地址"
        if ip.is_link_local:
            return False, "禁止访问链路本地地址 (169.254.x.x)"
    except ValueError:
        # 不是 IP 地址，检查是否为内网域名（通过解析后检查）
        pass

    return True, ""


def _extract_title_from_webpage(soup, html_text: str = "") -> str:
    """从网页中按优先级提取标题：
    1. 正文区域 h1/h2/h3
    2. meta og:title
    3. html title（去掉网站后缀）
    4. 正文第一行兜底
    """
    # 1. 正文区域标题
    for container in soup.find_all(["main", "article"]) or [soup]:
        for tag_name in ("h1", "h2", "h3"):
            h = container.find(tag_name)
            if h:
                t = h.get_text(strip=True)
                if t and 4 <= len(t) <= 200 and not t.startswith("<"):
                    # 排除明显的导航/非标题文本
                    skip_patterns = ["首页", "导航", "当前位置", "返回", "搜索", "打印", "字体"]
                    if not any(sp in t for sp in skip_patterns):
                        return t

    # 2. meta og:title
    og = soup.find("meta", property="og:title")
    if og and og.get("content", "").strip():
        return og["content"].strip()

    # 3. html title，去掉网站后缀
    title_tag = soup.find("title")
    if title_tag:
        raw = title_tag.get_text(strip=True)
        # 去掉常见后缀分隔符后的内容
        for sep in ["_", " - ", "—", "｜", "|", "–"]:
            if sep in raw:
                parts = raw.split(sep, 1)
                candidate = parts[0].strip()
                if 4 <= len(candidate) <= 200:
                    return candidate
        if 4 <= len(raw) <= 200:
            return raw

    # 4. 正文第一行兜底
    if html_text:
        lines = [l.strip() for l in html_text.splitlines() if l.strip()]
        for line in lines:
            if len(line) >= 4 and not line.startswith("（"):
                return line[:200]

    return ""


def _extract_revision_history(text: str) -> str:
    """识别正文开头的文件沿革说明，格式如：
    （1986年6月25日……通过 根据1988年……修正……）
    返回沿革文本，如果不是沿革则返回空字符串。
    """
    if not text:
        return ""
    text = text.strip()
    # 匹配以括号开头、包含通过/修正/修订/修改关键词的段落
    m = re.match(r"^[（(](.+?(?:通过|修正|修订|修改).+?)[）)]", text)
    if m:
        return m.group(0)
    # 也匹配结尾有)的
    m = re.match(r"^[（(](.+?(?:通过|修正|修订|修改).+)[）)]", text[:800])
    if m:
        return m.group(0)
    return ""


def _extract_dates_from_webpage(text: str) -> dict:
    """从网页文本中分离各类日期。
    返回 {source_publish_date, publish_date, pass_date, effective_date, latest_revision_date}
    """
    import datetime
    result = {
        "source_publish_date": "",
        "publish_date": "",
        "pass_date": "",
        "effective_date": "",
        "latest_revision_date": "",
    }

    date_re = re.compile(r"(\d{4})\s*[年/\-.—―－]\s*(\d{1,2})\s*[月/\-.—―－]\s*(\d{1,2})\s*日?")

    # 1. "时间：YYYY-MM-DD HH:mm:ss" → source_publish_date
    m = re.search(r"时间[：:]\s*(\d{4}-\d{1,2}-\d{1,2})", text)
    if m:
        result["source_publish_date"] = m.group(1)

    # 2. "自……起施行" → effective_date
    m = re.search(r"自\s*(\d{4})\s*[年]\s*(\d{1,2})\s*[月]\s*(\d{1,2})\s*日?\s*(?:起)?\s*(?:施行|实施|执行|生效)", text)
    if m:
        y, mo, d = m.groups()
        result["effective_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # 3. "公布"/"发布"日期 → publish_date
    m = re.search(r"(\d{4})\s*[年]\s*(\d{1,2})\s*[月]\s*(\d{1,2})\s*日?\s*(?:公布|发布)", text)
    if m:
        y, mo, d = m.groups()
        result["publish_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # 4. "通过"日期 → pass_date（查找"通过"，向前找最近的日期）
    pm = re.search(r"通过", text)
    if pm:
        pos = pm.start()
        before = text[max(0, pos - 120):pos]
        dm = re.search(r"(\d{4})\s*[年]\s*(\d{1,2})\s*[月]\s*(\d{1,2})\s*日?", before)
        if dm:
            y, mo, d = dm.groups()
            result["pass_date"] = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    # 5. 最近修正日期：先查找"修正"/"修订"，再向前找离它最近的日期
    revisions = []
    for m in re.finditer(r"(?:修正|修订)", text):
        pos = m.start()
        before = text[max(0, pos - 120):pos]
        matches = list(re.finditer(r"(\d{4})\s*[年]\s*(\d{1,2})\s*[月]\s*(\d{1,2})\s*日?", before))
        if matches:
            dm = matches[-1]  # 取最后一个（离"修正"最近的日期）
            y, mo, d = dm.groups()
            revisions.append(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")
    if revisions:
        result["latest_revision_date"] = revisions[-1]

    return result


def _parse_gd_natural_resource_page(soup) -> dict:
    """广东省自然资源厅网页专用解析。
    提取：标题、时间、来源、文号、正文、文件沿革。
    返回 dict 可直接合并到 safe_fetch_from_url 的 result 中。
    """
    result = {
        "source_publish_date": "",
        "source_name": "",
    }

    # 1. 查找"时间："标签
    time_pattern = re.compile(r"时间[：:]\s*(.+)")
    source_pattern = re.compile(r"来源[：:]\s*(.+)")
    doc_no_pattern = re.compile(r"文号[：:]\s*(.*)")

    # 获取页面全部文本用于标签匹配
    page_text = soup.get_text(separator="\n", strip=True)

    m = time_pattern.search(page_text)
    if m:
        time_str = m.group(1).strip()
        date_m = re.match(r"(\d{4}-\d{1,2}-\d{1,2})", time_str)
        if date_m:
            result["source_publish_date"] = date_m.group(1)

    m = source_pattern.search(page_text)
    if m:
        src = m.group(1).strip()
        # 截断到下一个标签（如"文号："）
        for sep in ["  文号", " 文号", "\n文号", "\n来源", "  来源"]:
            if sep in src:
                src = src.split(sep)[0].strip()
                break
        if src and len(src) < 60 and "来源" not in src:
            result["source_name"] = src

    m = doc_no_pattern.search(page_text)
    if m:
        no = m.group(1).strip()
        # 只有符合文号格式的内容才作为文号
        if no and re.search(r"[〔\(（\[\【]\d{4}[〕\)）\]\】]\d+号?", no):
            result["document_no"] = no
        else:
            result["document_no"] = ""

    return result


def _extract_webpage_metadata(soup, text: str) -> dict:
    """综合提取网页元数据，整合 HTML 解析和文本分析。
    返回 {title, document_no, source_publish_date, source_name,
           pass_date, effective_date, latest_revision_date,
           revision_history, category, region}
    """
    meta = {
        "title": "",
        "document_no": "",
        "source_publish_date": "",
        "source_name": "",
        "pass_date": "",
        "publish_date": "",
        "effective_date": "",
        "latest_revision_date": "",
        "revision_history": "",
        "category": "",
        "region": "",
        "issuing_authority_candidate": "",
    }

    # 1. 标题提取
    meta["title"] = _extract_title_from_webpage(soup, text)

    # 2. 文件沿革（检查前几行，找以括号开头且含"通过/修正/修订"的行）
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines[:5]:
        rh = _extract_revision_history(line)
        if rh:
            meta["revision_history"] = rh
            break

    # 3. 日期分离
    dates = _extract_dates_from_webpage(text)
    meta.update(dates)

    # 4. 广东省自然资源厅专用解析
    gd = _parse_gd_natural_resource_page(soup)
    if gd.get("source_publish_date"):
        meta["source_publish_date"] = gd["source_publish_date"]
    if gd.get("source_name"):
        meta["source_name"] = gd["source_name"]
    # 注意：文号从HTML标签读取比从正文正则更可靠
    if gd.get("document_no") is not None:
        meta["document_no"] = gd["document_no"]

    # 5. 文号：从正文用正则兜底（仅当网页标签无文号时）
    if not meta["document_no"]:
        for ptn in [
            r"[A-Za-z一-鿿、]+规字[〔\(（\[\【]\d{4}[〕\)）\]\】]\d+号",
            r"[A-Za-z一-鿿、]+发[〔\(（\[\【]\d{4}[〕\)）\]\】]\d+号",
            r"[A-Za-z一-鿿、]+办发[〔\(（\[\【]\d{4}[〕\)）\]\】]\d+号",
            r"[A-Za-z一-鿿、]+函[〔\(（\[\【]\d{4}[〕\)）\]\】]\d+号",
            r"[A-Za-z一-鿿、]+[〔\(（\[\【]\d{4}[〕\)）\]\】]\d+号",
        ]:
            m = re.search(ptn, text)
            if m:
                meta["document_no"] = m.group(0)
                break

    # 6. 标题 → 类别和地区推断
    title = meta["title"]
    if title:
        if re.search(r"中华人民共和国.{2,10}法\b", title) and "办法" not in title and "方法" not in title:
            meta["category"] = "法律"
            meta["region"] = "全国"

    return meta


def safe_fetch_from_url(url: str) -> dict:
    """安全地从公开政策网页抓取内容。
    仅允许 http/https GET 请求，禁止内网、本地文件、Cookie 等。
    返回 {"text": str, "source_type": str, "file_name": str, "error": str|None}
    """
    result = {"text": "", "source_type": "公开网页导入", "file_name": "", "error": None}

    # 安全校验
    is_safe, err_msg = _is_safe_url(url)
    if not is_safe:
        result["error"] = err_msg
        return result

    # 不携带用户 Cookie，仅使用通用 User-Agent
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 不允许重定向到不安全地址：使用自定义重定向处理
    try:
        resp = requests.get(
            url, headers=headers, timeout=15, allow_redirects=False, stream=True
        )
    except requests.RequestException as e:
        result["error"] = "网络请求失败，请检查链接是否正确、网络是否通畅"
        return result

    # 处理重定向
    redirect_count = 0
    while resp.status_code in (301, 302, 303, 307, 308) and redirect_count < 5:
        redirect_url = resp.headers.get("Location", "")
        if not redirect_url:
            break
        # 处理相对 URL
        from urllib.parse import urljoin
        redirect_url = urljoin(url, redirect_url)
        is_safe, err_msg = _is_safe_url(redirect_url)
        if not is_safe:
            result["error"] = "重定向目标地址不安全: " + err_msg
            return result
        try:
            resp = requests.get(
                redirect_url, headers=headers, timeout=15,
                allow_redirects=False, stream=True
            )
        except requests.RequestException as e:
            result["error"] = "重定向请求失败，请检查链接是否正确"
            return result
        url = redirect_url
        redirect_count += 1

    if resp.status_code != 200:
        result["error"] = "网页响应异常（HTTP " + str(resp.status_code) + "），请确认链接是否正确"
        resp.close()
        return result

    # 限制响应体大小：不超过 10MB
    max_size = 10 * 1024 * 1024
    content = b""
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > max_size:
                result["error"] = "响应内容超过 10MB 限制，请手动下载后上传"
                resp.close()
                return result
    except requests.RequestException:
        result["error"] = "读取网页内容时网络中断"
        resp.close()
        return result
    finally:
        resp.close()

    # 创建虚拟 response 对象用于 decode_response_content
    class _FakeResponse:
        def __init__(self, content, headers):
            self.content = content
            self.headers = headers
            self.apparent_encoding = None

    fake_resp = _FakeResponse(content, resp.headers)
    try:
        fake_resp.apparent_encoding = resp.apparent_encoding
    except Exception:
        pass
    html = decode_response_content(fake_resp)

    # 判断内容类型
    content_type = resp.headers.get("Content-Type", "").lower()
    url_lower = url.lower().split("?")[0]

    # 检查是否是可直接下载的文件（不支持 .doc，只支持 .docx）
    file_exts = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".xls": "xls", ".txt": "txt"}
    is_direct_file = False
    for ext, label in file_exts.items():
        if url_lower.endswith(ext) or ext in content_type:
            try:
                suffix = ext
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                text = parse_file(tmp_path, pdf_max_pages=20)
                os.unlink(tmp_path)
                result["text"] = text
                result["source_type"] = "公开网页导入"
                result["file_name"] = url.rstrip("/").split("/")[-1]
                return result
            except Exception as e:
                result["error"] = "文件解析失败，请确认文件格式正确"
                return result

    # 如果是 .doc 文件，提示不支持
    if url_lower.endswith(".doc") or ".doc" in content_type:
        result["error"] = "不支持 .doc 格式，请转换为 .docx 后上传"
        return result

    # 是网页，用 BeautifulSoup 提取正文
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # 移除 script/style/nav/footer/header/aside 及无关标签
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside",
                                   "button", "select", "textarea"]):
            tag.decompose()
        # 移除"打印"/"字体"/"分享"等UI元素
        for cls in ["print", "font", "share", "toolbar", "sidebar", "menu", "nav"]:
            for tag in soup.find_all(class_=re.compile(cls, re.I)):
                tag.decompose()

        # 尝试找正文容器
        main = soup.find("main") or soup.find("article") or soup.find(
            "div", class_=re.compile(r"(content|article|main|body|text)", re.I)) or soup.body
        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)
        # 清理空行
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        result["text"] = "\n".join(lines)
        result["source_type"] = "公开网页导入"
        result["file_name"] = url.rstrip("/").split("/")[-1] or "webpage"

        # 提取网页结构化元数据
        result["webpage_meta"] = _extract_webpage_metadata(soup, result["text"])
    except ImportError:
        result["error"] = "缺少 beautifulsoup4 库，无法解析网页"
    except Exception as e:
        result["error"] = "网页解析失败，请确认该页面是否为公开可访问的政策文件页面"

    return result


def fetch_from_url(url: str) -> dict:
    """兼容旧接口，内部调用 safe_fetch_from_url"""
    return safe_fetch_from_url(url)


def analyze_document(text: str) -> dict:
    """分析文档要点，提取结构化摘要。
    返回 {"summary": str, "key_points": list[str], "scope": str, "deadlines": list[str]}
    """
    if not text or len(text) < 50:
        return {"summary": "", "key_points": [], "scope": "", "deadlines": []}

    sentences = re.split(r"[。；\n]+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    # 关键标志词
    obligation_keywords = ["应当", "必须", "不得", "禁止", "严禁", "应", "要", "负责", "执行"]
    scope_keywords = ["范围", "适用", "管理对象", "调整", "规范"]
    deadline_keywords = ["期限", "日前", "之日起", "之前", "截止", "有效期至", "届满"]
    key_section_keywords = ["第一条", "第一章", "总则", "目的", "依据", "为"]

    key_points = []
    deadlines = []
    scope_text = ""

    for s in sentences:
        lower = s
        # 提取强制性条款
        if any(kw in lower for kw in obligation_keywords):
            if len(key_points) < 10 and len(s) > 15:
                key_points.append(s[:120])

        # 提取适用范围
        if any(kw in lower for kw in scope_keywords):
            if not scope_text and len(s) > 15:
                scope_text = s[:150]

        # 提取时限要求
        if any(kw in lower for kw in deadline_keywords):
            if len(deadlines) < 5 and len(s) > 15:
                deadlines.append(s[:120])

    # 生成摘要
    summary_parts = []
    # 取开头的前几句
    intro = "；".join(sentences[:3]) if len(sentences) >= 3 else "；".join(sentences)
    if len(intro) > 200:
        intro = intro[:200] + "…"
    summary_parts.append(intro)

    if key_points:
        summary_parts.append(f"涉及 {len(key_points)} 条强制性/义务性规定")
    if deadlines:
        summary_parts.append(f"包含 {len(deadlines)} 项时限要求")

    return {
        "summary": "。".join(summary_parts) if summary_parts else intro,
        "key_points": key_points,
        "scope": scope_text,
        "deadlines": deadlines,
    }
