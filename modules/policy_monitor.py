"""政策废止监测模块 — 手动检查官方公开网站，发现废止/失效/替代政策，进入候选池"""

import re
import hashlib
from datetime import datetime
from urllib.parse import urlparse, urljoin

from config import (
    MONITOR_KEYWORDS, OFFICIAL_POLICY_SOURCES,
    POLICY_MONITOR_MAX_PAGES, POLICY_MONITOR_MAX_ITEMS_PER_SOURCE,
    ENABLE_AUTO_UPDATE_LIBRARY, POLICY_MONITOR_SEED_URLS,
    MNR_ALLOWED_DOMAINS, POLICY_MONITOR_KEYWORDS,
    SEARCH_URL_TEMPLATE,
)


# ═══════════════════════════════════════════
#  网页内容解码 — 解决中文政府网站乱码
# ═══════════════════════════════════════════

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

    # 1. 从 HTTP header Content-Type 识别 charset
    charset_from_header = None
    content_type = response.headers.get("Content-Type", "")
    ct_match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
    if ct_match:
        charset_from_header = ct_match.group(1).lower().strip().strip('"').strip("'")
        # 标准化编码名
        charset_map = {
            "gb2312": "gb18030",  # gb2312 用 gb18030 解码更安全
            "gbk": "gb18030",
        }
        charset_from_header = charset_map.get(charset_from_header, charset_from_header)

    # 2. 从 HTML meta charset 识别
    charset_from_meta = None
    try:
        # 先用 utf-8 尝试解码前 2048 字节来读取 meta
        head_sample = content[:2048].decode("utf-8", errors="replace")
        meta_match = re.search(
            r'<meta[^>]+charset=["\']?([^"\'\s;>]+)',
            head_sample, re.IGNORECASE
        )
        if meta_match:
            charset_from_meta = meta_match.group(1).lower().strip()
            charset_from_meta = charset_map.get(charset_from_meta, charset_from_meta) if 'charset_map' in dir() else charset_from_meta
            m2 = {"gb2312": "gb18030", "gbk": "gb18030"}
            charset_from_meta = m2.get(charset_from_meta, charset_from_meta)
    except Exception:
        pass

    # 3. requests apparent_encoding
    apparent = None
    try:
        apparent = response.apparent_encoding
        if apparent:
            apparent = apparent.lower()
            m3 = {"gb2312": "gb18030", "gbk": "gb18030"}
            apparent = m3.get(apparent, apparent)
    except Exception:
        pass

    # 4. 按优先级尝试解码
    candidate_encodings = []
    seen = set()
    for enc in [charset_from_header, charset_from_meta, apparent, "utf-8", "gb18030", "gbk"]:
        if enc and enc not in seen:
            seen.add(enc)
            candidate_encodings.append(enc)

    # 再补充可能的编码
    for enc in ["utf-8", "gb18030", "gbk"]:
        if enc not in seen:
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

        # 评分：检查中文质量
        score = _evaluate_chinese_quality(decoded)
        if score > best_score:
            best_score = score
            best_html = decoded
            # 高质量直接返回
            if score >= 90:
                return best_html

    if best_html:
        return best_html

    # 最终兜底
    return content.decode("utf-8", errors="replace")


def _evaluate_chinese_quality(text: str) -> int:
    """评估文本中文质量，返回 0-100 分。

    高分 = 中文质量好，低分 = 乱码
    """
    if not text:
        return 0

    total = len(text)

    # 统计各类字符
    chinese_chars = len(re.findall(r"[一-鿿]", text))
    replacement_chars = text.count("�")  # �
    # 西欧乱码字符：高ASCII单字节的连续出现（GBK用UTF-8解码的典型乱码）
    mojibake_pattern = re.findall(r"[èæåäöüéêëîïôœ]{2,}", text)
    mojibake_chars = sum(len(m) for m in mojibake_pattern)

    # 乱码检测：替换字符过多
    if total > 0 and replacement_chars > total * 0.1:
        return 5  # 严重乱码

    # 西欧乱码检测
    if total > 0 and mojibake_chars > total * 0.05:
        return 10

    # 中文字符比例
    chinese_ratio = chinese_chars / max(total, 1)
    if chinese_ratio > 0.15:
        return 95  # 中文比例正常
    elif chinese_ratio > 0.05:
        return 75
    elif chinese_ratio > 0.01:
        return 50

    # 短文本且没有乱码标记 → 给高分
    if total < 50 and replacement_chars == 0 and mojibake_chars == 0:
        return 90

    # 没有中文但也没有乱码标记，可能是全英文页面
    if replacement_chars == 0 and mojibake_chars == 0:
        return 70

    return 30


def safe_fetch_html(url: str, timeout: int = 30) -> tuple[str, str]:
    """获取并解码网页 HTML。

    Returns:
        (html_text, error_message)
    """
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        return "", str(e)

    html = decode_response_content(resp)
    return html, ""


def get_monitor_keywords() -> list[str]:
    """获取监测关键词列表"""
    return list(MONITOR_KEYWORDS)


def detect_obsolete_keywords(text: str) -> list[str]:
    """检测文本中包含的废止/失效/替代关键词。

    Returns:
        匹配到的关键词列表（去重）
    """
    if not text:
        return []
    found = []
    for kw in MONITOR_KEYWORDS:
        if kw in text:
            found.append(kw)
    return list(dict.fromkeys(found))  # 去重保序


def detect_relation_basis(text: str) -> str:
    """从文本中提取废止/替代依据句。

    搜索包含废止/失效/替代关键词的句子（以句号、分号、换行为分隔）。
    """
    if not text:
        return ""

    sentences = re.split(r"[。；\n]+", text)
    keywords = ["废止", "失效", "替代", "代替", "不再执行", "停止执行", "修订", "修改"]

    candidates = []
    for s in sentences:
        s = s.strip()
        if len(s) < 15 or len(s) > 500:
            continue
        if any(kw in s for kw in keywords):
            candidates.append(s)

    return "\n".join(candidates[:5]) if candidates else ""


def match_existing_documents(title: str = "", document_no: str = "", text: str = "") -> dict:
    """尝试匹配文件库中已有文件。

    Returns:
        {"matched": bool, "matched_id": int|None, "matched_title": str, "match_method": str}
    """
    import database.db as db

    # 1. 文号精确匹配
    if document_no:
        existing = db.get_document_by_no(document_no)
        if existing:
            return {
                "matched": True,
                "matched_id": existing["id"],
                "matched_title": existing["title"],
                "match_method": "文号精确匹配",
            }

    # 2. 标题精确匹配
    if title:
        existing = db.get_document_by_title(title)
        if existing:
            return {
                "matched": True,
                "matched_id": existing["id"],
                "matched_title": existing["title"],
                "match_method": "标题精确匹配",
            }

    # 3. 标题模糊匹配（内嵌）
    if title and len(title) >= 10:
        all_titles = db.get_all_titles()
        for doc in all_titles:
            doc_title = doc.get("title", "")
            if doc_title and (title in doc_title or doc_title in title):
                return {
                    "matched": True,
                    "matched_id": doc["id"],
                    "matched_title": doc_title,
                    "match_method": "标题模糊匹配",
                }

    return {"matched": False, "matched_id": None, "matched_title": "", "match_method": ""}


def guess_relation_type(keywords: list[str], text: str) -> str:
    """根据检测到的关键词推测关系类型"""
    kw_str = " ".join(keywords) + " " + (text or "")
    if any(k in kw_str for k in ["废止", "予以废止", "同时废止", "废止的部门规章"]):
        return "疑似废止"
    if any(k in kw_str for k in ["失效", "有效期届满", "已废止或者失效"]):
        return "疑似失效"
    if any(k in kw_str for k in ["替代", "代替"]):
        return "疑似替代"
    if any(k in kw_str for k in ["修订", "修改"]):
        return "替代修订"
    return "其他"


# ═══════════════════════════════════════════
#  policy_monitor_candidates CRUD
# ═══════════════════════════════════════════

def save_monitor_candidate(data: dict) -> int:
    """保存监测候选到数据库"""
    import database.db as db
    allowed = [
        "source_name", "source_domain", "source_url",
        "title", "document_no", "publish_date", "source_publish_date",
        "source_name_text", "summary", "full_text",
        "candidate_type", "detected_keywords",
        "relation_type_guess", "relation_basis_text",
        "matched_document_id", "matched_title", "confidence",
        "status", "notes",
    ]
    row_data = {k: data.get(k, "") for k in allowed}
    row_data.setdefault("status", "已抓取待确认")
    row_data.setdefault("candidate_type", "其他")

    conn = db.get_connection()
    placeholders = ", ".join([f":{k}" for k in allowed])
    cols = ", ".join(allowed)
    sql = f"INSERT INTO policy_monitor_candidates ({cols}) VALUES ({placeholders})"
    cur = conn.execute(sql, row_data)
    conn.commit()
    cid = cur.lastrowid
    conn.close()

    # 操作日志
    db.log_operation({
        "action": "政策监测候选",
        "target_type": "monitor_candidate",
        "target_id": cid,
        "file_name": data.get("title", "")[:50],
        "notes": f"从 {data.get('source_name', '')} 抓取，类型: {data.get('candidate_type', '')}",
    })
    return cid


def get_monitor_candidates(status: str = "", limit: int = 100) -> list[dict]:
    """获取监测候选列表"""
    import database.db as db
    conn = db.get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM policy_monitor_candidates WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM policy_monitor_candidates ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monitor_candidate(candidate_id: int) -> dict | None:
    """获取单个监测候选"""
    import database.db as db
    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM policy_monitor_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_monitor_candidate(candidate_id: int, data: dict):
    """更新监测候选"""
    import database.db as db
    conn = db.get_connection()
    allowed = [
        "title", "document_no", "publish_date", "summary", "full_text",
        "candidate_type", "detected_keywords", "relation_type_guess",
        "relation_basis_text", "matched_document_id", "matched_title",
        "confidence", "status", "notes",
    ]
    sets = []
    values = {"id": candidate_id}
    for k in allowed:
        if k in data:
            sets.append(f"{k} = :{k}")
            values[k] = data[k]
    if sets:
        sets.append("updated_at = datetime('now','localtime')")
        sql = f"UPDATE policy_monitor_candidates SET {', '.join(sets)} WHERE id = :id"
        conn.execute(sql, values)
        conn.commit()
    conn.close()


def confirm_candidate_to_library(candidate_id: int) -> dict:
    """将候选确认入库（人工确认后调用）。

    返回 {"success": bool, "doc_id": int|None, "message": str}
    """
    if ENABLE_AUTO_UPDATE_LIBRARY:
        # 安全阀：即使配置为 True 也应该有人工确认环节
        pass

    candidate = get_monitor_candidate(candidate_id)
    if not candidate:
        return {"success": False, "doc_id": None, "message": "候选记录不存在"}

    import database.db as db
    from modules.metadata_extractor import extract_all_metadata, classify_document
    from modules.classifier import classify_business_tags
    from modules.status_utils import normalize_document_status

    title = candidate.get("title", "")
    doc_no = candidate.get("document_no", "")
    text = candidate.get("full_text", "")
    meta = extract_all_metadata(text) if text else {}

    try:
        data = {
            "title": title or meta.get("title", "未命名政策"),
            "document_no": doc_no or meta.get("document_no", ""),
            "issuing_authority": meta.get("issuing_authority", ""),
            "publish_date": candidate.get("publish_date") or meta.get("publish_date", ""),
            "effective_date": meta.get("effective_date", ""),
            "status": normalize_document_status(meta.get("status", "待核实")),
            "region": candidate.get("source_name", "").find("广东") >= 0 and "省" or "全国",
            "category": classify_document(title, doc_no, text),
            "keywords": meta.get("keywords", ""),
            "business_tags": ",".join(classify_business_tags(title, "", text)),
            "sensitivity_level": "公开",
            "file_name": "",
            "file_size": 0,
            "file_type": "",
            "full_text": text,
            "source_type": "政策监测导入",
            "source_url": candidate.get("source_url", ""),
            "file_path": "",
            "confirmed": 0,
            "notes": f"从 {candidate.get('source_name', '')} 监测候选入库",
        }
        doc_id = db.create_document(data)

        # 更新候选状态
        update_monitor_candidate(candidate_id, {"status": "已确认入库"})

        db.log_operation({
            "action": "监测候选确认入库",
            "target_type": "document",
            "target_id": doc_id,
            "file_name": title[:50],
            "notes": f"候选ID: {candidate_id}, 来源: {candidate.get('source_name', '')}",
        })
        return {"success": True, "doc_id": doc_id, "message": f"《{title}》入库成功"}
    except Exception as e:
        return {"success": False, "doc_id": None, "message": str(e)}


def delete_monitor_candidate(candidate_id: int):
    """从候选池删除一条候选记录"""
    import database.db as db
    conn = db.get_connection()
    conn.execute("DELETE FROM policy_monitor_candidates WHERE id = ?", (candidate_id,))
    conn.commit()
    conn.close()


def add_ignored_url(url: str, title: str = "", source_name: str = "", notes: str = ""):
    """将 URL 加入已忽略列表"""
    import hashlib
    import database.db as db
    url_hash = hashlib.md5(url.encode()).hexdigest()
    conn = db.get_connection()
    conn.execute(
        """INSERT INTO policy_monitor_ignored_urls (url, url_hash, title, source_name, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (url, url_hash, title, source_name, notes)
    )
    conn.commit()
    conn.close()


def ignore_candidate(candidate_id: int, reason: str = "", add_to_ignored: bool = True):
    """忽略候选：从候选池删除，可选加入已忽略列表"""
    candidate = get_monitor_candidate(candidate_id)
    if candidate:
        url = candidate.get("source_url", "")
        title = candidate.get("title", "")
        source = candidate.get("source_name", "")

        # 从候选池删除
        delete_monitor_candidate(candidate_id)

        # 加入已忽略列表
        if add_to_ignored and url:
            add_ignored_url(url, title, source, reason)

        import database.db as db
        db.log_operation({
            "action": "忽略并删除政策监测候选",
            "target_type": "policy_monitor_candidate",
            "target_id": candidate_id,
            "notes": f"{reason} | URL: {url} | 标题: {title}",
        })


def add_manual_monitor_url(url: str, source_name: str = "手动添加") -> dict:
    """手动添加一个监测链接，抓取详情并加入候选池。

    返回 {
        "success": bool, "candidate_id": int|None, "message": str,
        "preview": dict|None  # 解析预览
    }
    """
    import database.db as db
    import requests

    # 安全检查
    allowed = MNR_ALLOWED_DOMAINS
    safe, err = _check_safe_url(url, allowed)
    if not safe:
        return {"success": False, "candidate_id": None, "message": f"URL 不安全: {err}", "preview": None}

    # 检查是否已忽略
    if is_url_ignored(url):
        return {"success": False, "candidate_id": None, "message": "该链接已被忽略，是否恢复？", "preview": None}

    # 检查是否已存在候选池
    conn = db.get_connection()
    existing = conn.execute(
        "SELECT id FROM policy_monitor_candidates WHERE source_url = ?", (url,)
    ).fetchone()
    conn.close()
    if existing:
        return {"success": False, "candidate_id": existing["id"], "message": f"该链接已在候选池中 (ID: {existing['id']})", "preview": None}

    # 抓取并解码（使用稳定解码）
    html, fetch_error = safe_fetch_html(url, timeout=20)
    if fetch_error:
        return {"success": False, "candidate_id": None, "message": f"抓取失败: {fetch_error}", "preview": None}

    # 使用 MNR 专用解析器
    parsed = parse_mnr_policy_library_detail(html, url)
    full_text = parsed.get("full_text", "") or _extract_main_text_from_html(html)

    # 提取被废止旧文件
    obsolete_items = extract_obsolete_items_from_text(full_text)
    match_affected_items_with_library(obsolete_items)

    # 检测关键词
    found_kws = detect_obsolete_keywords(parsed.get("title", "") + " " + full_text)
    relation_guess = guess_relation_type(found_kws, full_text)

    preview = {
        "title": parsed.get("title", ""),
        "document_no": parsed.get("document_no", ""),
        "issuing_authority": parsed.get("issuing_authority", ""),
        "publish_date": parsed.get("publish_date", "") or parsed.get("pass_date", ""),
        "status_from_source": parsed.get("status_from_source", ""),
        "effectiveness_level": parsed.get("effectiveness_level", ""),
        "candidate_type": "废止公告" if "废止" in parsed.get("title", "") + full_text[:200]
        else ("失效目录" if "失效" in parsed.get("title", "") + full_text[:200] else "其他"),
        "detected_keywords": ",".join(found_kws),
        "obsolete_items": obsolete_items,
        "obsolete_count": len(obsolete_items),
        "full_text": full_text,
        "parse_warning": parsed.get("parse_warning", ""),
    }

    return {"success": True, "candidate_id": None, "message": "解析完成，请确认入库", "preview": preview}


def _extract_main_text_from_html(html: str) -> str:
    """从 HTML 提取正文（辅助函数）"""
    from bs4 import BeautifulSoup
    import re as _re
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.find(
        "div", class_=_re.compile(r"(content|article|main|body|text)", _re.I))
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def mark_old_document_status(doc_id: int, new_status: str, basis: str = ""):
    """将某旧文件状态更新（人工确认后）"""
    import database.db as db
    from modules.status_utils import normalize_document_status

    norm_status = normalize_document_status(new_status)
    db.update_document(doc_id, {
        "status": norm_status,
        "notes": (db.get_document(doc_id) or {}).get("notes", "") + f"; 监测更新: {basis}",
    })
    db.log_operation({
        "action": "监测-更新文件状态",
        "target_type": "document",
        "target_id": doc_id,
        "notes": f"状态改为: {norm_status}, 依据: {basis}",
    })


def is_allowed_mnr_url(url: str) -> bool:
    """检查 URL 是否属于自然资源部允许域名（主域 mnr.gov.cn 及其子域）"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname == "mnr.gov.cn" or hostname.endswith(".mnr.gov.cn")


def is_url_ignored(url: str) -> bool:
    """检查 URL 是否已被忽略"""
    import hashlib
    import database.db as db
    url_hash = hashlib.md5(url.encode()).hexdigest()
    conn = db.get_connection()
    row = conn.execute(
        "SELECT id FROM policy_monitor_ignored_urls WHERE url_hash = ?",
        (url_hash,)
    ).fetchone()
    conn.close()
    return bool(row)


def is_url_in_library(url: str) -> bool:
    """检查 URL 是否已存在于正式文件库 source_url 中"""
    import database.db as db
    conn = db.get_connection()
    row = conn.execute(
        "SELECT id FROM documents WHERE source_url = ? AND source_url != ''",
        (url,)
    ).fetchone()
    conn.close()
    return bool(row)


def is_url_in_candidates(url: str) -> bool:
    """检查 URL 是否已存在于候选池中"""
    import database.db as db
    conn = db.get_connection()
    row = conn.execute(
        "SELECT id FROM policy_monitor_candidates WHERE source_url = ?",
        (url,)
    ).fetchone()
    conn.close()
    return bool(row)


def is_duplicate_by_title_doc_no(title: str, document_no: str) -> bool:
    """检查 title + document_no 是否已在正式库中存在"""
    if not document_no:
        return False
    import database.db as db
    conn = db.get_connection()
    row = conn.execute(
        "SELECT id FROM documents WHERE title = ? AND document_no = ? AND document_no != ''",
        (title, document_no)
    ).fetchone()
    conn.close()
    return bool(row)


def _check_safe_url(url: str, allowed_domains: list[str]) -> tuple[bool, str]:
    """安全检查 URL。支持子域名：只要 hostname 以允许域名的某个结束即可"""
    from urllib.parse import urlparse
    import ipaddress

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "仅支持 http/https"
    hostname = (parsed.hostname or "").lower()
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False, "禁止本地地址"
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False, "禁止内网地址"
    except ValueError:
        pass
    # 域名白名单检查：支持子域名
    if not any(hostname == d or hostname.endswith("." + d) or hostname.endswith(d) for d in allowed_domains):
        return False, f"域名不在白名单中 (允许: {allowed_domains})"
    return True, ""


def search_mnr_policy_library_by_keyword(keyword: str, max_pages: int = 3) -> list[dict]:
    """在自然资源部政策法规库中根据关键词搜索，查找废止/失效/替代类页面。

    实现方式：
    1. 优先尝试自然资源部政策法规库的站内搜索引擎
    2. 如果不能识别，使用配置的 SEARCH_URL_TEMPLATE
    3. 结果只保留 mnr.gov.cn 及其子域链接
    4. 结果链接进入候选判断流程

    Returns:
        [{title, url, snippet, detected_keywords, source}]
    """
    import requests
    from bs4 import BeautifulSoup
    import urllib.parse

    results = []
    allowed_domains = MNR_ALLOWED_DOMAINS

    # 方式1: 尝试自然资源部站内搜索
    # 自然资源部站内搜索 URL 格式常见几种
    search_urls = [
        SEARCH_URL_TEMPLATE.format(keyword=urllib.parse.quote(keyword)),
        f"https://www.mnr.gov.cn/s?searchWord={urllib.parse.quote(keyword)}&pageSize=20&pageNum=1",
    ]

    all_links = []
    search_html = ""

    for search_url in search_urls[:2]:
        if not is_allowed_mnr_url(search_url):
            continue
        try:
            html, err = safe_fetch_html(search_url, timeout=20)
            if err:
                continue
            search_html = html
            break
        except Exception:
            continue

    if not search_html:
        return results

    soup = BeautifulSoup(search_html, "html.parser")

    # 解析搜索结果
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # 解析相对URL
        if href.startswith("/"):
            href = f"https://www.mnr.gov.cn{href}"
        elif not href.startswith("http"):
            href = f"https://www.mnr.gov.cn/{href}"

        # 只保留允许域名
        if not is_allowed_mnr_url(href):
            continue

        # 只保留详情页链接（.html 或含 /t 的）
        if not (href.endswith(".html") or "/t" in href.split("/")[-1] if "/" in href else False):
            continue

        link_text = a_tag.get_text(strip=True)
        combined = link_text + " " + href

        # 检查是否包含监测关键词
        found_kws = detect_obsolete_keywords(combined)
        if not found_kws:
            # 检查是否包含搜索关键词
            if keyword in combined:
                found_kws = [keyword]

        if found_kws:
            # 检查是否已存在
            if is_url_ignored(href):
                continue
            if is_url_in_library(href):
                continue
            if is_url_in_candidates(href):
                continue

            all_links.append({
                "title": link_text[:200] or "",
                "url": href,
                "snippet": "",
                "detected_keywords": ",".join(found_kws),
                "source": f"关键词搜索: {keyword}",
            })

    # 限制条数
    all_links = all_links[:POLICY_MONITOR_MAX_ITEMS_PER_SOURCE]

    # 尝试抓取详情页获取更多信息
    for link in all_links[:max_pages * 10]:
        try:
            detail_html, err = safe_fetch_html(link["url"], timeout=20)
            if err:
                continue

            soup_detail = BeautifulSoup(detail_html, "html.parser")
            text = _extract_main_text(soup_detail)
            if text:
                link["snippet"] = text[:300]
                link["full_text"] = text

                # 补充检测关键词
                extra_kws = detect_obsolete_keywords(text)
                existing_kws = set(link["detected_keywords"].split(",")) if link["detected_keywords"] else set()
                all_kws = existing_kws | set(extra_kws)
                link["detected_keywords"] = ",".join(all_kws)

                # 尝试提取标题
                if not link["title"]:
                    parsed = parse_mnr_policy_library_detail(detail_html, link["url"])
                    link["title"] = parsed.get("title", "")[:200]

            results.append(link)
        except Exception:
            pass

    return results


def check_official_source(source: dict) -> dict:
    """检查一个官方来源，抓取种子URL并提取含关键词的链接和内容。

    返回 {
        "source_name": str,
        "candidates": list[dict],
        "error": str|None,
        "scanned_count": int,
        "in_library_count": int,
        "in_candidates_count": int,
        "ignored_count": int,
        "duplicate_count": int,
        "new_count": int,
        "failed_count": int,
    }
    """
    import requests
    from bs4 import BeautifulSoup

    domain = source.get("domain", "")
    allowed_domains = MNR_ALLOWED_DOMAINS if domain == "mnr.gov.cn" else [domain]

    result = {
        "source_name": source.get("source_name", ""),
        "candidates": [],
        "error": None,
        "scanned_count": 0,
        "in_library_count": 0,
        "in_candidates_count": 0,
        "ignored_count": 0,
        "duplicate_count": 0,
        "new_count": 0,
        "failed_count": 0,
    }

    urls_to_check = POLICY_MONITOR_SEED_URLS if domain == "mnr.gov.cn" else [source.get("url", "")]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    all_links = []

    for seed_url in urls_to_check:
        safe, err_msg = _check_safe_url(seed_url, allowed_domains)
        if not safe:
            continue

        # 种子链接本身如果是详情页，直接尝试抓取
        if seed_url.endswith(".html") or ("/t" in seed_url.split("/")[-1] if "/" in seed_url else False):
            html, fetch_err = safe_fetch_html(seed_url, timeout=30)
            if fetch_err:
                continue

            soup = BeautifulSoup(html, "html.parser")
            text = _extract_main_text(soup)
            if text:
                found_kws = detect_obsolete_keywords(text)
                if found_kws:
                    if is_url_ignored(seed_url):
                        result["ignored_count"] += 1
                    elif is_url_in_library(seed_url):
                        result["in_library_count"] += 1
                    elif is_url_in_candidates(seed_url):
                        result["in_candidates_count"] += 1
                    else:
                        all_links.append({
                            "title": "",
                            "url": seed_url,
                            "detected_keywords": ",".join(found_kws),
                            "is_detail": True,
                        })
            continue

        html, fetch_err = safe_fetch_html(seed_url, timeout=30)
        if fetch_err:
            continue

        soup = BeautifulSoup(html, "html.parser")

        for a_tag in soup.find_all("a", href=True):
            link_text = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if href.startswith("/"):
                href = f"{seed_url.rstrip('/')}{href}"
            elif not href.startswith("http"):
                href = f"{seed_url.rstrip('/')}/{href}"

            safe, _ = _check_safe_url(href, allowed_domains)
            if not safe:
                continue

            # 去重检查
            result["scanned_count"] += 1

            if is_url_ignored(href):
                result["ignored_count"] += 1
                continue
            if is_url_in_library(href):
                result["in_library_count"] += 1
                continue
            if is_url_in_candidates(href):
                result["in_candidates_count"] += 1
                continue

            combined = link_text + href
            found_kws = detect_obsolete_keywords(combined)
            if found_kws:
                all_links.append({
                    "title": link_text[:200],
                    "url": href,
                    "detected_keywords": ",".join(found_kws),
                })

    # 去重
    seen_urls = set()
    unique_links = []
    for li in all_links:
        if li["url"] not in seen_urls:
            seen_urls.add(li["url"])
            unique_links.append(li)
    unique_links = unique_links[:POLICY_MONITOR_MAX_ITEMS_PER_SOURCE]

    # 抓取详情
    for link in unique_links[:POLICY_MONITOR_MAX_PAGES * 10]:
        try:
            detail = fetch_candidate_detail(link["url"], source)
            if detail:
                # 再次检查 title+doc_no dup
                if is_duplicate_by_title_doc_no(
                    detail.get("title", ""), detail.get("document_no", "")
                ):
                    result["duplicate_count"] += 1
                    continue

                detail["source_name"] = source.get("source_name", "")
                detail["source_domain"] = domain
                detail["source_url"] = link["url"]
                detail["detected_keywords"] = link.get("detected_keywords", "")
                result["candidates"].append(detail)
                result["new_count"] += 1
        except Exception:
            result["failed_count"] += 1

    return result


def parse_mnr_policy_library_detail(html: str, url: str = "") -> dict:
    """解析自然资源部政策法规库（f.mnr.gov.cn）详情页。

    提取元数据表中的字段：标题、文号、发布机构、成文日期、效力级别等。
    返回结构化 dict。
    """
    from bs4 import BeautifulSoup
    import re as _re

    result = {
        "title": "",
        "document_no": "",
        "issuing_authority": "",
        "pass_date": "",
        "publish_date": "",
        "source_publish_date": "",
        "effectiveness_level": "",  # 效力级别
        "business_type_source": "",  # 页面上的业务类型
        "status_from_source": "",  # 时效状态（仅作参考）
        "full_text": "",
        "affected_items_text": "",
        "parse_warning": "",
        "candidate_type_hint": "",  # 基于标题的关键词推断
    }

    soup = BeautifulSoup(html, "html.parser")

    # 1. 从页面元数据表格提取（td/tr 结构）
    # 自然资源部常见字段映射
    field_map = {
        "名称": "title",
        "标题": "title",
        "文号": "document_no",
        "发文字号": "document_no",
        "发布机构": "issuing_authority",
        "发文单位": "issuing_authority",
        "机构": "issuing_authority",
        "成文日期": "pass_date",
        "效力级别": "effectiveness_level",
        "业务类型": "business_type_source",
        "发布日期": "publish_date",
        "发布时间": "publish_date",
        "时效状态": "status_from_source",
        "废止记录": "affected_items_text",
        "时效性": "status_from_source",
    }

    # 方法1: 查找 tr 中的标签-值对
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).replace("：", "").replace(":", "").strip()
            value = cells[1].get_text(strip=True)
            # 尝试匹配
            for known_label, key_name in field_map.items():
                if known_label in label or label == known_label:
                    if not result.get(key_name):
                        result[key_name] = value
                        break

    # 方法2: 查找 dl/dt/dd 结构
    if not result["title"]:
        for dt in soup.find_all(["dt", "th"]):
            label = dt.get_text(strip=True).replace("：", "").replace(":", "").strip()
            for known_label, key_name in field_map.items():
                if known_label in label:
                    dd = dt.find_next_sibling(["dd", "td"])
                    if dd:
                        value = dd.get_text(strip=True)
                        if not result.get(key_name):
                            result[key_name] = value
                        break

    # 方法3: 查找 span.label + span.value 结构（自然资源部详情页常见）
    if not result["title"]:
        # 查找 class 中包含 label/value 等词的元素
        for span in soup.find_all("span", class_=_re.compile(r"label|key|field", _re.I)):
            label = span.get_text(strip=True).replace("：", "").replace(":", "").strip()
            for known_label, key_name in field_map.items():
                if known_label in label:
                    next_val = span.find_next("span")
                    if next_val:
                        value = next_val.get_text(strip=True)
                        if not result.get(key_name):
                            result[key_name] = value
                        break

    # 方法4: 从 meta 标签提取标题
    if not result["title"]:
        for meta_tag in soup.find_all("meta"):
            if meta_tag.get("name", "").lower() in ("title", "dc.title"):
                result["title"] = meta_tag.get("content", "")
                break

    # 2. 从页面标题/标题标签提取标题（兜底）
    if not result["title"]:
        title_tag = soup.find("title")
        if title_tag:
            t = title_tag.get_text(strip=True)
            # 去掉网站后缀
            t = _re.sub(r"[_\-—|｜].*$", "", t)
            if len(t) >= 4:
                result["title"] = t

    # 也尝试从 h1 提取
    if not result["title"]:
        h1 = soup.find("h1")
        if h1:
            t = h1.get_text(strip=True)
            if 4 <= len(t) <= 200:
                result["title"] = t

    # 3. 提取正文
    main = soup.find("article") or soup.find("main") or soup.find(
        "div", class_=_re.compile(r"content|article|main|body|text|TRS_Editor", _re.I))
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    result["full_text"] = "\n".join(lines)

    # 4. 日期格式化
    for date_field in ["pass_date", "publish_date", "source_publish_date"]:
        v = result.get(date_field, "")
        if v:
            # 中文日期：2026年6月5日
            m = _re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", v)
            if m:
                result[date_field] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                continue
            # ISO日期：2026-06-05
            m = _re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
            if m:
                result[date_field] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 5. 从正文提取发布机构（如果表格没有）
    if not result["issuing_authority"] and result["full_text"]:
        result["issuing_authority"] = _extract_issuing_authority_from_text(
            result["full_text"]
        )

    # 6. 如果页面有 source_publish_date 但没有 publish_date，尝试从标题中的日期推断
    if not result["publish_date"] and not result["source_publish_date"]:
        # 从 URL 中提取日期（自然资源部 URL 格式：/202606/t20260605_xxx.html）
        date_from_url = _re.search(r"/(\d{4})(\d{2})(\d{2})/", url)
        if not date_from_url:
            date_from_url = _re.search(r"/t(\d{4})(\d{2})(\d{2})", url)
        if date_from_url:
            y, mo, d = date_from_url.groups()
            date_str = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
            result["source_publish_date"] = date_str
            if not result["publish_date"]:
                result["publish_date"] = date_str

    # 7. 候选类型推断
    full_text_for_type = (result.get("title", "") + " " + result.get("full_text", ""))[:500]
    if any(kw in full_text_for_type for kw in ["废止", "予以废止", "同时废止"]):
        result["candidate_type_hint"] = "废止决定"
    elif "失效" in full_text_for_type:
        result["candidate_type_hint"] = "失效公告"
    elif "修改" in full_text_for_type or "修订" in full_text_for_type:
        result["candidate_type_hint"] = "修订公告"

    # 8. 解析警告
    if not result["title"]:
        result["parse_warning"] = "未能从页面提取标题"
    if not result["document_no"]:
        result["parse_warning"] = (result["parse_warning"] + "；未提取到文号").strip("；")

    return result


def _extract_issuing_authority_from_text(text: str) -> str:
    """从正文中提取发布机构。"""
    if not text:
        return ""
    # 匹配"自然资源部"等常见发文机构
    m = re.search(r"(自然资源部|农业农村部|生态环境部|交通运输部|水利部"
                  r"|国务院|全国人大|全国人大常委会|最高人民法院|最高人民检察院"
                  r"|国家发展和改革委员会|国家市场监督管理总局)", text[:200])
    if m:
        return m.group(1)
    return ""


def extract_obsolete_items_from_text(text: str) -> list[dict]:
    """从废止公告/决定正文中提取被废止、失效、替代的旧文件列表。

    识别编号形式：一、二、三、1. 2. （一）（二） - ● 等后跟《xxx》的模式。

    改进：
    - 更好地处理中文括号对
    - 支持从编号行和后续行中提取文件信息
    - 文号识别更鲁棒
    """
    import re as _re

    if not text:
        return []

    items = []
    full_text = text
    seen_titles = set()

    # 编码前缀：中文序号、阿拉伯数字、括号序号、破折号等
    number_prefixes = (
        r"(?:[一二三四五六七八九十]+[、．]\s*"
        r"|[（(][一二三四五六七八九十\d]+[)）]\s*"
        r"|\d+[.、．]\s*"
        r"|[—\-—●•·]\s*)"
    )

    # 模式1: 编号 + 《标题》 + （可选信息）
    # 注意: info 部分需要排除下一个编号项的情况
    pattern1 = _re.compile(
        number_prefixes
        + r"《(?P<title>[^》]{2,80})》"
        + r"(?:\s*[（(](?P<info>(?!\s*[一二三四五六七八九十\d]+[)）])[^)）\n]{0,300})[)）])?"
    )

    for m in pattern1.finditer(full_text):
        title = m.group("title").strip()
        info = (m.group("info") or "").strip()

        # 过滤无效标题
        if not title or len(title) < 3:
            continue
        if title in seen_titles:
            continue
        # 过滤明显不是文件名的内容
        if re.match(r"^[\d\s\.\-_,，、。；;：:]+$", title):
            continue

        seen_titles.add(title)

        doc_no = ""
        publish_date = ""

        if info:
            # 文号: 国土资源部令第7号, 自然资源部令第21号
            # 注意: (?:[年月日]|^) 确保不把日期字符（如"日"）捕获到机构名中
            no_m = _re.search(r"(?:[年月日]|^)([一-鿿]{2,12}令第\d+号)", info)
            if not no_m:
                # 发文字号格式: 自然资发〔2024〕204号
                no_m = _re.search(
                    r"([一-鿿A-Za-z]{2,12}(?:发|办发|函|规字)\s*[〔\(（\[]?\d{4}[〕\)）\]]?\d+号?)", info
                )
            if no_m:
                doc_no = no_m.group(1).strip()

            # 日期: 2001年7月25日
            date_m = _re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", info)
            if date_m:
                publish_date = (
                    f"{int(date_m.group(1)):04d}-"
                    f"{int(date_m.group(2)):02d}-"
                    f"{int(date_m.group(3)):02d}"
                )

        items.append({
            "old_title": title,
            "old_document_no": doc_no,
            "old_publish_date": publish_date,
            "relation_type": "废止",
            "basis_text": m.group(0).strip()[:300],
            "source_candidate_url": "",
        })

    # 模式2: 如果在文本中没找到带编号的《》，尝试直接匹配《xxx》后面跟括号信息
    if not items:
        pattern2 = _re.compile(
            r"《(?P<title>[^》]{3,80})》"
            r"\s*[（(]?(?P<info>[^)）]{0,300})[)）]?"
        )
        for m in pattern2.finditer(full_text):
            title = m.group("title").strip()
            info = (m.group("info") or "").strip()

            if title in seen_titles:
                continue
            seen_titles.add(title)

            doc_no = ""
            publish_date = ""

            if info:
                no_m = _re.search(r"(?:[年月日]|^)([一-鿿]{2,12}令第\d+号)", info)
                if no_m:
                    doc_no = no_m.group(1).strip()
                date_m = _re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", info)
                if date_m:
                    publish_date = (
                        f"{int(date_m.group(1)):04d}-"
                        f"{int(date_m.group(2)):02d}-"
                        f"{int(date_m.group(3)):02d}"
                    )

            items.append({
                "old_title": title,
                "old_document_no": doc_no,
                "old_publish_date": publish_date,
                "relation_type": "废止",
                "basis_text": m.group(0).strip()[:300],
                "source_candidate_url": "",
            })

    return items


def match_affected_items_with_library(affected_items: list[dict]) -> list[dict]:
    """将 affected_items 与文件库匹配。

    为每个 item 添加 matched 字段。
    """
    import database.db as db

    for item in affected_items:
        old_title = item.get("old_title", "")
        old_no = item.get("old_document_no", "")

        # 1. 文号精确匹配
        if old_no:
            existing = db.get_document_by_no(old_no)
            if existing:
                item["matched"] = True
                item["matched_id"] = existing["id"]
                item["matched_title"] = existing["title"]
                item["match_method"] = "文号精确匹配"
                continue

        # 2. 标题精确匹配
        if old_title:
            existing = db.get_document_by_title(old_title)
            if existing:
                item["matched"] = True
                item["matched_id"] = existing["id"]
                item["matched_title"] = existing["title"]
                item["match_method"] = "标题精确匹配"
                continue

        # 3. 模糊匹配
        if old_title and len(old_title) >= 8:
            all_titles = db.get_all_titles()
            best = None
            for doc in all_titles:
                doc_title = doc.get("title", "")
                if doc_title and (old_title in doc_title or doc_title in old_title):
                    best = doc
                    break
            if best:
                item["matched"] = True
                item["matched_id"] = best["id"]
                item["matched_title"] = best["title"]
                item["match_method"] = "标题模糊匹配"
                continue

        item["matched"] = False
        item["matched_id"] = None
        item["matched_title"] = ""
        item["match_method"] = ""

    return affected_items


def fetch_candidate_detail(url: str, source: dict) -> dict | None:
    """抓取候选详情页"""
    import requests
    from bs4 import BeautifulSoup

    domain = source.get("domain", "")
    allowed_domains = [domain]

    safe, _ = _check_safe_url(url, allowed_domains)
    if not safe:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return None

    # 限制响应大小
    if len(resp.content) > 2 * 1024 * 1024:
        return None

    html = decode_response_content(resp)
    soup = BeautifulSoup(html, "html.parser")
    text = _extract_main_text(soup)
    if not text:
        return None

    from modules.metadata_extractor import extract_all_metadata
    meta = extract_all_metadata(text)

    keywords_found = detect_obsolete_keywords(text)
    relation_text = detect_relation_basis(text)
    relation_guess = guess_relation_type(keywords_found, text)

    # 匹配已有文件
    match_result = match_existing_documents(
        title=meta.get("title", ""),
        document_no=meta.get("document_no", ""),
        text=text,
    )

    return {
        "title": meta.get("title", ""),
        "document_no": meta.get("document_no", ""),
        "publish_date": meta.get("publish_date", ""),
        "source_publish_date": "",
        "summary": text[:500] if text else "",
        "full_text": text,
        "candidate_type": "废止公告" if "废止" in (meta.get("title", "") + text[:200])
        else ("失效目录" if "失效" in (meta.get("title", "") + text[:200]) else "其他"),
        "relation_type_guess": relation_guess,
        "relation_basis_text": relation_text,
        "matched_document_id": match_result.get("matched_id"),
        "matched_title": match_result.get("matched_title", ""),
        "confidence": match_result.get("match_method", ""),
        "status": "已抓取待确认",
    }


def _extract_main_text(soup) -> str:
    """从网页提取正文"""
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.find(
        "div", class_=re.compile(r"(content|article|main|body|text)", re.I))
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)
