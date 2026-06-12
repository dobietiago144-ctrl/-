"""测试政策废止监测模块 — 乱码修复、详情页解析、旧文件提取"""

import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from modules.policy_monitor import (
    decode_response_content,
    _evaluate_chinese_quality,
    parse_mnr_policy_library_detail,
    extract_obsolete_items_from_text,
    is_allowed_mnr_url,
    detect_obsolete_keywords,
)


class TestDecodeResponseContent:
    """测试网页内容解码"""

    def test_utf8_html_decodes_correctly(self):
        """UTF-8编码的中文网页应该正确解码"""
        content = "<html><head><title>自然资源部关于第八批废止的部门规章的决定</title></head><body><p>测试内容</p></body></html>".encode("utf-8")

        class FakeResp:
            pass

        resp = FakeResp()
        resp.content = content
        resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        resp.apparent_encoding = "utf-8"

        result = decode_response_content(resp)
        assert "自然资源部关于第八批废止的部门规章的决定" in result
        assert "测试内容" in result
        assert "è" not in result  # 无乱码
        assert "æ" not in result
        assert "å" not in result

    def test_gb2312_decoded_as_utf8_produces_mojibake(self):
        """GB2312编码用UTF-8解码会产生乱码，应被检测并修正"""
        text = "自然资源部关于第八批废止的部门规章的决定"
        content = text.encode("gb2312")

        class FakeResp:
            pass

        resp = FakeResp()
        resp.content = content
        resp.headers = {"Content-Type": "text/html"}
        resp.apparent_encoding = "gb2312"

        result = decode_response_content(resp)
        # 应该正确解码
        assert "自然资源部" in result
        # 不应该有大量乱码字符
        assert result.count("�") < 5

    def test_gbk_content_with_wrong_header(self):
        """GBK编码但header标注为UTF-8的页面应该被正确解码"""
        text = "关于废止部分规范性文件的决定"
        content = text.encode("gbk")

        class FakeResp:
            pass

        resp = FakeResp()
        resp.content = content
        resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        resp.apparent_encoding = "utf-8"

        result = decode_response_content(resp)
        assert "废止" in result
        assert result.count("�") < 3

    def test_gb18030_content(self):
        """GB18030编码的中文应该正确解码"""
        text = "自然资源部办公厅关于进一步规范用地审批工作的通知"
        content = text.encode("gb18030")

        class FakeResp:
            pass

        resp = FakeResp()
        resp.content = content
        resp.headers = {"Content-Type": "text/html"}
        resp.apparent_encoding = "gb18030"

        result = decode_response_content(resp)
        assert "自然资源部" in result


class TestChineseQuality:
    """测试中文质量评估"""

    def test_good_chinese_scores_high(self):
        """正常中文文本得分高"""
        text = "自然资源部关于第八批废止的部门规章的决定 一、《建设项目用地预审管理办法》"
        score = _evaluate_chinese_quality(text)
        assert score >= 90

    def test_mojibake_scores_low(self):
        """西欧乱码文本得分低"""
        text = "èèèæææååå china government document"
        score = _evaluate_chinese_quality(text)
        assert score < 40

    def test_replacement_chars_scores_low(self):
        """包含替换字符的文本得分低"""
        text = "���关于废止��文件的决定���"
        score = _evaluate_chinese_quality(text)
        assert score < 40

    def test_empty_text(self):
        """空文本得分为0"""
        assert _evaluate_chinese_quality("") == 0


class TestParseMnrPolicyLibraryDetail:
    """测试自然资源部详情页解析"""

    def test_extract_title_from_tr_table(self):
        """从表格行提取标题"""
        html = """
        <html><body>
        <table>
        <tr><td>名称：</td><td>自然资源部关于第八批废止的部门规章的决定</td></tr>
        <tr><td>文号：</td><td>中华人民共和国自然资源部令第21号</td></tr>
        <tr><td>发布机构：</td><td>自然资源部</td></tr>
        <tr><td>发布日期：</td><td>2026年6月5日</td></tr>
        <tr><td>时效状态：</td><td>现行有效</td></tr>
        </table>
        <div class="content">
        一、《建设项目用地预审管理办法》（2001年7月25日国土资源部令第7号发布）
        二、《海洋行政处罚实施办法》（2002年12月25日国土资源部令第15号发布）
        </div>
        </body></html>
        """
        result = parse_mnr_policy_library_detail(html)
        assert "自然资源部关于第八批废止的部门规章的决定" in result["title"]
        assert result["document_no"] == "中华人民共和国自然资源部令第21号"
        assert result["issuing_authority"] == "自然资源部"
        assert result["status_from_source"] == "现行有效"

    def test_extract_date_from_tr_table(self):
        """日期字段正确提取和格式化"""
        html = """
        <html><body>
        <table>
        <tr><td>发布日期：</td><td>2026年6月5日</td></tr>
        </table>
        </body></html>
        """
        result = parse_mnr_policy_library_detail(html)
        assert result["publish_date"] == "2026-06-05"

    def test_extract_from_html_title_fallback(self):
        """当表格没有标题时，从 <title> 标签提取"""
        html = """
        <html><head><title>自然资源部关于第八批废止的部门规章的决定</title></head>
        <body></body></html>
        """
        result = parse_mnr_policy_library_detail(html)
        assert "自然资源部关于第八批废止的部门规章的决定" in result["title"]

    def test_no_garbled_title(self):
        """确保标题不乱码"""
        # 模拟一个常见乱码场景
        html = """
        <html><head><meta charset="utf-8"><title>自然资源部关于第八批废止的部门规章的决定</title></head>
        <body>
        <table>
        <tr><td>名称</td><td>自然资源部关于第八批废止的部门规章的决定</td></tr>
        </table>
        </body></html>
        """
        result = parse_mnr_policy_library_detail(html)
        garbled_chars = ["è", "æ", "å", "¤"]
        for gc in garbled_chars:
            assert gc not in result["title"], f"标题包含乱码字符: {gc}"

    def test_candidate_type_hint(self):
        """根据标题推断候选类型"""
        html = """
        <html><body>
        <table>
        <tr><td>名称</td><td>自然资源部关于第八批废止的部门规章的决定</td></tr>
        </table>
        <div class="content">废止以下部门规章</div>
        </body></html>
        """
        result = parse_mnr_policy_library_detail(html)
        assert result["candidate_type_hint"] == "废止决定"


class TestExtractObsoleteItems:
    """测试从正文提取被废止旧文件"""

    def test_extract_numbered_items(self):
        """提取编号列表中的废止文件"""
        text = """
        自然资源部决定废止下列部门规章：
        一、《建设项目用地预审管理办法》（2001年7月25日国土资源部令第7号发布）
        二、《海洋行政处罚实施办法》（2002年12月25日国土资源部令第15号发布）
        三、《国土资源行政复议规定》（2001年7月27日国土资源部令第8号发布）
        """
        items = extract_obsolete_items_from_text(text)
        assert len(items) >= 2

        titles = [i["old_title"] for i in items]
        assert "建设项目用地预审管理办法" in titles
        assert "海洋行政处罚实施办法" in titles

    def test_extract_document_no(self):
        """提取文号"""
        text = "一、《建设项目用地预审管理办法》（2001年7月25日国土资源部令第7号发布）"
        items = extract_obsolete_items_from_text(text)
        assert len(items) >= 1
        assert items[0]["old_title"] == "建设项目用地预审管理办法"
        assert items[0]["old_document_no"] == "国土资源部令第7号"

    def test_extract_publish_date(self):
        """提取发布日期"""
        text = "一、《海洋行政处罚实施办法》（2002年12月25日国土资源部令第15号发布）"
        items = extract_obsolete_items_from_text(text)
        assert len(items) >= 1
        assert items[0]["old_publish_date"] == "2002-12-25"

    def test_dedup_titles(self):
        """去重相同标题"""
        text = """
        一、《建设项目用地预审管理办法》
        二、《建设项目用地预审管理办法》
        """
        items = extract_obsolete_items_from_text(text)
        assert len(items) == 1

    def test_extract_without_parentheses(self):
        """提取没有括号信息的文件（至少提取 old_title）"""
        text = "一、《某管理办法》"
        items = extract_obsolete_items_from_text(text)
        assert len(items) >= 1
        assert items[0]["old_title"] == "某管理办法"
        assert "basis_text" in items[0]

    def test_arabic_numbered_items(self):
        """支持数字编号"""
        text = "1.《文件A》 2.《文件B》"
        items = extract_obsolete_items_from_text(text)
        assert len(items) >= 2
        titles = [i["old_title"] for i in items]
        assert "文件A" in titles
        assert "文件B" in titles

    def test_parenthesized_numbered_items(self):
        """支持括号编号"""
        text = "（一）《文件A》（二）《文件B》"
        items = extract_obsolete_items_from_text(text)
        assert len(items) >= 2


class TestIsAllowedMnrUrl:
    """测试URL域名白名单"""

    def test_allowed_domains(self):
        assert is_allowed_mnr_url("https://www.mnr.gov.cn/") is True
        assert is_allowed_mnr_url("https://f.mnr.gov.cn/202606/t20260605_2931308.html") is True
        assert is_allowed_mnr_url("https://gk.mnr.gov.cn/") is True
        assert is_allowed_mnr_url("https://gi.mnr.gov.cn/") is True
        assert is_allowed_mnr_url("https://mnr.gov.cn/") is True

    def test_blocked_domains(self):
        assert is_allowed_mnr_url("https://localhost:8080/") is False
        assert is_allowed_mnr_url("https://127.0.0.1/") is False
        assert is_allowed_mnr_url("https://example.com/") is False


class TestDetectKeywords:
    """测试关键词检测"""

    def test_detect_abolish_keywords(self):
        text = "自然资源部关于废止部分规章的决定予以废止下列文件"
        found = detect_obsolete_keywords(text)
        assert "废止" in found
        assert "予以废止" in found

    def test_detect_expired_keywords(self):
        text = "以下规范性文件已失效有效期届满"
        found = detect_obsolete_keywords(text)
        assert "失效" in found
        assert "已失效" in found

    def test_no_keywords(self):
        text = "自然资源部关于加强用地管理的通知"
        found = detect_obsolete_keywords(text)
        # 修改、修订 也是关键词
        # 通知不一定是监测关键词
        assert "废止" not in found
        assert "失效" not in found
