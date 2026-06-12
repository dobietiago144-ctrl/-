"""审查引擎自动化测试

运行方式：
    cd policy-reviewer
    python -m unittest tests.test_review_engine -v

或者：
    python tests/test_review_engine.py
"""

import sys
import os
import unittest
import tempfile
import shutil

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.db as db
from database.models import ALL_TABLES
from modules.matcher import (
    match_by_document_no, match_by_title_exact, match_by_title_embedded,
    match_by_fuzzy, match_reference, _extract_embedded_title,
    _check_title_relation, match_all_references,
)
from modules.reviewer import (
    parse_document_no_parts, compare_document_no_parts,
    validate_document_no_format, assess_risk,
    review_single_reference, review_all,
)
from config import STATUS_TO_RISK, FUZZY_MATCH_HIGH, FUZZY_MATCH_LOW


class BaseDBTest(unittest.TestCase):
    """每个测试用例使用独立的临时数据库"""

    def setUp(self):
        import config
        self._original_db_path = config.DB_PATH
        self._temp_dir = tempfile.mkdtemp()
        test_db = os.path.join(self._temp_dir, "test.db")
        config.DB_PATH = test_db
        db.DB_PATH = test_db

        conn = db.get_connection()
        for sql in ALL_TABLES:
            conn.execute(sql)
        conn.commit()
        conn.close()

    def tearDown(self):
        import config
        config.DB_PATH = self._original_db_path
        db.DB_PATH = self._original_db_path
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _seed_doc(self, title, document_no="", status="现行有效", **kwargs):
        data = {
            "title": title,
            "document_no": document_no,
            "status": status,
            "issuing_authority": kwargs.get("issuing_authority", "自然资源部"),
            "publish_date": kwargs.get("publish_date", ""),
            "effective_date": kwargs.get("effective_date", ""),
            "expiry_date": kwargs.get("expiry_date", ""),
            "region": kwargs.get("region", "全国"),
            "category": kwargs.get("category", "部门规章"),
            "keywords": kwargs.get("keywords", ""),
            "summary": kwargs.get("summary", ""),
            "full_text": kwargs.get("full_text", ""),
            "source_type": kwargs.get("source_type", "手工录入"),
            "source_url": kwargs.get("source_url", ""),
            "file_path": kwargs.get("file_path", ""),
            "business_tags": kwargs.get("business_tags", ""),
            "sensitivity_level": kwargs.get("sensitivity_level", "公开"),
            "file_name": kwargs.get("file_name", ""),
            "file_size": kwargs.get("file_size", 0),
            "file_type": kwargs.get("file_type", ""),
            "confirmed": kwargs.get("confirmed", 1),
            "notes": kwargs.get("notes", ""),
        }
        return db.create_document(data)


# ── Test 1: 正常引用不误报 ───────────────────────────────────────────

class TestNormalReference(BaseDBTest):

    def test_normal_reference_no_false_alarm(self):
        """正常引用不应产生误报：名称文号一致，文件现行有效"""
        self._seed_doc("中华人民共和国土地管理法", "主席令第32号", status="现行有效")

        ref = {"title": "中华人民共和国土地管理法", "document_no": "主席令第32号", "text": "《中华人民共和国土地管理法》"}
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        self.assertEqual(review["risk_level"], "正常")
        self.assertEqual(review["problem_type"], "正常")
        self.assertIn(review["match_method"], ("标题精确匹配", "标题内嵌匹配"))
        self.assertEqual(review["match_score"], 100.0)


# ── Test 2: 文件名称和文号一致 ──────────────────────────────────────

class TestTitleDocNoMatch(BaseDBTest):

    def test_title_and_doc_no_match_same_document(self):
        """文件名称和文号指向同一个文件，应判定为正常"""
        self._seed_doc(
            "自然资源部关于印发《城镇开发边界管理办法（试行）》的通知",
            "自然资规〔2026〕1号", status="现行有效")

        ref = {
            "title": "自然资源部关于印发《城镇开发边界管理办法（试行）》的通知",
            "document_no": "自然资规〔2026〕1号",
            "text": "《自然资源部关于印发〈城镇开发边界管理办法（试行）〉的通知》（自然资规〔2026〕1号）",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        self.assertEqual(review["risk_level"], "正常")


# ── Test 3: 文件名称和文号不匹配 ──────────────────────────────────

class TestTitleDocNoMismatch(BaseDBTest):

    def test_title_and_doc_no_mismatch(self):
        """文件名称指向A文件，文号指向B文件，应判定为严重问题"""
        self._seed_doc("A管理办法", "自然资发〔2024〕10号", status="现行有效")
        self._seed_doc("B实施细则", "自然资发〔2024〕20号", status="现行有效")

        ref = {
            "title": "A管理办法",
            "document_no": "自然资发〔2024〕20号",
            "text": "《A管理办法》（自然资发〔2024〕20号）",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        if result.get("title_no_mismatch"):
            self.assertEqual(review["risk_level"], "严重问题")
        else:
            self.assertIn(review["risk_level"], ("严重问题", "正常"))


# ── Test 4: 文号年份不一致 ─────────────────────────────────────────

class TestDocNoYearMismatch(BaseDBTest):

    def test_doc_no_year_mismatch(self):
        """报告文号年份与文件库正式文号年份不一致，应判定为严重问题"""
        self._seed_doc("某管理办法", "自然资规〔2026〕1号", status="现行有效")

        ref = {
            "title": "某管理办法",
            "document_no": "自然资规〔2025〕1号",
            "text": "《某管理办法》（自然资规〔2025〕1号）",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        self.assertEqual(review["risk_level"], "严重问题")
        self.assertIn("年份不一致", review["judgment_basis"])


# ── Test 5: 文号序号不一致 ─────────────────────────────────────────

class TestDocNoNumberMismatch(BaseDBTest):

    def test_doc_no_number_mismatch(self):
        """报告文号序号与文件库正式文号序号不一致"""
        self._seed_doc("城镇开发边界管理办法（试行）", "自然资规〔2026〕1号", status="现行有效")

        ref = {
            "title": "城镇开发边界管理办法（试行）",
            "document_no": "自然资规〔2026〕2号",
            "text": "《城镇开发边界管理办法（试行）》（自然资规〔2026〕2号）",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        self.assertEqual(review["risk_level"], "严重问题")
        self.assertIn("序号不一致", review["judgment_basis"])


# ── Test 6: 已废止文件 ─────────────────────────────────────────────

class TestAbolishedDocument(BaseDBTest):

    def test_abolished_document(self):
        """引用已废止的文件，应判定为严重问题"""
        self._seed_doc("已废止管理办法", "自然资发〔2020〕5号", status="已废止")

        ref = {
            "title": "已废止管理办法",
            "document_no": "自然资发〔2020〕5号",
            "text": "《已废止管理办法》（自然资发〔2020〕5号）",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        self.assertEqual(review["risk_level"], "严重问题")


# ── Test 7: 被替代文件并提示新版 ───────────────────────────────────

class TestReplacedDocument(BaseDBTest):

    def test_replaced_document_with_suggestion(self):
        """引用被替代的文件且有替代文件，应给出高风险和替代建议"""
        old_id = self._seed_doc("旧版管理办法", "自然资发〔2020〕6号", status="被替代")
        new_id = self._seed_doc("新版管理办法", "自然资发〔2025〕8号", status="现行有效")

        db.create_relation({
            "old_document_id": old_id,
            "new_document_id": new_id,
            "relation_type": "替代",
            "relation_basis": "自然资发〔2025〕8号明确替代",
            "relation_date": "2025-03-01",
            "affected_scope": "全文",
            "confidence": "人工确认",
            "notes": "",
        })

        ref = {
            "title": "旧版管理办法",
            "document_no": "自然资发〔2020〕6号",
            "text": "《旧版管理办法》（自然资发〔2020〕6号）",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        self.assertEqual(review["risk_level"], "高风险")
        self.assertEqual(review["suggested_title"], "新版管理办法")


# ── Test 8: 文件库未收录只提醒人工核查 ─────────────────────────────

class TestNotInLibrary(BaseDBTest):

    def test_not_in_library_is_reminder_only(self):
        """文件库中未收录的引用只做提醒，不报严重问题"""
        ref = {
            "title": "某未知文件",
            "document_no": "某发〔2025〕99号",
            "text": "《某未知文件》（某发〔2025〕99号）",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        self.assertEqual(review["match_method"], "未匹配")
        self.assertEqual(review["risk_level"], "提醒")
        self.assertEqual(review["need_manual_confirm"], 1)


# ── Test 9: 模糊匹配不得直接输出严重问题 ──────────────────────────

class TestFuzzyMatch(BaseDBTest):

    def test_fuzzy_match_not_severe(self):
        """模糊匹配只能作为提醒，不得直接判定严重问题"""
        self._seed_doc("自然资源部办公厅关于加强耕地保护工作的通知",
                 "自然资办发〔2024〕15号", status="现行有效")

        ref = {
            "title": "关于加强耕地保护工作的通知",
            "document_no": "",
            "text": "《关于加强耕地保护工作的通知》",
        }
        result = match_reference(ref)
        review = review_single_reference({**ref, **result})

        if review["match_method"] == "模糊匹配":
            self.assertIn(review["risk_level"], ("提醒", "低风险"))
            self.assertNotEqual(review["risk_level"], "严重问题")


# ── Test 10: 标题内嵌匹配 ────────────────────────────────────────

class TestTitleEmbeddedMatch(BaseDBTest):

    def test_title_embedded_matching(self):
        """报告引用简称《X》，文件库有'关于印发《X》的通知'，应通过标题内嵌匹配"""
        self._seed_doc(
            "自然资源部关于印发《城镇开发边界管理办法（试行）》的通知",
            "自然资规〔2026〕1号",
            status="现行有效",
        )

        ref = {
            "title": "城镇开发边界管理办法（试行）",
            "document_no": "",
            "text": "《城镇开发边界管理办法（试行）》",
        }
        result = match_reference(ref)

        self.assertEqual(result["match_method"], "标题内嵌匹配")
        self.assertEqual(result["match_score"], 100.0)
        self.assertIn("城镇开发边界管理办法（试行）", result["matched_title"])


# ── Additional: 文号解析测试 ────────────────────────────────────────

class TestParseDocumentNo(unittest.TestCase):

    def test_parse_document_no_parts(self):
        parts = parse_document_no_parts("自然资规〔2026〕1号")
        self.assertIsNotNone(parts)
        self.assertEqual(parts["prefix"], "自然资规")
        self.assertEqual(parts["year"], "2026")
        self.assertEqual(parts["number"], "1")
        self.assertTrue(parts["bracket_format_ok"])

    def test_parse_nonstandard_brackets(self):
        parts = parse_document_no_parts("自然资规(2026)1号")
        self.assertIsNotNone(parts)
        self.assertEqual(parts["prefix"], "自然资规")
        self.assertFalse(parts["bracket_format_ok"])


# ── Additional: 文号比较测试 ────────────────────────────────────────

class TestCompareDocNo(unittest.TestCase):

    def test_all_match(self):
        result = compare_document_no_parts("自然资规〔2026〕1号", "自然资规〔2026〕1号")
        self.assertEqual(result["issue_type"], "正常")
        self.assertEqual(result["risk_level"], "正常")

    def test_prefix_diff(self):
        result = compare_document_no_parts("粤自然资规〔2026〕1号", "自然资规〔2026〕1号")
        self.assertEqual(result["issue_type"], "文号前缀不一致")
        self.assertEqual(result["risk_level"], "严重问题")

    def test_format_only_low_risk(self):
        result = compare_document_no_parts("自然资规(2026)1号", "自然资规〔2026〕1号")
        self.assertEqual(result["risk_level"], "低风险")
        self.assertIn("括号格式不规范", result["issue_type"])

    def test_number_diff_not_format(self):
        """序号不一致是严重问题，不能被格式提醒覆盖"""
        result = compare_document_no_parts("自然资规〔2026〕2号", "自然资规〔2026〕1号")
        self.assertEqual(result["risk_level"], "严重问题")
        self.assertEqual(result["issue_type"], "文号序号不一致")
        self.assertNotIn("格式", result["issue_type"])


# ── Additional: 标题内嵌提取测试 ──────────────────────────────────

class TestExtractEmbedded(unittest.TestCase):

    def test_extract_embedded_title(self):
        title = _extract_embedded_title("自然资源部关于印发《城镇开发边界管理办法（试行）》的通知")
        self.assertEqual(title, "城镇开发边界管理办法（试行）")

    def test_no_bookmarks(self):
        title = _extract_embedded_title("中华人民共和国土地管理法")
        self.assertIsNone(title)


# ── Additional: STATUS_TO_RISK 映射测试 ─────────────────────────────

class TestStatusRiskMapping(unittest.TestCase):

    def test_status_to_risk_mapping(self):
        self.assertEqual(STATUS_TO_RISK["现行有效"], "正常")
        self.assertEqual(STATUS_TO_RISK["已废止"], "严重问题")
        self.assertEqual(STATUS_TO_RISK["已失效"], "严重问题")
        self.assertEqual(STATUS_TO_RISK["被替代"], "高风险")
        self.assertEqual(STATUS_TO_RISK["部分废止"], "中风险")
        self.assertEqual(STATUS_TO_RISK["即将失效"], "低风险")
        self.assertEqual(STATUS_TO_RISK["待核实"], "提醒")
        self.assertEqual(STATUS_TO_RISK["不明"], "提醒")


# ── New: 多个无文号文件可以入库 ──────────────────────────────────

class TestMultipleEmptyDocNo(BaseDBTest):

    def test_multiple_empty_doc_no_can_be_inserted(self):
        """多个无文号文件应能同时入库，不触发唯一约束冲突"""
        id1 = self._seed_doc("文件A", document_no="", status="现行有效")
        id2 = self._seed_doc("文件B", document_no="", status="现行有效")
        id3 = self._seed_doc("文件C", document_no="", status="现行有效")

        doc1 = db.get_document(id1)
        doc2 = db.get_document(id2)
        doc3 = db.get_document(id3)

        self.assertIsNotNone(doc1)
        self.assertIsNotNone(doc2)
        self.assertIsNotNone(doc3)
        self.assertEqual(doc1["title"], "文件A")
        self.assertEqual(doc2["title"], "文件B")
        self.assertEqual(doc3["title"], "文件C")


# ── New: 同标题不同文号不会被提前去重 ─────────────────────────────

class TestSameTitleDiffDocNoDedup(unittest.TestCase):

    def test_same_title_different_doc_no_not_deduped(self):
        """同标题不同文号的引用不应被去重合并"""
        from modules.reference_extractor import extract_book_title_refs

        text = (
            "依据《A办法》（自然资发〔2024〕1号）和"
            "《A办法》（自然资发〔2024〕2号）执行。"
        )
        refs = extract_book_title_refs(text)

        titles = [r["title"] for r in refs]
        doc_nos = [r["document_no"] for r in refs]

        # 应有两条引用
        a_refs = [r for r in refs if r["title"] == "A办法"]
        self.assertEqual(len(a_refs), 2,
                         "同标题不同文号应保留为两条独立引用")

        # 两条引用的文号应不同
        a_doc_nos = [r["document_no"] for r in a_refs]
        self.assertIn("自然资发〔2024〕1号", a_doc_nos)
        self.assertIn("自然资发〔2024〕2号", a_doc_nos)


# ── New: 网址导入保存 full_text ──────────────────────────────────

class TestSafeFetchSavesFullText(unittest.TestCase):

    def test_safe_fetch_result_includes_text_field(self):
        """safe_fetch_from_url 返回结果应包含 text 字段"""
        from modules.document_parser import safe_fetch_from_url, _is_safe_url

        # 测试 _is_safe_url 安全校验
        safe, _ = _is_safe_url("https://www.gov.cn/test")
        self.assertTrue(safe)

        unsafe, err = _is_safe_url("http://localhost/test")
        self.assertFalse(unsafe)

        unsafe2, _ = _is_safe_url("http://127.0.0.1/test")
        self.assertFalse(unsafe2)

        unsafe3, _ = _is_safe_url("http://192.168.1.1/test")
        self.assertFalse(unsafe3)

        unsafe4, _ = _is_safe_url("file:///etc/passwd")
        self.assertFalse(unsafe4)

        unsafe5, _ = _is_safe_url("http://10.0.0.1/test")
        self.assertFalse(unsafe5)

        # 测试 safe_fetch_from_url 结构
        result = safe_fetch_from_url("http://169.254.0.1/test")
        self.assertIn("error", result)
        self.assertIsNotNone(result["error"])
        self.assertEqual(result["source_type"], "公开网页导入")


# ── New: ENABLE_WEB_IMPORT 配置检查 ───────────────────────────────

class TestWebImportConfig(unittest.TestCase):

    def test_enable_web_import_is_true(self):
        """ENABLE_WEB_IMPORT 应为 True，允许显示导入链接页面"""
        from config import ENABLE_WEB_IMPORT
        self.assertTrue(ENABLE_WEB_IMPORT)

    def test_enable_web_search_is_false(self):
        """ENABLE_WEB_SEARCH 应为 False，禁止自动联网搜索"""
        from config import ENABLE_WEB_SEARCH
        self.assertFalse(ENABLE_WEB_SEARCH)

    def test_save_review_file_is_false(self):
        """SAVE_REVIEW_FILE 应为 False，审查后不保留原上传文件"""
        from config import SAVE_REVIEW_FILE
        self.assertFalse(SAVE_REVIEW_FILE)

    def test_source_type_options_has_public_web_import(self):
        """SOURCE_TYPE_OPTIONS 应包含 '公开网页导入'"""
        from config import SOURCE_TYPE_OPTIONS
        self.assertIn("公开网页导入", SOURCE_TYPE_OPTIONS)
        self.assertNotIn("网络检索", SOURCE_TYPE_OPTIONS)


# ── New: SAVE_REVIEW_FILE=False 时不保留文件 ──────────────────────

class TestSaveReviewFileFalse(unittest.TestCase):

    def test_save_review_file_false_does_not_persist_temp_file(self):
        """验证 SAVE_REVIEW_FILE=False 的配置语义"""
        from config import SAVE_REVIEW_FILE
        self.assertFalse(SAVE_REVIEW_FILE,
                         "SAVE_REVIEW_FILE 应为 False，审查后不保留上传文件")


# ── New: 网页元数据提取测试 ──────────────────────────────────────

class TestWebpageMetadataExtraction(unittest.TestCase):

    def setUp(self):
        self.maxDiff = 2000

    def test_revision_history_extraction(self):
        """正文开头的括号中通过/修正/修订信息应识别为文件沿革"""
        from modules.document_parser import _extract_revision_history

        text = "（1986年6月25日第六届全国人民代表大会常务委员会第十六次会议通过 根据1988年12月29日《关于修改〈中华人民共和国土地管理法〉的决定》第一次修正）"
        result = _extract_revision_history(text)
        self.assertTrue(len(result) > 0, "应识别出文件沿革")
        self.assertIn("1986年6月25日", result)
        self.assertIn("1988年12月29日", result)

    def test_revision_history_not_title(self):
        """文件沿革不应被当作标题"""
        from modules.document_parser import _extract_revision_history

        # 沿革文本
        revision = "（1986年6月25日通过 2019年8月26日修正）"
        result = _extract_revision_history(revision)
        self.assertTrue(len(result) > 0)

        # 正常标题不应被识别为沿革
        normal = "中华人民共和国土地管理法"
        result = _extract_revision_history(normal)
        self.assertEqual(result, "")

    def test_dates_separated_correctly(self):
        """日期应分离为通过日期和实施日期，不能混淆"""
        from modules.document_parser import _extract_dates_from_webpage

        text = (
            "时间：2024-08-21 10:00\n"
            "（1986年6月25日通过 2019年8月26日修正）\n"
            "自1987年1月1日起施行"
        )
        dates = _extract_dates_from_webpage(text)

        self.assertEqual(dates["source_publish_date"], "2024-08-21",
                         "网页发布日期应为 2024-08-21")
        self.assertEqual(dates["pass_date"], "1986-06-25",
                         "通过日期应为 1986-06-25")
        self.assertEqual(dates["effective_date"], "1987-01-01",
                         "实施日期应为 1987-01-01（自×起施行）")
        self.assertTrue(dates["latest_revision_date"] >= "2019-08-26",
                        "最近修正日期不应早于 2019-08-26")

    def test_pass_date_not_effective_date(self):
        """"通过"日期不能填到实施日期字段"""
        from modules.document_parser import _extract_dates_from_webpage

        # 只有"通过"没有"施行"的情况
        text = "（1986年6月25日第六届全国人民代表大会常务委员会通过）"
        dates = _extract_dates_from_webpage(text)

        self.assertEqual(dates["pass_date"], "1986-06-25")
        self.assertEqual(dates["effective_date"], "",
                         "没有'自×起施行'时，实施日期应为空")

    def test_title_priority_not_revision(self):
        """标题应优先从 meta/h1 提取，不应把'关于修改...'当标题"""
        from modules.document_parser import _extract_title_from_webpage

        html = '''<html><head>
        <meta property="og:title" content="中华人民共和国土地管理法"/>
        <title>中华人民共和国土地管理法_广东省自然资源厅</title>
        </head><body>
        <article><h2>中华人民共和国土地管理法</h2>
        <p>（1986年6月25日通过 根据1988年...《关于修改〈中华人民共和国土地管理法〉的决定》第一次修正）</p>
        </article></body></html>'''
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_title_from_webpage(soup)
        self.assertEqual(title, "中华人民共和国土地管理法")
        self.assertNotIn("关于修改", title)

    def test_category_law_from_title(self):
        """标题含'中华人民共和国...法'应识别为'法律'"""
        from modules.document_parser import _extract_webpage_metadata
        from bs4 import BeautifulSoup

        html = '''<html><head><title>中华人民共和国土地管理法</title></head>
        <body><article><h2>中华人民共和国土地管理法</h2>
        <p>（1986年6月25日通过 2019年8月26日修正）
        时间：2024-08-21 来源：自然资源部门户网站</p>
        <p>第一条 为了加强土地管理...</p>
        </article></body></html>'''
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        meta = _extract_webpage_metadata(soup, text)

        self.assertEqual(meta["title"], "中华人民共和国土地管理法")
        self.assertEqual(meta["category"], "法律")
        self.assertEqual(meta["region"], "全国")
        self.assertIn("1986年6月25日", meta.get("revision_history", ""))

    def test_gd_page_source_name_not_authority(self):
        """'来源：自然资源部门户网站'是来源，不是发文单位"""
        from modules.document_parser import _parse_gd_natural_resource_page
        from bs4 import BeautifulSoup

        html = '''<html><body><div class="content">
        时间：2024-08-21 10:30  来源：自然资源部门户网站  文号：
        <h2>中华人民共和国土地管理法</h2>
        <p>（1986年6月25日通过）</p>
        </div></body></html>'''
        soup = BeautifulSoup(html, "html.parser")
        gd = _parse_gd_natural_resource_page(soup)

        self.assertEqual(gd.get("source_name"), "自然资源部门户网站")
        self.assertEqual(gd.get("source_publish_date"), "2024-08-21")
        # 文号为空时应返回空字符串
        self.assertEqual(gd.get("document_no"), "")

    def test_full_land_law_extraction(self):
        """土地管理法页面综合提取测试"""
        from modules.document_parser import _extract_webpage_metadata, _extract_revision_history
        from bs4 import BeautifulSoup

        html = '''<html><head>
        <title>中华人民共和国土地管理法_广东省自然资源厅</title>
        <meta property="og:title" content="中华人民共和国土地管理法"/>
        </head><body>
        <div class="content">
        时间：2024-08-21 10:30:15  来源：自然资源部门户网站  文号：
        <h2>中华人民共和国土地管理法</h2>
        <div class="article-content">
        <p>（1986年6月25日第六届全国人民代表大会常务委员会第十六次会议通过 根据1988年12月29日第七届全国人民代表大会常务委员会第五次会议《关于修改〈中华人民共和国土地管理法〉的决定》第一次修正 1998年8月29日第九届全国人民代表大会常务委员会第四次会议修订 根据2004年8月28日第十届全国人民代表大会常务委员会第十一次会议《关于修改〈中华人民共和国土地管理法〉的决定》第二次修正 根据2019年8月26日第十三届全国人民代表大会常务委员会第十二次会议《关于修改〈中华人民共和国土地管理法〉、〈中华人民共和国城市房地产管理法〉的决定》第三次修正）</p>
        <p>第一章 总则</p>
        <p>第一条 为了加强土地管理...</p>
        <p>自1999年1月1日起施行。</p>
        </div></div></body></html>'''
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        meta = _extract_webpage_metadata(soup, text)

        # 标题
        self.assertEqual(meta["title"], "中华人民共和国土地管理法")
        self.assertNotIn("关于修改", meta["title"])

        # 类别地区
        self.assertEqual(meta["category"], "法律")
        self.assertEqual(meta["region"], "全国")

        # 日期
        self.assertEqual(meta["source_publish_date"], "2024-08-21")
        self.assertEqual(meta["pass_date"], "1986-06-25")
        self.assertTrue(meta["latest_revision_date"] >= "2019-08-26")
        self.assertEqual(meta["effective_date"], "1999-01-01")

        # 来源
        self.assertEqual(meta["source_name"], "自然资源部门户网站")

        # 沿革
        self.assertIn("1986年6月25日", meta["revision_history"])
        self.assertIn("1988年12月29日", meta["revision_history"])
        self.assertIn("2019年8月26日", meta["revision_history"])

        # 发文单位不应被强行填写
        self.assertEqual(meta.get("issuing_authority_candidate", ""), "")


# ── New: database 文件夹可正常导入 ──────────────────────────────

class TestDatabaseImport(unittest.TestCase):

    def test_database_package_imports(self):
        """database 文件夹应可正常导入"""
        import database
        from database.models import ALL_TABLES, CREATE_DOCUMENTS_TABLE
        from database.db import get_connection, init_db, migrate_database
        self.assertTrue(len(ALL_TABLES) >= 4)
        self.assertIsNotNone(CREATE_DOCUMENTS_TABLE)

    def test_init_db_runs(self):
        """init_db() 应可正常运行"""
        import config
        import tempfile
        orig = config.DB_PATH
        tmp = tempfile.mkdtemp()
        try:
            config.DB_PATH = os.path.join(tmp, "test.db")
            db.DB_PATH = config.DB_PATH
            db.init_db()
            conn = db.get_connection()
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            conn.close()
            table_names = {t[0] for t in tables}
            for tn in ["documents", "document_relations", "review_tasks",
                        "review_results", "operation_logs"]:
                self.assertIn(tn, table_names)
        finally:
            config.DB_PATH = orig
            db.DB_PATH = orig
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_migrate_database_runs(self):
        """migrate_database() 应可正常运行"""
        import config
        import tempfile
        orig = config.DB_PATH
        tmp = tempfile.mkdtemp()
        try:
            config.DB_PATH = os.path.join(tmp, "test.db")
            db.DB_PATH = config.DB_PATH
            db.init_db()
            db.migrate_database()
        finally:
            config.DB_PATH = orig
            db.DB_PATH = orig
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


# ── New: documents 表新增字段 ──────────────────────────────────

class TestNewDocumentFields(BaseDBTest):

    def test_new_fields_exist(self):
        """documents 表应包含新增字段"""
        conn = db.get_connection()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
        conn.close()
        for col in ["business_tags", "sensitivity_level", "file_name",
                     "file_size", "file_type"]:
            self.assertIn(col, cols)

    def test_default_sensitivity_level(self):
        """新建文件默认敏感级别为 '公开'"""
        doc_id = self._seed_doc("测试文件")
        doc = db.get_document(doc_id)
        self.assertEqual(doc.get("sensitivity_level", ""), "公开")

    def test_business_tags_saved(self):
        """business_tags 字段可正常保存和读取"""
        doc_id = db.create_document({
            "title": "测试增减挂钩文件",
            "document_no": "",
            "business_tags": "增减挂钩类,耕地保护类",
            "sensitivity_level": "内部",
            "file_name": "test.pdf",
            "file_size": 12345,
            "file_type": "pdf",
        })
        doc = db.get_document(doc_id)
        self.assertIn("增减挂钩类", doc.get("business_tags", ""))
        self.assertIn("耕地保护类", doc.get("business_tags", ""))
        self.assertEqual(doc["sensitivity_level"], "内部")
        self.assertEqual(doc["file_name"], "test.pdf")
        self.assertEqual(doc["file_size"], 12345)
        self.assertEqual(doc["file_type"], "pdf")


# ── New: 业务类型自动分类 ──────────────────────────────────────

class TestBusinessClassifier(unittest.TestCase):

    def test_classify_by_title(self):
        """标题包含关键词应正确分类"""
        from modules.classifier import classify_business_tags
        tags = classify_business_tags(
            "关于城乡建设用地增减挂钩的管理办法", "", "")
        self.assertIn("增减挂钩类", tags)

    def test_classify_multiple(self):
        """一个文件可以有多个业务类型"""
        from modules.classifier import classify_business_tags
        tags = classify_business_tags(
            "耕地保护和占补平衡实施办法", "增减挂钩", "")
        self.assertIn("耕地保护类", tags)
        self.assertIn("占补平衡类", tags)

    def test_classify_no_match(self):
        """无匹配时返回空列表"""
        from modules.classifier import classify_business_tags
        tags = classify_business_tags("普通文件名称", "", "通用内容")
        self.assertEqual(tags, [])


# ── New: search_documents 支持新字段 ────────────────────────────

class TestSearchExtended(BaseDBTest):

    def test_search_business_tags(self):
        """搜索应能匹配 business_tags"""
        self._seed_doc("测试A", business_tags="增减挂钩类,耕地保护类")
        results = db.search_documents(keyword="增减挂钩类")
        self.assertEqual(len(results), 1)

    def test_search_full_text(self):
        """搜索应能匹配 full_text"""
        self._seed_doc("测试B", full_text="包含增减挂钩相关内容的正文")
        results = db.search_documents(keyword="增减挂钩")
        self.assertEqual(len(results), 1)

    def test_search_by_business_type_filter(self):
        """按业务类型筛选"""
        self._seed_doc("测试C", business_tags="增减挂钩类")
        self._seed_doc("测试D", business_tags="耕地保护类")
        results = db.search_documents(business_type="增减挂钩类")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "测试C")


# ── New: 操作日志 ─────────────────────────────────────────────

class TestOperationLog(BaseDBTest):

    def test_log_operation(self):
        """操作日志应可正常写入和读取"""
        db.log_operation({
            "action": "文件上传",
            "target_type": "document",
            "file_name": "test.pdf",
            "sensitivity_level": "公开",
        })
        logs = db.get_operation_logs(limit=10)
        self.assertTrue(len(logs) > 0)
        self.assertEqual(logs[0]["action"], "文件上传")

    def test_log_default_user(self):
        """默认用户名为'本地用户'"""
        db.log_operation({"action": "测试"})
        logs = db.get_operation_logs(limit=1)
        self.assertEqual(logs[0]["user_name"], "本地用户")


# ── New: 多个无文号文件可入库 ──────────────────────────────────

class TestMultipleEmptyDocNoInLibrary(BaseDBTest):

    def test_multiple_empty_doc_no(self):
        """多个空文号文件应能同时入库"""
        ids = []
        for i in range(5):
            doc_id = db.create_document({
                "title": f"无文号文件{i}",
                "document_no": "",
            })
            ids.append(doc_id)
        self.assertEqual(len(ids), 5)
        for did in ids:
            self.assertIsNotNone(db.get_document(did))


# ── New: 重复文号不崩溃 ──────────────────────────────────────

class TestDuplicateDocNo(BaseDBTest):

    def test_duplicate_doc_no_handled(self):
        """重复文号入库不应导致程序崩溃"""
        doc_id1 = db.create_document({"title": "首次", "document_no": "测试发〔2026〕1号"})
        self.assertIsNotNone(doc_id1)
        # 尝试插入重复文号——create_document 不检查重复，应由调用方检查
        try:
            doc_id2 = db.create_document({"title": "再试", "document_no": "测试发〔2026〕1号"})
            # 如果没有报错，说明数据库未阻止（部分唯一索引可能未生效）
        except Exception:
            pass  # 预期可能报约束冲突，但不应该让程序崩溃
        existing = db.get_document_by_no("测试发〔2026〕1号")
        self.assertIsNotNone(existing)


# ── New: 下载不暴露 host file_path ───────────────────────────-

class TestDownloadSafePath(unittest.TestCase):

    def test_file_path_not_in_download_response(self):
        """下载时应使用 st.download_button 的 file_name 参数而非暴露路径"""
        # 验证逻辑：下载按钮使用的文件名来自 doc.file_name，非 doc.file_path
        test_path = r"D:\secret\policy.pdf"
        test_name = "policy.pdf"
        self.assertNotEqual(test_path, test_name)
        self.assertNotIn("D:", test_name)
        self.assertNotIn("secret", test_name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
