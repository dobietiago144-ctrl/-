"""文档解析：从 Word/PDF/TXT/Excel/URL 中提取文本"""

import os
import re
import tempfile
from docx import Document
import requests


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


def parse_pdf(file_path: str, max_pages: int = 0) -> str:
    """解析 PDF 文件。max_pages=0 表示全部页面"""
    import fitz  # PyMuPDF
    doc = fitz.open(file_path)
    pages = []
    for i, page in enumerate(doc):
        if max_pages > 0 and i >= max_pages:
            break
        text = page.get_text()
        if text.strip():
            pages.append(text.strip())
    total = doc.page_count
    doc.close()
    result = "\n".join(pages)
    if max_pages > 0 and total > max_pages:
        result += f"\n\n[PDF共{total}页，仅展示前{max_pages}页概要，完整内容将在入库后存储]"
    return result


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
    if ext == ".docx":
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
    """返回支持的文件扩展名列表（用于 file_uploader）"""
    return ["docx", "pdf", "txt", "xlsx", "xls"]


def fetch_from_url(url: str) -> dict:
    """从 URL 抓取政策文件内容。
    返回 {"text": str, "source_type": str, "file_name": str, "error": str|None}
    """
    result = {"text": "", "source_type": "网络检索", "file_name": "", "error": None}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        # 强制检测真正的编码（中文网站常声明错误）
        resp.encoding = resp.apparent_encoding or "utf-8"
    except requests.RequestException as e:
        result["error"] = f"网络请求失败: {e}"
        return result

    # 判断内容类型
    content_type = resp.headers.get("Content-Type", "").lower()
    url_lower = url.lower().split("?")[0]

    # 检查是否是可直接下载的文件
    file_exts = {".pdf": "pdf", ".docx": "docx", ".doc": "docx", ".xlsx": "xlsx", ".xls": "xls", ".txt": "txt"}
    for ext, label in file_exts.items():
        if url_lower.endswith(ext) or ext in content_type:
            try:
                suffix = ext
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(resp.content)
                    tmp_path = tmp.name
                text = parse_file(tmp_path, pdf_max_pages=20)
                os.unlink(tmp_path)
                result["text"] = text
                result["source_type"] = "上传"
                result["file_name"] = url.rstrip("/").split("/")[-1]
                return result
            except Exception as e:
                result["error"] = f"文件解析失败: {e}"
                return result

    # 是网页，用 BeautifulSoup 提取正文（用 content 让其自动检测编码）
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.content, "html.parser")
        # 移除 script/style/nav/footer
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
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
        result["source_type"] = "网络检索"
        result["file_name"] = url.rstrip("/").split("/")[-1] or "webpage"
    except ImportError:
        result["error"] = "缺少 beautifulsoup4 库"
    except Exception as e:
        result["error"] = f"网页解析失败: {e}"

    return result


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
