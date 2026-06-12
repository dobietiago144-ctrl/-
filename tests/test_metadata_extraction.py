"""元数据提取优化测试：标题识别、文号绑定、附件排除、状态默认

运行方式：
    cd policy-reviewer
    python -m unittest tests.test_metadata_extraction -v
"""

import sys
import os
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.db as db
from database.models import ALL_TABLES
from modules.metadata_extractor import (
    extract_title, extract_document_no, extract_issuing_authority,
    extract_dates, infer_status, extract_all_metadata,
    is_attachment_or_form_title, extract_title_candidates,
    extract_primary_document_no, extract_title_with_meta,
    _extract_attachment_titles,
)
from modules.import_validator import is_attachment_title, validate_import_candidate


# ═══════════════════════════════════════════════════════════
#  GD 文件测试案例（核心修复验证）
# ═══════════════════════════════════════════════════════════

GD_DOCUMENT_TEXT = """
广东省国土资源厅文件
粤国土资利用发〔2018〕25号

广东省国土资源厅关于印发《省政府审批建设用地报批材料范本（2018年修订版）》的通知

各地级以上市国土资源主管部门，各县（市、区）国土资源主管部门：

为进一步规范省政府审批建设用地报批工作，提高报批材料质量，省厅制定了《省政府审批建设用地报批材料范本（2018年修订版）》，现印发给你们，请遵照执行。

附件1
①县级以上城市规划主管部门出具的城市规划审核意见

附件2
②用地预审意见

附件3
③建设项目用地申请表

材料清单：
1. 勘测定界报告
2. 法人身份证明
3. 授权委托书

2018年3月15日
"""


class TestGDDocumentCase(unittest.TestCase):
    """广东省国土资源厅文件案例 — 核心修复验证"""

    def test_title_is_red_header_not_attachment(self):
        """标题应为红头文件标题，不能是附件条目"""
        title = extract_title(GD_DOCUMENT_TEXT)
        self.assertIn("广东省国土资源厅", title)
        self.assertIn("省政府审批建设用地报批材料范本", title)
        self.assertIn("通知", title)
        self.assertNotIn("①", title)
        self.assertNotIn("县级以上城市规划主管部门", title)

    def test_title_exact_match(self):
        """标题应精确匹配红头文件标题"""
        title = extract_title(GD_DOCUMENT_TEXT)
        expected = "广东省国土资源厅关于印发《省政府审批建设用地报批材料范本（2018年修订版）》的通知"
        self.assertEqual(title, expected)

    def test_document_no_is_front_page_primary(self):
        """文号应为首页主文号"""
        doc_no = extract_document_no(GD_DOCUMENT_TEXT)
        self.assertEqual(doc_no, "粤国土资利用发〔2018〕25号")

    def test_issuing_authority_is_front_page(self):
        """发文单位应为首页红头机关"""
        authority = extract_issuing_authority(GD_DOCUMENT_TEXT)
        self.assertEqual(authority, "广东省国土资源厅")

    def test_status_is_daiheshi_not_effective(self):
        """状态应为'待核实'，不能自动判定为'现行有效'"""
        meta = extract_all_metadata(GD_DOCUMENT_TEXT)
        self.assertEqual(meta["status"], "待核实")
        self.assertNotEqual(meta["status"], "现行有效")

    def test_attachment_not_main_title(self):
        """附件条目不能作为主标题"""
        candidates = extract_title_candidates(GD_DOCUMENT_TEXT)
        # 最高分候选应为红头标题
        best = candidates[0]
        self.assertIn("广东省国土资源厅", best["title"])
        self.assertNotIn("①", best["title"])
        # 附件条目标题得分应远低于红头标题
        main_score = best["score"]
        for c in candidates:
            if "县级以上城市规划主管部门" in c["title"]:
                self.assertLess(c["score"], main_score,
                               f"附件条目标题({c['score']})得分不应超过主标题({main_score})")

    def test_full_metadata_extraction(self):
        """综合元数据提取验证"""
        meta = extract_all_metadata(GD_DOCUMENT_TEXT)
        self.assertIn("广东省国土资源厅关于印发", meta["title"])
        self.assertEqual(meta["document_no"], "粤国土资利用发〔2018〕25号")
        self.assertEqual(meta["issuing_authority"], "广东省国土资源厅")
        self.assertEqual(meta["status"], "待核实")
        # 附件标题应在 attachment_titles 中
        att_titles = meta.get("attachment_titles", [])
        self.assertTrue(any("城市规划审核意见" in t for t in att_titles),
                       "附件标题应在 attachment_titles 中")


# ═══════════════════════════════════════════════════════════
#  附件/材料清单标题检测测试
# ═══════════════════════════════════════════════════════════

class TestAttachmentTitleDetection(unittest.TestCase):

    def test_attachment_prefix_detected(self):
        """以'附件'开头的行应被检测为附件标题"""
        self.assertTrue(is_attachment_or_form_title(
            "附件1 县级以上城市规划主管部门出具的城市规划审核意见"))
        self.assertTrue(is_attachment_or_form_title(
            "附表 建设用地审批表"))

    def test_material_list_detected(self):
        """材料清单条目应被检测为非主标题"""
        self.assertTrue(is_attachment_or_form_title("材料名称：建设项目用地申请表"))
        self.assertTrue(is_attachment_or_form_title("提交条件：需提供……"))

    def test_numbered_prefix_detected(self):
        """编号前缀开头的条目应被检测"""
        self.assertTrue(is_attachment_or_form_title(
            "①县级以上城市规划主管部门出具的城市规划审核意见"))
        self.assertTrue(is_attachment_or_form_title("一、用地预审意见"))
        self.assertTrue(is_attachment_or_form_title("（一）勘测定界报告"))

    def test_application_form_detected(self):
        """申请书/登记表等应被检测"""
        self.assertTrue(is_attachment_or_form_title("建设项目用地申请表"))
        self.assertTrue(is_attachment_or_form_title("土地登记申请书"))

    def test_policy_title_not_detected(self):
        """正常政策标题不应被误判为附件"""
        self.assertFalse(is_attachment_or_form_title(
            "广东省国土资源厅关于印发《省政府审批建设用地报批材料范本（2018年修订版）》的通知"))
        self.assertFalse(is_attachment_or_form_title(
            "自然资源部关于进一步加强耕地保护的通知"))
        self.assertFalse(is_attachment_or_form_title(
            "城乡建设用地增减挂钩管理办法"))


# ═══════════════════════════════════════════════════════════
#  标题候选评分测试
# ═══════════════════════════════════════════════════════════

class TestTitleCandidatesScoring(unittest.TestCase):

    def test_red_header_scores_highest(self):
        """首页红头标题得分应最高"""
        text = """
自然资源部文件
自然资发〔2024〕10号
自然资源部关于进一步加强耕地保护工作的通知

各省、自治区、直辖市自然资源主管部门：

附件1
①耕地保护目标责任考核表
"""
        candidates = extract_title_candidates(text)
        best = candidates[0]
        self.assertIn("自然资源部关于进一步加强耕地保护工作的通知", best["title"])
        self.assertEqual(best["source"], "首页红头")

    def test_attachment_candidate_scores_low(self):
        """附件条目标题得分应很低"""
        text = """
广东省自然资源厅文件
粤自然资发〔2024〕5号
广东省自然资源厅关于加强土地管理的通知

附件1
①用地预审意见

附件2
②规划选址意见书
"""
        candidates = extract_title_candidates(text)
        # 附件条目的得分应很低
        for c in candidates:
            if "用地预审意见" in c["title"] or "规划选址意见书" in c["title"]:
                self.assertTrue(c["score"] <= 30,
                               f"附件条目'{c['title']}'得分{c['score']}不应超过30")

    def test_near_doc_no_gets_bonus(self):
        """靠近文号的标题应获得加分"""
        text = """
广东省自然资源厅文件
粤自然资发〔2024〕5号
广东省自然资源厅关于加强土地管理的通知
"""
        candidates = extract_title_candidates(text)
        best = candidates[0]
        self.assertIn("靠近主文号", best["reason"])

    def test_filename_fallback_low_priority(self):
        """文件名兜底标题得分应最低"""
        text = "这是正文内容，没有明确标题行。"
        candidates = extract_title_candidates(text, file_name="耕地保护管理办法（扫描件）.pdf")
        # 文件名兜底得分应很低
        file_cands = [c for c in candidates if c["source"] == "文件名兜底"]
        if file_cands:
            self.assertLess(file_cands[0]["score"], 30)


# ═══════════════════════════════════════════════════════════
#  文号识别测试
# ═══════════════════════════════════════════════════════════

class TestDocumentNoExtraction(unittest.TestCase):

    def test_primary_doc_no_from_front_page(self):
        """主文号应从首页提取"""
        text = """
广东省国土资源厅文件
粤国土资利用发〔2018〕25号
广东省国土资源厅关于印发……的通知

……根据国土资发〔2015〕10号文件要求……
"""
        result = extract_primary_document_no(text)
        self.assertEqual(result["primary_document_no"], "粤国土资利用发〔2018〕25号")

    def test_referenced_doc_nos_collected(self):
        """正文引用的文号应归入引用文号列表"""
        text = """
广东省自然资源厅文件
粤自然资发〔2024〕5号
广东省自然资源厅关于加强土地管理的通知

根据自然资发〔2023〕10号、粤府〔2022〕3号……现制定本通知。
"""
        result = extract_primary_document_no(text)
        self.assertEqual(result["primary_document_no"], "粤自然资发〔2024〕5号")
        self.assertIn("自然资发〔2023〕10号", result["referenced_document_nos"])
        self.assertIn("粤府〔2022〕3号", result["referenced_document_nos"])

    def test_referenced_not_override_primary(self):
        """引用文号不能覆盖主文号"""
        text = """
广东省自然资源厅文件
粤自然资发〔2024〕5号

根据国土资发〔2015〕10号文件要求，现印发《关于规范用地报批工作的通知》。
"""
        doc_no = extract_document_no(text)
        self.assertEqual(doc_no, "粤自然资发〔2024〕5号")
        self.assertNotEqual(doc_no, "国土资发〔2015〕10号")


# ═══════════════════════════════════════════════════════════
#  发文单位识别测试
# ═══════════════════════════════════════════════════════════

class TestIssuingAuthorityExtraction(unittest.TestCase):

    def test_front_page_red_header_authority(self):
        """'XXX厅文件'格式应提取机关名"""
        text = """
广东省国土资源厅文件
粤国土资利用发〔2018〕25号
"""
        authority = extract_issuing_authority(text)
        self.assertEqual(authority, "广东省国土资源厅")

    def test_recipient_not_authority(self):
        """收文对象不应被当作发文单位"""
        text = """
各地级以上市国土资源主管部门：

根据省厅要求……
"""
        authority = extract_issuing_authority(text)
        self.assertNotEqual(authority, "各地级以上市国土资源主管部门")

    def test_authority_near_yinfa(self):
        """'印发'附近的机构名应被提取"""
        text = """
自然资源部关于印发《某办法》的通知

各省、自治区……
"""
        authority = extract_issuing_authority(text)
        self.assertEqual(authority, "自然资源部")


# ═══════════════════════════════════════════════════════════
#  日期识别测试
# ═══════════════════════════════════════════════════════════

class TestDateExtraction(unittest.TestCase):

    def test_version_year_not_publish_date(self):
        """标题中的'2018年修订版'不是发布日期"""
        text = """
广东省国土资源厅关于印发《省政府审批建设用地报批材料范本（2018年修订版）》的通知

2018年3月15日
"""
        dates = extract_dates(text)
        self.assertNotEqual(dates.get("publish_date"), "2018-01-01")
        # 发布日期应为正文中的 2018-03-15
        self.assertEqual(dates.get("publish_date"), "2018-03-15")


# ═══════════════════════════════════════════════════════════
#  状态推断测试（核心变更）
# ═══════════════════════════════════════════════════════════

class TestStatusInference(unittest.TestCase):

    def test_has_date_not_equals_effective(self):
        """有发布日期不等于现行有效"""
        result = infer_status("普通正文", {"publish_date": "2024-01-15"}, "")
        self.assertEqual(result, "待核实")

    def test_empty_dates_defaults_daiheshi(self):
        """无任何信息默认待核实"""
        result = infer_status("普通正文", {}, "")
        self.assertEqual(result, "待核实")

    def test_expired_date_returns_expired(self):
        """明确的已过期失效日期返回已失效"""
        result = infer_status("", {"publish_date": "2020-01-01"}, "2021-12-31")
        self.assertEqual(result, "已失效")

    def test_abolished_text_returns_abolished(self):
        """明确废止措辞返回已废止"""
        result = infer_status("本办法已废止", {}, "")
        self.assertEqual(result, "已废止")

    def test_web_effective_status_returns_effective(self):
        """网页时效状态'现行有效'返回现行有效"""
        text = """
时效状态：现行有效
发布机构：自然资源部
"""
        result = infer_status(text, {}, "")
        self.assertEqual(result, "现行有效")

    def test_web_abolished_status_returns_abolished(self):
        """网页时效状态'已废止'返回已废止"""
        text = """
时效状态：已废止
"""
        result = infer_status(text, {"publish_date": "2020-01-01"}, "")
        self.assertEqual(result, "已废止")


# ═══════════════════════════════════════════════════════════
#  导入候选校验测试
# ═══════════════════════════════════════════════════════════

class TestImportCandidateValidation(unittest.TestCase):

    def test_attachment_title_not_allowed(self):
        """附件标题不应被验证为可入库"""
        result = validate_import_candidate(
            title="①县级以上城市规划主管部门出具的城市规划审核意见",
            document_no="",
            text="",
            file_name="test.pdf",
        )
        self.assertFalse(result["valid"])
        self.assertIn("附件", result["reason"])

    def test_material_list_not_allowed(self):
        """材料清单条目不应被验证为可入库"""
        result = validate_import_candidate(
            title="材料名称：建设项目用地申请表",
            document_no="",
            text="",
            file_name="test.pdf",
        )
        self.assertFalse(result["valid"])

    def test_low_confidence_not_auto_import(self):
        """低置信度标题不应自动勾选入库"""
        # 模拟文件名兜底场景
        result = extract_title_with_meta(
            "普通文本内容，无明确标题。", file_name="某文件.pdf")
        self.assertTrue(result["needs_manual_review"])
        self.assertEqual(result["confidence"], "低")


# ═══════════════════════════════════════════════════════════
#  重新解析不覆盖人工字段测试
# ═══════════════════════════════════════════════════════════

class TestReparseDoesNotOverwriteManual(unittest.TestCase):

    def test_extract_title_with_meta_returns_candidates(self):
        """extract_title_with_meta 返回候选列表供对比"""
        result = extract_title_with_meta(GD_DOCUMENT_TEXT)
        self.assertIn("candidates", result)
        self.assertGreater(len(result["candidates"]), 0)
        self.assertIn("title_source", result)
        self.assertIn("confidence", result)

    def test_reparse_result_includes_all_fields(self):
        """重新解析结果包含所有对比字段"""
        meta = extract_all_metadata(GD_DOCUMENT_TEXT)
        self.assertIn("title_source", meta)
        self.assertIn("title_confidence", meta)
        self.assertIn("document_no_source", meta)
        self.assertIn("title_candidates", meta)
        self.assertIn("attachment_titles", meta)


# ═══════════════════════════════════════════════════════════
#  附件内容提取测试
# ═══════════════════════════════════════════════════════════

class TestAttachmentContentExtraction(unittest.TestCase):

    def test_attachment_titles_extracted(self):
        """附件标题应被提取到 attachment_titles"""
        att_titles = _extract_attachment_titles(GD_DOCUMENT_TEXT)
        self.assertTrue(len(att_titles) > 0)
        self.assertTrue(any("城市规划审核意见" in t for t in att_titles))
        self.assertTrue(any("用地预审意见" in t for t in att_titles))
        self.assertTrue(any("建设项目用地申请表" in t for t in att_titles))

    def test_attachment_not_in_main_title(self):
        """附件标题不在主标题中"""
        meta = extract_all_metadata(GD_DOCUMENT_TEXT)
        title = meta["title"]
        self.assertNotIn("城市规划审核意见", title)
        self.assertNotIn("用地预审意见", title)
        self.assertNotIn("勘测定界报告", title)


# ═══════════════════════════════════════════════════════════
#  import_validator is_attachment_title 测试
# ═══════════════════════════════════════════════════════════

class TestImportValidatorAttachment(unittest.TestCase):

    def test_is_attachment_title_detected(self):
        """import_validator.is_attachment_title 应检测附件标题"""
        is_att, reason = is_attachment_title(
            "①县级以上城市规划主管部门出具的城市规划审核意见")
        self.assertTrue(is_att)
        self.assertIn("①", reason)

    def test_normal_title_not_attachment(self):
        """正常政策标题不应被判定为附件"""
        is_att, _ = is_attachment_title(
            "广东省国土资源厅关于印发《省政府审批建设用地报批材料范本》的通知")
        self.assertFalse(is_att)

    def test_short_bookmark_maybe_attachment(self):
        """短书名号条目可能是附件"""
        is_att, _ = is_attachment_title("《用地预审意见》")
        self.assertTrue(is_att)


# ═══════════════════════════════════════════════════════════
#  多文号场景测试
# ═══════════════════════════════════════════════════════════

class TestMultiDocNoScenario(unittest.TestCase):

    def test_multiple_doc_nos_collected(self):
        """应收集所有文号"""
        text = """
自然资源部文件
自然资发〔2024〕10号

根据自然资规〔2023〕5号和国土资发〔2015〕20号……
"""
        result = extract_primary_document_no(text)
        self.assertIn("自然资发〔2024〕10号", result["all_document_nos"])
        self.assertIn("自然资规〔2023〕5号", result["all_document_nos"])

    def test_primary_is_front_page(self):
        """主文号应选首页的"""
        text = """
广东省自然资源厅文件
粤自然资发〔2024〕5号

根据自然资发〔2023〕10号……
"""
        result = extract_primary_document_no(text)
        self.assertEqual(result["primary_document_no"], "粤自然资发〔2024〕5号")
        self.assertEqual(result["source"], "首页文号")


if __name__ == "__main__":
    unittest.main(verbosity=2)
