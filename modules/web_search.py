"""网络搜索模块：在线搜索政策文件"""

import concurrent.futures
import requests


def _search_duckduckgo(query: str, max_results: int = 10) -> list[dict]:
    """通过 DuckDuckGo 搜索"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return []

    results = []
    try:
        with DDGS(timeout=10) as ddgs:
            for r in ddgs.text(f"{query} 政策 文件", max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                    "source": "DuckDuckGo",
                })
    except Exception:
        pass
    return results


def _search_baidu(query: str, max_results: int = 10) -> list[dict]:
    """通过百度搜索（国内优先）"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    try:
        url = f"https://www.baidu.com/s?wd={requests.utils.quote(query + ' 政策 文件')}&rn={max_results}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select(".result, .c-container")[:max_results]:
            title_el = item.select_one("h3 a")
            snippet_el = item.select_one(".c-abstract, .c-span-last, .content-right_8Zs40")
            if title_el:
                href = title_el.get("href", "")
                # 百度结果链接可能是跳转链接
                title_text = title_el.get_text(strip=True)
                if title_text and href:
                    results.append({
                        "title": title_text,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                        "url": href,
                        "source": "百度",
                    })
    except requests.Timeout:
        pass
    except Exception:
        pass
    return results


def _search_bing(query: str, max_results: int = 10) -> list[dict]:
    """通过 Bing 搜索"""
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    try:
        url = f"https://www.bing.com/search?q={requests.utils.quote(query + ' 政策 文件')}&count={max_results}"
        resp = requests.get(url, headers=headers, timeout=10)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select("li.b_algo")[:max_results]:
            title_el = item.select_one("h2 a")
            snippet_el = item.select_one(".b_caption p, .b_lineclamp2")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    "url": title_el.get("href", ""),
                    "source": "Bing",
                })
    except requests.Timeout:
        pass
    except Exception:
        pass
    return results


def _run_engine(name, func, query, max_results):
    """在独立线程中运行一个搜索引擎"""
    try:
        results = func(query, max_results)
        return (name, results)
    except Exception:
        return (name, [])


def search_policy_online(query: str, max_results: int = 10) -> list[dict]:
    """在线搜索政策文件。国内优先：百度 → Bing → DuckDuckGo
    使用线程超时防止卡死"""
    if not query or len(query) < 2:
        return []

    # 国内用户优先使用百度
    engines = [
        ("baidu", _search_baidu),
        ("bing", _search_bing),
        ("duckduckgo", _search_duckduckgo),
    ]

    all_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        for name, func in engines:
            future = executor.submit(_run_engine, name, func, query, max_results)
            try:
                name, results = future.result(timeout=12)
                if results:
                    return results
            except concurrent.futures.TimeoutError:
                continue
            except Exception:
                continue

    return all_results


def fetch_policy_content(url: str) -> dict:
    """抓取政策文件网页内容"""
    from modules.document_parser import fetch_from_url

    result = fetch_from_url(url)
    return {
        "text": result.get("text", ""),
        "title": result.get("file_name", ""),
        "error": result.get("error"),
    }
