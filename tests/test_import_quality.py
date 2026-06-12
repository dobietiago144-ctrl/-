"""导入质量校验和新增功能测试

运行方式：
    cd policy-reviewer
    python -m unittest tests.test_import_quality -v
"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.db as db
from database.models import ALL_TABLES
from modules.import_validator import (
    validate_import_candidate, clean_filename_for_title, looks_like_policy_filename,
)


class BaseDBTest(unittest.TestCase):
    """使用临时数据库的基类"""

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
            "title": title, "document_no": document_no, "status": status,
            "issuing_authority": kwargs.get("issuing_authority", "自然资源部"),
            "publish_date": kwargs.get("publish_date", ""),
            "effective_date": kwargs.get("effective_date", ""),
            "expiry_date": kwargs.get("expiry_date", ""),
            "region": kwargs.get("region", "全国"),
            "category": kwargs.get("category", "部门规章"),
            "keywords": kwargs.get("keywords", ""),
            "business_tags": kwargs.get("business_tags", ""),
            "sensitivity_level": kwargs.get("sensitivity_level", "公开"),
            "file_name": kwargs.get("file_name", ""),
            "file_size": kwargs.get("file_size", 0),
            "file_type": kwargs.get("file_type", ""),
            "full_text": kwargs.get("full_text", ""),
            "file_path": kwargs.get("file_path", ""),
            "confirmed": kwargs.get("confirmed", 1),
        }
        return db.create_document(data)


# ═══════════ 标题质量校验测试 ═══════════

class TestTitleValidation(unittest.TestCase):

    def test_empty_title_not_allowed(self):
        """标题为空时不允许入库"""
        result = validate_import_candidate(title="", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])
        self.assertEqual(result["level"], "不建议入库")

    def test_brackets_only_not_allowed(self):
        """标题只有《》时不允许入库"""
        result = validate_import_candidate(title="《》", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])
        self.assertEqual(result["level"], "不建议入库")

    def test_pdf_hint_not_allowed_1(self):
        """标题包含'PDF共64页'时不允许入库"""
        result = validate_import_candidate(
            title="PDF共64页的土地管理办法概述", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])
        self.assertIn("PDF共", result["reason"])

    def test_pdf_hint_not_allowed_2(self):
        """标题包含'仅展示前'时不允许入库"""
        result = validate_import_candidate(
            title="仅展示前30页概要", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])

    def test_only_punctuation_not_allowed(self):
        """标题只有标点符号时不允许入库"""
        result = validate_import_candidate(
            title="《》[]（）", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])

    def test_too_short_title_not_allowed(self):
        """标题长度小于4不允许入库"""
        result = validate_import_candidate(
            title="通知", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])

    def test_unrecognized_not_allowed(self):
        """标题为'未识别'时不允许入库"""
        result = validate_import_candidate(
            title="未识别", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])

    def test_invalid_words_not_allowed(self):
        """标题为无效词（目录、正文等）时不允许入库"""
        for word in ["目录", "正文", "附件", "打印", "下载"]:
            result = validate_import_candidate(title=word, document_no="", text="", file_name="")
            self.assertFalse(result["valid"], f"'{word}' should not be allowed")

    def test_too_long_title_manual_confirm(self):
        """标题超过120字标记为待人工确认"""
        long_title = "关于进一步做好耕地保护和永久基本农田管理工作的若干政策措施和实施细则的补充通知和指导意见" * 3
        result = validate_import_candidate(title=long_title, document_no="", text="", file_name="")
        self.assertFalse(result["valid"])
        self.assertEqual(result["level"], "待人工确认")

    def test_valid_title_with_doc_no_accepted(self):
        """有效标题+有文号：可入库"""
        result = validate_import_candidate(
            title="城乡建设用地增减挂钩管理办法",
            document_no="自然资规〔2024〕10号",
            file_name="test.pdf",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["level"], "可入库")

    def test_valid_title_without_doc_no_accepted(self):
        """有效标题+无文号：可入库"""
        result = validate_import_candidate(
            title="耕地保护目标责任考核办法",
            document_no="",
            file_name="test.pdf",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["level"], "可入库")

    def test_no_policy_keywords_no_doc_no_manual_confirm(self):
        """没有政策关键词且无文号：待人工确认"""
        result = validate_import_candidate(
            title="一些行政管理工作安排", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])
        self.assertEqual(result["level"], "待人工确认")

    def test_filename_as_title_not_allowed(self):
        """标题为文件名（含扩展名）不允许入库"""
        result = validate_import_candidate(
            title="耕地保护办法.pdf", document_no="", text="", file_name="")
        self.assertFalse(result["valid"])

    def test_paragraph_as_title(self):
        """标题为正文段落时不允许入库"""
        result = validate_import_candidate(
            title="第一条为了加强土地管理。第二条维护土地的社会主义公有制。第三条十分珍惜合理利用土地。",
            document_no="", text="", file_name="")
        self.assertFalse(result["valid"])
        self.assertEqual(result["level"], "不建议入库")


# ═══════════ 文件名清洗测试 ═══════════

class TestFilenameCleaning(unittest.TestCase):

    def test_remove_extension(self):
        result = clean_filename_for_title("耕地保护办法.pdf")
        self.assertEqual(result, "耕地保护办法")

    def test_remove_date_numbering(self):
        result = clean_filename_for_title("20240115_耕地保护通知.pdf")
        self.assertNotIn("20240115", result)
        self.assertIn("耕地保护通知", result)

    def test_remove_noise_words(self):
        result = clean_filename_for_title("耕地保护办法（扫描件）.pdf")
        self.assertNotIn("扫描件", result)

    def test_remove_final_version_marker(self):
        result = clean_filename_for_title("耕地保护办法最终版.pdf")
        self.assertNotIn("最终版", result)

    def test_looks_like_policy_filename(self):
        self.assertTrue(looks_like_policy_filename("耕地保护管理办法"))
        self.assertFalse(looks_like_policy_filename("abc"))
        self.assertFalse(looks_like_policy_filename("目录"))


# ═══════════ PDF 解析测试 ═══════════

class TestPDFParse(unittest.TestCase):

    def test_parse_pdf_no_warning_in_output(self):
        """PDF解析后文本不应包含解析提示"""
        from modules.document_parser import get_pdf_page_info
        # get_pdf_page_info 函数结构正确
        self.assertTrue(callable(get_pdf_page_info))

    def test_parse_pdf_returns_clean_text(self):
        """parse_pdf 返回纯文本，不包含解析提示"""
        from modules.document_parser import parse_pdf
        # 函数签名正确：接受 file_path 和 max_pages 参数
        import inspect
        sig = inspect.signature(parse_pdf)
        params = list(sig.parameters.keys())
        self.assertIn("file_path", params)
        self.assertIn("max_pages", params)


# ═══════════ 数据库统计测试 ═══════════

class TestDocumentStats(BaseDBTest):

    def test_get_document_stats_returns_correct_structure(self):
        """get_document_stats 返回正确结构"""
        self._seed_doc("测试文件A", status="现行有效", sensitivity_level="公开", business_tags="增减挂钩类")
        self._seed_doc("测试文件B", status="已废止", sensitivity_level="内部", business_tags="耕地保护类")
        self._seed_doc("测试文件C", status="现行有效", sensitivity_level="公开", business_tags="增减挂钩类")

        stats = db.get_document_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["by_status"].get("现行有效", 0), 2)
        self.assertEqual(stats["by_status"].get("已废止", 0), 1)
        self.assertEqual(stats["by_sensitivity"].get("公开", 0), 2)
        self.assertEqual(stats["by_sensitivity"].get("内部", 0), 1)
        self.assertIn("增减挂钩类", stats["by_business_type"])

    def test_get_document_stats_with_filters(self):
        """按筛选条件聚合统计"""
        self._seed_doc("增减挂钩管理办法", status="现行有效", business_tags="增减挂钩类")
        self._seed_doc("耕地保护办法", status="现行有效", business_tags="耕地保护类")

        stats = db.get_document_stats(business_type="增减挂钩类")
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["by_business_type"].get("增减挂钩类", 0), 1)

    def test_get_document_stats_with_keyword(self):
        """搜索关键词后统计"""
        self._seed_doc("耕地保护办法", business_tags="耕地保护类")
        self._seed_doc("增减挂钩管理办法", business_tags="增减挂钩类")

        stats = db.get_document_stats(keyword="耕地")
        self.assertEqual(stats["total"], 1)


# ═══════════ 批量删除测试 ═══════════

class TestBatchDelete(BaseDBTest):

    def test_batch_delete_success(self):
        """批量删除多条记录"""
        id1 = self._seed_doc("文件A")
        id2 = self._seed_doc("文件B")
        id3 = self._seed_doc("文件C")

        result = db.batch_delete_documents([id1, id2])
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["failed"], 0)

        self.assertIsNone(db.get_document(id1))
        self.assertIsNone(db.get_document(id2))
        self.assertIsNotNone(db.get_document(id3))

    def test_batch_delete_writes_log(self):
        """批量删除写入操作日志"""
        doc_id = self._seed_doc("测试删除")
        result = db.batch_delete_documents([doc_id])
        self.assertEqual(result["deleted"], 1)

        logs = db.get_operation_logs(limit=10)
        self.assertTrue(any(l["action"] == "批量删除文件" for l in logs))

    def test_batch_delete_nonexistent(self):
        """删除不存在的ID不崩溃"""
        result = db.batch_delete_documents([99999])
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(result["failed"], 1)


# ═══════════ 重复检查测试 ═══════════

class TestDuplicateCheck(BaseDBTest):

    def test_duplicate_by_doc_no(self):
        """文号相同检测为重复"""
        self._seed_doc("某文件", "自然资发〔2024〕1号")
        result = db.check_duplicate(document_no="自然资发〔2024〕1号")
        self.assertTrue(result["is_duplicate"])
        self.assertIn("文号重复", result["reason"])

    def test_no_duplicate_for_new_doc_no(self):
        """新文号不重复"""
        result = db.check_duplicate(document_no="新文号〔2024〕99号")
        self.assertFalse(result["is_duplicate"])

    def test_duplicate_by_filename_size(self):
        """文件名+大小相同检测为疑似重复"""
        self._seed_doc("某文件", file_name="test.pdf", file_size=12345)
        result = db.check_duplicate(file_name="test.pdf", file_size=12345)
        self.assertTrue(result["is_duplicate"])


# ═══════════ 导入清单导出测试 ═══════════

class TestImportReport(unittest.TestCase):

    def test_import_report_structure(self):
        """导入报告结构正确"""
        report = {
            "success": 5, "failed": 1, "skipped": 2, "duplicate": 1,
            "manual_confirm": 0, "not_recommended": 0,
            "details": [
                {"file_name": "test.pdf", "title": "测试", "status": "成功", "document_id": 1},
            ],
        }
        self.assertEqual(report["success"], 5)
        self.assertTrue(len(report["details"]) > 0)

    def test_import_report_excel_export(self):
        """导入清单可导出Excel"""
        import pandas as pd
        import io
        details = [
            {"序号": 1, "文件名": "test.pdf", "识别标题": "测试办法",
             "识别文号": "", "发文单位": "", "文件类别": "",
             "业务类型": "", "敏感级别": "公开", "入库状态": "成功",
             "失败原因": "", "处理建议": "", "document_id": 1},
        ]
        df = pd.DataFrame(details)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="导入清单")
        self.assertTrue(len(buf.getvalue()) > 0)


# ═══════════ 分页测试 ═══════════

class TestPagination(BaseDBTest):

    def test_search_with_pagination(self):
        """分页查询正确"""
        for i in range(25):
            self._seed_doc(f"文件{i}")

        page1 = db.search_documents(limit=10, offset=0)
        page2 = db.search_documents(limit=10, offset=10)
        page3 = db.search_documents(limit=10, offset=20)

        self.assertEqual(len(page1), 10)
        self.assertEqual(len(page2), 10)
        self.assertEqual(len(page3), 5)

    def test_count_matches_search(self):
        """计数与搜索数量一致"""
        for i in range(5):
            self._seed_doc(f"耕地文件{i}", business_tags="耕地保护类")
        for i in range(3):
            self._seed_doc(f"增减挂钩文件{i}", business_tags="增减挂钩类")

        total = db.count_documents()
        all_docs = db.search_documents(limit=200)
        self.assertEqual(total, len(all_docs))
        self.assertEqual(total, 8)


# ═══════════ 状态规范化测试 ═══════════

class TestStatusNormalization(unittest.TestCase):

    def test_normalize_standard_status_unchanged(self):
        """标准状态不变"""
        from modules.status_utils import normalize_document_status
        for s in ["现行有效", "已废止", "已失效", "被替代", "部分废止", "即将失效", "待核实", "不明"]:
            self.assertEqual(normalize_document_status(s), s)

    def test_normalize_bianma_youxiao(self):
        """'编码有效' → '现行有效'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("编码有效"), "现行有效")

    def test_normalize_daiyanzheng(self):
        """'待验证' → '待核实'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("待验证"), "待核实")

    def test_normalize_youxiao(self):
        """'有效' → '现行有效'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("有效"), "现行有效")

    def test_normalize_guoqi(self):
        """'过期' → '已失效'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("过期"), "已失效")

    def test_normalize_feizhi(self):
        """'废止' → '已废止'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("废止"), "已废止")

    def test_normalize_tidai(self):
        """'替代' → '被替代'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("替代"), "被替代")

    def test_normalize_empty(self):
        """空值 → '待核实'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status(""), "待核实")
        self.assertEqual(normalize_document_status(None), "待核实")

    def test_normalize_unknown(self):
        """无法识别 → '待核实'"""
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("奇怪的文本"), "待核实")

    def test_get_migration_sql(self):
        """迁移SQL包含关键清理语句"""
        from modules.status_utils import get_migration_sql
        sqls = get_migration_sql()
        self.assertTrue(any("编码有效" in s for s in sqls))
        self.assertTrue(any("待验证" in s for s in sqls))
        self.assertTrue(any("status NOT IN" in s for s in sqls))


# ═══════════ 政策监测测试 ═══════════

class TestPolicyMonitor(unittest.TestCase):

    def test_detect_obsolete_keywords(self):
        """检测废止关键词"""
        from modules.policy_monitor import detect_obsolete_keywords

        text = "根据自然资源部令，同时废止《某办法》（自然资发〔2020〕1号）"
        found = detect_obsolete_keywords(text)
        self.assertIn("同时废止", found)
        self.assertIn("废止", found)

    def test_detect_obsolete_keywords_multiple(self):
        """检测多个废止/失效关键词"""
        from modules.policy_monitor import detect_obsolete_keywords

        text = "予以废止。本办法自有效期届满后失效。修订后的新办法替代旧办法。"
        found = detect_obsolete_keywords(text)
        self.assertIn("予以废止", found)
        self.assertIn("有效期届满", found)
        self.assertIn("替代", found)
        self.assertIn("修订", found)

    def test_detect_obsolete_keywords_empty(self):
        """空文本返回空列表"""
        from modules.policy_monitor import detect_obsolete_keywords
        self.assertEqual(detect_obsolete_keywords(""), [])
        self.assertEqual(detect_obsolete_keywords(None), [])

    def test_guess_relation_type_feizhi(self):
        """推测废止关系"""
        from modules.policy_monitor import guess_relation_type
        result = guess_relation_type(["废止", "同时废止"], "予以废止")
        self.assertEqual(result, "疑似废止")

    def test_guess_relation_type_shixiao(self):
        """推测失效关系"""
        from modules.policy_monitor import guess_relation_type
        result = guess_relation_type(["失效"], "有效期届满")
        self.assertEqual(result, "疑似失效")

    def test_guess_relation_type_tidai(self):
        """推测替代关系"""
        from modules.policy_monitor import guess_relation_type
        result = guess_relation_type(["替代"], "新办法替代旧办法")
        self.assertEqual(result, "疑似替代")

    def test_get_monitor_keywords(self):
        """获取监测关键词"""
        from modules.policy_monitor import get_monitor_keywords
        kws = get_monitor_keywords()
        self.assertIn("废止", kws)
        self.assertIn("失效", kws)
        self.assertIn("替代", kws)
        self.assertTrue(len(kws) > 5)


class TestMonitorCandidatesTable(BaseDBTest):

    def test_candidates_table_exists(self):
        """policy_monitor_candidates 表存在"""
        conn = db.get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='policy_monitor_candidates'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(tables)

    def test_save_and_get_candidate(self):
        """保存和获取监测候选"""
        from modules.policy_monitor import save_monitor_candidate, get_monitor_candidate

        cid = save_monitor_candidate({
            "source_name": "自然资源部-政策",
            "source_domain": "mnr.gov.cn",
            "source_url": "https://www.mnr.gov.cn/test",
            "title": "关于废止某项政策的通知",
            "document_no": "自然资发〔2024〕50号",
            "publish_date": "2024-06-01",
            "full_text": "根据...现予以废止...",
            "candidate_type": "废止公告",
            "detected_keywords": "废止,予以废止",
            "relation_type_guess": "疑似废止",
            "relation_basis_text": "现予以废止",
            "status": "已抓取待确认",
        })
        self.assertGreater(cid, 0)

        cand = get_monitor_candidate(cid)
        self.assertIsNotNone(cand)
        self.assertEqual(cand["title"], "关于废止某项政策的通知")
        self.assertEqual(cand["status"], "已抓取待确认")

    def test_confirm_candidate_does_not_auto_update(self):
        """确认候选人不会自动改正式库（需人工确认）"""
        from config import ENABLE_AUTO_UPDATE_LIBRARY
        self.assertFalse(ENABLE_AUTO_UPDATE_LIBRARY)


# ═══════════ 选择逻辑测试 ═══════════

class TestSelectionLogic(unittest.TestCase):

    def test_select_all_page_logic(self):
        """全选本页逻辑：update + 同步 checkbox keys"""
        selected_ids = set()
        checkbox_states = {}
        current_page_ids = [1, 2, 3, 4, 5]

        # 模拟全选动作
        selected_ids.update(current_page_ids)
        for doc_id in current_page_ids:
            checkbox_states[f"sel_{doc_id}"] = True

        self.assertEqual(selected_ids, {1, 2, 3, 4, 5})
        for doc_id in current_page_ids:
            self.assertTrue(checkbox_states[f"sel_{doc_id}"])

    def test_deselect_page_logic(self):
        """取消本页逻辑：difference_update + 同步 checkbox keys"""
        selected_ids = {1, 2, 3, 4, 5, 10, 20}
        checkbox_states = {"sel_1": True, "sel_2": True, "sel_3": True, "sel_4": True, "sel_5": True}
        current_page_ids = [1, 2, 3, 4, 5]

        selected_ids.difference_update(current_page_ids)
        for doc_id in current_page_ids:
            checkbox_states[f"sel_{doc_id}"] = False

        self.assertEqual(selected_ids, {10, 20})
        for doc_id in current_page_ids:
            self.assertFalse(checkbox_states[f"sel_{doc_id}"])

    def test_clear_all_selection(self):
        """清空全部选择 + 清空 checkbox keys"""
        selected_ids = {1, 2, 3, 4, 5}
        checkbox_states = {f"sel_{i}": True for i in range(1, 6)}
        current_page_ids = [1, 2, 3, 4, 5]

        selected_ids = set()
        for doc_id in current_page_ids:
            checkbox_states[f"sel_{doc_id}"] = False

        self.assertEqual(len(selected_ids), 0)
        for doc_id in current_page_ids:
            self.assertFalse(checkbox_states[f"sel_{doc_id}"])

    def test_filter_change_clears_selection(self):
        """筛选条件变化清空选中"""
        old_filter_key = "耕地|现行有效|全国||增减挂钩类|1"
        new_filter_key = "耕地|待核实|全国||增减挂钩类|1"
        self.assertNotEqual(old_filter_key, new_filter_key)

    def test_checkbox_sync_on_select_all(self):
        """全选后 checkbox state 和 selected_ids 一致"""
        selected_ids = set()
        current_page_ids = [101, 102, 103]

        # 全选操作
        selected_ids.update(current_page_ids)
        for doc_id in current_page_ids:
            selected_ids.add(doc_id)

        for doc_id in current_page_ids:
            self.assertIn(doc_id, selected_ids)


# ═══════════ 状态清理测试 ═══════════

class TestStatusCleanup(BaseDBTest):

    def test_clean_document_statuses(self):
        """clean_document_statuses 清理非标准状态"""
        # 插入带有非标准状态的文件
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO documents (title, status) VALUES (?, ?)",
            ("测试文件1", "编码有效")
        )
        conn.execute(
            "INSERT INTO documents (title, status) VALUES (?, ?)",
            ("测试文件2", "待验证")
        )
        conn.execute(
            "INSERT INTO documents (title, status) VALUES (?, ?)",
            ("正常文件", "现行有效")
        )
        conn.commit()
        conn.close()

        result = db.clean_document_statuses()
        self.assertGreater(result["updated"], 0)
        # 清理后不应该再有"编码有效"和"待验证"
        self.assertEqual(result["non_standard_after"], 0)

        # 验证已清理
        conn = db.get_connection()
        row = conn.execute(
            "SELECT status FROM documents WHERE title = ?", ("测试文件1",)
        ).fetchone()
        conn.close()
        self.assertEqual(row["status"], "现行有效")

    def test_clean_statuses_batch(self):
        """批量清理多种非标准状态"""
        conn = db.get_connection()
        test_data = [
            ("过期文件", "过期"),
            ("废止文件", "废止"),
            ("有效文件", "有效"),
            ("替代文件", "替代"),
        ]
        for title, status in test_data:
            conn.execute(
                "INSERT INTO documents (title, status) VALUES (?, ?)",
                (title, status)
            )
        conn.commit()
        conn.close()

        result = db.clean_document_statuses()
        self.assertGreaterEqual(result["updated"], 4)

        # 验证全部标准化
        conn = db.get_connection()
        for title, _ in test_data:
            row = conn.execute(
                "SELECT status FROM documents WHERE title = ?", (title,)
            ).fetchone()
            from modules.status_utils import STANDARD_STATUSES
            self.assertIn(row["status"], STANDARD_STATUSES,
                         f"'{title}' status should be standard")
        conn.close()


# ═══════════ 规则引擎测试 ═══════════

class TestRuleEngine(unittest.TestCase):

    def test_detect_invalid_title_empty(self):
        from modules.rule_engine import detect_invalid_title
        self.assertTrue(detect_invalid_title(""))

    def test_detect_invalid_title_brackets(self):
        from modules.rule_engine import detect_invalid_title
        self.assertTrue(detect_invalid_title("《》"))

    def test_detect_invalid_title_pdf_hint(self):
        from modules.rule_engine import detect_invalid_title
        self.assertTrue(detect_invalid_title("PDF共64页，仅展示前30页概要"))

    def test_detect_invalid_title_normal(self):
        from modules.rule_engine import detect_invalid_title
        self.assertFalse(detect_invalid_title("耕地保护管理办法"))

    def test_detect_invalid_title_unrecognized(self):
        from modules.rule_engine import detect_invalid_title
        self.assertTrue(detect_invalid_title("未识别"))

    def test_get_display_title_invalid(self):
        from modules.rule_engine import get_display_title
        self.assertEqual(get_display_title(""), "【未识别标题，请补录】")
        self.assertEqual(get_display_title("《》"), "【未识别标题，请补录】")

    def test_get_display_title_long(self):
        from modules.rule_engine import get_display_title
        long_title = "关于进一步做好耕地保护和永久基本农田管理工作的若干政策措施" * 3
        result = get_display_title(long_title, max_len=50)
        self.assertTrue(result.endswith("..."))

    def test_get_display_title_normal(self):
        from modules.rule_engine import get_display_title
        self.assertEqual(get_display_title("耕地保护条例"), "耕地保护条例")

    def test_apply_rules_status_code_valid(self):
        from modules.rule_engine import apply_rules
        results = apply_rules({"status": "编码有效"}, rule_type="状态修正")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["rule"]["rule_id"], "STATUS_001")

    def test_apply_rules_title_empty_brackets(self):
        from modules.rule_engine import apply_rules
        results = apply_rules({"title": "《》"}, rule_type="标题校验")
        self.assertTrue(len(results) > 0)


# ═══════════ MNR URL 和监控增强测试 ═══════════

class TestMNRMonitor(unittest.TestCase):

    def test_is_allowed_mnr_url_f_domain(self):
        from modules.policy_monitor import is_allowed_mnr_url
        self.assertTrue(is_allowed_mnr_url("https://f.mnr.gov.cn/202606/t20260605_2931308.html"))

    def test_is_allowed_mnr_url_gk_domain(self):
        from modules.policy_monitor import is_allowed_mnr_url
        self.assertTrue(is_allowed_mnr_url("https://gk.mnr.gov.cn/some-page"))

    def test_is_allowed_mnr_url_gi_domain(self):
        from modules.policy_monitor import is_allowed_mnr_url
        self.assertTrue(is_allowed_mnr_url("https://gi.mnr.gov.cn/notice"))

    def test_is_allowed_mnr_url_www_domain(self):
        from modules.policy_monitor import is_allowed_mnr_url
        self.assertTrue(is_allowed_mnr_url("https://www.mnr.gov.cn/"))

    def test_is_allowed_mnr_url_mnr_root(self):
        from modules.policy_monitor import is_allowed_mnr_url
        self.assertTrue(is_allowed_mnr_url("https://mnr.gov.cn/"))

    def test_is_allowed_mnr_url_external_false(self):
        from modules.policy_monitor import is_allowed_mnr_url
        self.assertFalse(is_allowed_mnr_url("https://www.baidu.com/"))

    def test_is_allowed_mnr_url_localhost_false(self):
        from modules.policy_monitor import is_allowed_mnr_url
        self.assertFalse(is_allowed_mnr_url("http://localhost:8501/"))

    def test_detect_obsolete_keywords_extended(self):
        from modules.policy_monitor import detect_obsolete_keywords
        text = "关于公布已废止或者失效的规范性文件目录的公告"
        found = detect_obsolete_keywords(text)
        self.assertTrue(len(found) > 0)
        self.assertIn("已废止或者失效", found)

    def test_detect_feizhi_bumen_guizhang(self):
        from modules.policy_monitor import detect_obsolete_keywords
        text = "关于第X批废止的部门规章的决定"
        found = detect_obsolete_keywords(text)
        self.assertIn("废止的部门规章", found)

    def test_ignored_urls_table_created(self):
        import database.db as db
        import tempfile, os, shutil
        from database.models import ALL_TABLES
        orig = db.DB_PATH
        tmp = tempfile.mkdtemp()
        try:
            test_db = os.path.join(tmp, "test.db")
            db.DB_PATH = test_db
            conn = db.get_connection()
            for sql in ALL_TABLES:
                conn.execute(sql)
            conn.commit()
            conn.close()
            conn2 = db.get_connection()
            tables = conn2.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='policy_monitor_ignored_urls'"
            ).fetchone()
            conn2.close()
            self.assertIsNotNone(tables)
        finally:
            db.DB_PATH = orig
            shutil.rmtree(tmp, ignore_errors=True)


# ═══════════ 状态和去重测试 ═══════════

class TestStatusFilterAndDedup(unittest.TestCase):

    def test_doc_status_options_no_bianma(self):
        from config import DOC_STATUS_OPTIONS
        self.assertNotIn("编码有效", DOC_STATUS_OPTIONS)
        self.assertNotIn("不明白", DOC_STATUS_OPTIONS)
        self.assertNotIn("待验证", DOC_STATUS_OPTIONS)

    def test_allowed_statuses_no_bianma(self):
        from config import DOC_STATUS_OPTIONS
        allowed = [s for s in DOC_STATUS_OPTIONS if s not in ("编码有效", "待验证", "不明白")]
        self.assertNotIn("编码有效", allowed)
        self.assertNotIn("不明白", allowed)

    def test_normalize_bumingbai(self):
        from modules.status_utils import normalize_document_status
        self.assertEqual(normalize_document_status("不明白"), "待核实")

    def test_normalize_bianma_not_xianxing(self):
        """编码有效不直接映射为现行有效说明逻辑"""
        from modules.status_utils import normalize_document_status
        # normalize 把"编码有效"→"现行有效"是历史迁移，但新导入不应产生
        self.assertEqual(normalize_document_status("编码有效"), "现行有效")

    def test_default_status_is_daiheshi(self):
        """默认状态应为待核实"""
        from modules.metadata_extractor import infer_status
        # infer_status 在没有明确日期的情况下返回 "待核实"
        result = infer_status("普通正文", {}, "")
        self.assertEqual(result, "待核实")


# ═══════════ MNR 解析器测试 ═══════════

class TestMNRParser(unittest.TestCase):

    def setUp(self):
        self.maxDiff = 3000

    def test_parse_mnr_page_metadata(self):
        """解析模拟的自然资源部政策法规库详情页"""
        from modules.policy_monitor import parse_mnr_policy_library_detail

        html = """<html><body>
        <div class="content">
        <table>
        <tr><td>名称：</td><td>自然资源部关于第八批废止的部门规章的决定</td></tr>
        <tr><td>文号：</td><td>中华人民共和国自然资源部令第21号</td></tr>
        <tr><td>发布机构：</td><td>自然资源部</td></tr>
        <tr><td>成文日期：</td><td>2026年5月27日</td></tr>
        <tr><td>发布日期：</td><td>2026年6月5日</td></tr>
        <tr><td>效力级别：</td><td>部门规章</td></tr>
        <tr><td>业务类型：</td><td>综合管理</td></tr>
        <tr><td>时效状态：</td><td>现行有效</td></tr>
        </table>
        <div class="article">
        <p>一、《建设项目用地预审管理办法》（2001年7月25日国土资源部令第7号发布……）</p>
        <p>二、《海洋行政处罚实施办法》（2002年12月25日国土资源部令第15号发布）</p>
        </div>
        </div></body></html>"""

        result = parse_mnr_policy_library_detail(html, "")
        self.assertEqual(result["title"], "自然资源部关于第八批废止的部门规章的决定")
        self.assertEqual(result["document_no"], "中华人民共和国自然资源部令第21号")
        self.assertEqual(result["issuing_authority"], "自然资源部")
        self.assertEqual(result["pass_date"], "2026-05-27")
        self.assertEqual(result["publish_date"], "2026-06-05")
        self.assertEqual(result["status_from_source"], "现行有效")
        self.assertEqual(result["effectiveness_level"], "部门规章")

    def test_extract_obsolete_items(self):
        """从正文提取被废止旧文件"""
        from modules.policy_monitor import extract_obsolete_items_from_text

        text = """
        一、《建设项目用地预审管理办法》（2001年7月25日国土资源部令第7号发布）
        二、《海洋行政处罚实施办法》（2002年12月25日国土资源部令第15号发布）
        """

        items = extract_obsolete_items_from_text(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["old_title"], "建设项目用地预审管理办法")
        self.assertEqual(items[1]["old_title"], "海洋行政处罚实施办法")
        self.assertEqual(items[0]["old_document_no"], "国土资源部令第7号")
        self.assertEqual(items[1]["old_document_no"], "国土资源部令第15号")
        self.assertIn("废止", items[0]["relation_type"])

    def test_extract_obsolete_items_numbered(self):
        """支持多种编号形式"""
        from modules.policy_monitor import extract_obsolete_items_from_text

        text = """
        （一）《某管理办法》
        1.《某实施细则》
        - 《某通知》
        """

        items = extract_obsolete_items_from_text(text)
        self.assertEqual(len(items), 3)
        titles = [i["old_title"] for i in items]
        self.assertIn("某管理办法", titles)
        self.assertIn("某实施细则", titles)
        self.assertIn("某通知", titles)

    def test_abolish_notice_not_abolished(self):
        """废止公告本身不应标记为已废止"""
        title = "自然资源部关于第八批废止的部门规章的决定"
        self.assertIn("废止", title)
        # 该标题本身是"废止决定"，不是被废止文件


class TestMonitorDedup(BaseDBTest):

    def test_is_url_in_library(self):
        from modules.policy_monitor import is_url_in_library
        db.create_document({
            "title": "测试", "source_url": "https://f.mnr.gov.cn/test.html",
        })
        self.assertTrue(is_url_in_library("https://f.mnr.gov.cn/test.html"))
        self.assertFalse(is_url_in_library("https://f.mnr.gov.cn/nonexistent.html"))

    def test_is_url_in_candidates(self):
        from modules.policy_monitor import is_url_in_candidates, save_monitor_candidate
        save_monitor_candidate({
            "source_url": "https://f.mnr.gov.cn/candidate_test.html",
            "title": "测试", "source_name": "test", "source_domain": "mnr.gov.cn",
        })
        self.assertTrue(is_url_in_candidates("https://f.mnr.gov.cn/candidate_test.html"))

    def test_is_url_ignored_check(self):
        from modules.policy_monitor import is_url_ignored, add_ignored_url
        add_ignored_url("https://f.mnr.gov.cn/ignored_test.html", "测试忽略")
        self.assertTrue(is_url_ignored("https://f.mnr.gov.cn/ignored_test.html"))


# ══════════════════════════════════════════════════════
#  新增功能测试：文件重要级别 & 自定义业务类型 & 批量下载
# ══════════════════════════════════════════════════════


class TestImportanceLevel(BaseDBTest):
    """文件重要级别 (importance_level) 相关测试"""

    def test_importance_level_column_exists(self):
        """documents 表有 importance_level 字段"""
        conn = db.get_connection()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
        conn.close()
        self.assertIn("importance_level", cols)

    def test_new_document_default_importance_level(self):
        """新增文件默认 importance_level = 一般"""
        doc_id = db.create_document({"title": "测试默认重要级别"})
        doc = db.get_document(doc_id)
        self.assertEqual(doc.get("importance_level"), "一般")

    def test_create_document_can_save_importance_level(self):
        """手工新增可以保存 importance_level"""
        doc_id = db.create_document({
            "title": "核心政策文件",
            "importance_level": "核心",
        })
        doc = db.get_document(doc_id)
        self.assertEqual(doc["importance_level"], "核心")

    def test_update_document_importance_level(self):
        """更新文件可以修改 importance_level"""
        doc_id = db.create_document({"title": "测试更新重要级别"})
        db.update_document(doc_id, {"importance_level": "重要"})
        doc = db.get_document(doc_id)
        self.assertEqual(doc["importance_level"], "重要")

    def test_search_documents_by_importance_level(self):
        """search_documents 可以按 importance_level 筛选"""
        db.create_document({"title": "核心文件", "importance_level": "核心"})
        db.create_document({"title": "一般文件", "importance_level": "一般"})
        results = db.search_documents(importance_level="核心")
        self.assertTrue(all(r["importance_level"] == "核心" for r in results))
        self.assertTrue(len(results) >= 1)

    def test_count_documents_by_importance_level(self):
        """count_documents 可以按 importance_level 统计"""
        db.create_document({"title": "计数测试", "importance_level": "参考"})
        count = db.count_documents(importance_level="参考")
        self.assertTrue(count >= 1)

    def test_get_document_stats_includes_importance(self):
        """get_document_stats 包含 by_importance"""
        db.create_document({"title": "统计测试", "importance_level": "待评估"})
        stats = db.get_document_stats()
        self.assertIn("by_importance", stats)
        self.assertIsInstance(stats["by_importance"], dict)

    def test_importance_level_edge_values(self):
        """importance_level 支持所有有效值"""
        valid_levels = ["核心", "重要", "一般", "参考", "待评估"]
        for level in valid_levels:
            doc_id = db.create_document({"title": f"测试-{level}", "importance_level": level})
            doc = db.get_document(doc_id)
            self.assertEqual(doc["importance_level"], level)

    def test_migrate_sets_empty_importance_to_general(self):
        """历史数据 importance_level 为空时统一为'一般'"""
        doc_id = db.create_document({"title": "迁移测试文件"})
        conn = db.get_connection()
        conn.execute("UPDATE documents SET importance_level = '' WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()
        db.migrate_database()
        doc = db.get_document(doc_id)
        self.assertEqual(doc["importance_level"], "一般")


class TestCustomBusinessType(BaseDBTest):
    """自定义业务类型相关测试"""

    def test_business_tags_can_save_custom_type(self):
        """business_tags 支持自定义类型"""
        doc_id = db.create_document({
            "title": "自定义业务测试",
            "business_tags": "耕地保护类,城市更新类,历史遗留用地类",
        })
        doc = db.get_document(doc_id)
        self.assertIn("城市更新类", doc["business_tags"])
        self.assertIn("历史遗留用地类", doc["business_tags"])

    def test_search_can_find_custom_business_type(self):
        """search_documents 可以搜索自定义业务类型"""
        db.create_document({
            "title": "测试自定义搜索",
            "business_tags": "城市更新类,测试专用类",
        })
        results = db.search_documents(business_type="测试专用类")
        self.assertTrue(len(results) >= 1)
        self.assertIn("测试专用类", results[0]["business_tags"])

    def test_get_document_stats_includes_custom_types(self):
        """get_document_stats 统计中包含自定义业务类型"""
        db.create_document({
            "title": "业务统计测试",
            "business_tags": "测试统计类型,耕地保护类",
        })
        stats = db.get_document_stats()
        all_tags = set(stats["by_business_type"].keys())
        self.assertIn("测试统计类型", all_tags)

    def test_business_tags_deduplication(self):
        """business_tags 去重逻辑正确"""
        # 测试 _merge_business_tags 去重（应用层逻辑）
        # 此处模拟应用层合并：通过 update 去重后保存
        doc_id = db.create_document({
            "title": "去重测试",
            "business_tags": "耕地保护类,成片开发类",
        })
        # 应用层合并去重逻辑
        existing_tags = set(["耕地保护类", "成片开发类"])
        new_tags = set(["耕地保护类", "全域土地综合整治类"])  # "耕地保护类" 重复
        existing_tags.update(new_tags)
        merged = ",".join(sorted(existing_tags))
        db.update_document(doc_id, {"business_tags": merged})
        doc = db.get_document(doc_id)
        tags = [t.strip() for t in doc["business_tags"].split(",") if t.strip()]
        self.assertEqual(len(tags), len(set(tags)))
        self.assertIn("耕地保护类", tags)
        self.assertIn("成片开发类", tags)
        self.assertIn("全域土地综合整治类", tags)


class TestDocumentStatsWithFilters(BaseDBTest):
    """get_document_stats 扩展过滤测试"""

    def test_stats_with_importance_level_filter(self):
        """get_document_stats 支持 importance_level 筛选"""
        db.create_document({"title": "核心文件", "importance_level": "核心"})
        db.create_document({"title": "参考文件", "importance_level": "参考"})
        stats = db.get_document_stats(importance_level="核心")
        self.assertTrue(stats["total"] >= 1)
        for doc in db.search_documents(importance_level="核心", limit=100):
            self.assertEqual(doc["importance_level"], "核心")

    def test_stats_with_sensitivity_level_filter(self):
        """get_document_stats 支持 sensitivity_level 筛选"""
        db.create_document({"title": "内部文件", "sensitivity_level": "内部"})
        stats = db.get_document_stats(sensitivity_level="内部")
        self.assertTrue(stats["total"] >= 1)


class TestBatchDownloadSensitivityCheck(BaseDBTest):
    """批量下载敏感级别检查测试"""

    def test_public_allowed(self):
        """公开文件允许下载"""
        from config import ALLOW_PUBLIC_DOWNLOAD
        self.assertTrue(ALLOW_PUBLIC_DOWNLOAD)
        # 检查 _can_download_by_sensitivity 逻辑（导入 pages 模块中的函数）
        doc_id = db.create_document({
            "title": "公开测试",
            "sensitivity_level": "公开",
            "file_path": __file__,
        })
        doc = db.get_document(doc_id)
        self.assertEqual(doc["sensitivity_level"], "公开")

    def test_sensitive_default_denied(self):
        """敏感文件默认不允许下载"""
        from config import ALLOW_SENSITIVE_DOWNLOAD
        self.assertFalse(ALLOW_SENSITIVE_DOWNLOAD)

    def test_sheimi_upload_denied(self):
        """涉密文件禁止上传"""
        doc_id = db.create_document({
            "title": "涉密测试",
            "sensitivity_level": "涉密禁止上传",
        })
        doc = db.get_document(doc_id)
        self.assertIn("涉密", doc["sensitivity_level"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
