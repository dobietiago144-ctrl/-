"""网络搜索模块：在线搜索政策文件"""

import requests


# 搜索引擎优先顺序
SEARCH_ENGINES = ["duckduckgo", "bing"]


def _search_duckduckgo(query: str, max_results: int = 10) -> list[dict]:
    """通过 DuckDuckGo 搜索"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(f"{query} 政策 文件 site:gov.cn", max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                    "source": "DuckDuckGo",
                })
    except Exception:
        pass
    return results


def _search_bing(query: str, max_results: int = 10) -> list[dict]:
    """通过 Bing 搜索（无 API Key 时用网页抓取）"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        url = f"https://www.bing.com/search?q={requests.utils.quote(query + ' 政策 文件')}&count={max_results}"
        resp = requests.get(url, headers=headers, timeout=15)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select("li.b_algo")[:max_results]:
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one(".b_caption p")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    "url": title_el.get("href", ""),
                    "source": "Bing",
                })
    except Exception:
        pass
    return results


def _search_baidu(query: str, max_results: int = 10) -> list[dict]:
    """通过百度搜索"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        url = f"https://www.baidu.com/s?wd={requests.utils.quote(query + ' 政策 文件')}&rn={max_results}"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select(".result, .c-container")[:max_results]:
            title_el = item.select_one("h3 a")
            snippet_el = item.select_one(".c-abstract, .content-right_8Zs40")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    "url": title_el.get("href", ""),
                    "source": "百度",
                })
    except Exception:
        pass
    return results


def search_policy_online(query: str, max_results: int = 10) -> list[dict]:
    """在线搜索政策文件，返回结果列表 [{"title","snippet","url","source"}]"""
    if not query or len(query) < 2:
        return []

    # 按优先级尝试各搜索引擎
    engines = [
        ("duckduckgo", _search_duckduckgo),
        ("bing", _search_bing),
        ("baidu", _search_baidu),
    ]

    for name, func in engines:
        try:
            results = func(query, max_results)
            if results:
                return results
        except Exception:
            continue

    return []


def fetch_policy_content(url: str) -> dict:
    """抓取政策文件网页内容，返回 {"text","title","error"}"""
    from modules.document_parser import fetch_from_url

    result = fetch_from_url(url)
    return {
        "text": result.get("text", ""),
        "title": result.get("file_name", ""),
        "error": result.get("error"),
    }
