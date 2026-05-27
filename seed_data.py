"""种子数据：从官网收集的自然资源领域常用政策法规"""
from database.db import init_db, create_document, create_relation, get_document_by_no

init_db()

# ═══════════ 国家级法律法规和政策文件 ═══════════
national_docs = [
    {
        "title": "中华人民共和国土地管理法",
        "document_no": "主席令第三十二号",
        "issuing_authority": "全国人民代表大会常务委员会",
        "publish_date": "2019-08-26",
        "effective_date": "2020-01-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "法律",
        "keywords": "土地管理,耕地保护,永久基本农田,建设用地,土地征收,宅基地",
        "summary": "2019年第三次修正，2020年1月1日施行。七大突破：集体经营性建设用地入市、改革征地制度、完善宅基地制度、多规合一、永久基本农田、央地审批分权、土地督察入法。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "第三次修正。首次1986年通过，1988年第一次修正，1998年修订，2004年第二次修正。",
    },
    {
        "title": "中华人民共和国土地管理法实施条例",
        "document_no": "国务院令第743号",
        "issuing_authority": "国务院",
        "publish_date": "2021-07-02",
        "effective_date": "2021-09-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "行政法规",
        "keywords": "土地管理法,实施条例,耕地保护,建设用地,土地征收",
        "summary": "2021年修订，配合新《土地管理法》实施。细化耕地保护补偿、集体经营性建设用地入市程序、土地征收程序等规定。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "",
    },
    {
        "title": "永久基本农田保护红线管理办法",
        "document_no": "自然资源部、农业农村部令第17号",
        "issuing_authority": "自然资源部、农业农村部",
        "publish_date": "2025-09-01",
        "effective_date": "2025-10-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "部门规章",
        "keywords": "永久基本农田,耕地保护,红线管理,粮食安全",
        "summary": "2025年发布，自2025年10月1日起施行。落实最严格耕地保护制度，强化永久基本农田划定、保护、监管和用途管制。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "最新发布的永久基本农田保护部门规章",
    },
    {
        "title": "自然资源部 农业农村部关于改革完善耕地占补平衡管理的通知",
        "document_no": "自然资发〔2024〕204号",
        "issuing_authority": "自然资源部、农业农村部",
        "publish_date": "2024-09-30",
        "effective_date": "2024-09-30",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "政策文件",
        "keywords": "耕地占补平衡,耕地保护,以补定占,省域平衡",
        "summary": "将各类占用耕地行为统一纳入占补平衡管理，建立以省域耕地总量动态平衡为核心的新机制，实行年度算大账。自2025年1月1日起不再受理按原管理方式落实占补平衡的建设用地申请。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "同时废止国土资发〔2009〕168号",
    },
    {
        "title": "国土资源部 农业部关于加强占补平衡补充耕地质量建设与管理的通知",
        "document_no": "国土资发〔2009〕168号",
        "issuing_authority": "国土资源部、农业部",
        "publish_date": "2009-01-01",
        "effective_date": "2009-01-01",
        "expiry_date": "2024-09-30",
        "status": "已废止",
        "region": "全国",
        "category": "政策文件",
        "keywords": "占补平衡,补充耕地,质量建设",
        "summary": "已被自然资发〔2024〕204号废止。",
        "source_type": "手工录入",
        "source_url": "",
        "confirmed": 1,
        "notes": "被自然资发〔2024〕204号明文废止",
    },
    {
        "title": "城乡建设用地增减挂钩试点管理办法",
        "document_no": "国土资发〔2008〕138号",
        "issuing_authority": "国土资源部",
        "publish_date": "2008-06-27",
        "effective_date": "2008-06-27",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "政策文件",
        "keywords": "增减挂钩,城乡建设用地,土地整治,拆旧建新,指标周转",
        "summary": "将拟整理复垦为耕地的农村建设用地（拆旧地块）和拟用于城镇建设的地块（建新地块）等面积组成项目区，通过建新拆旧实现耕地面积不减少、建设用地总量不增加。挂钩周转指标归还期限一般不超过3年。",
        "source_type": "手工录入",
        "source_url": "https://gk.mnr.gov.cn/zc/zxgfxwj/201702/t20170206_1436480.html",
        "confirmed": 1,
        "notes": "",
    },
    {
        "title": "巩固拓展脱贫攻坚成果同乡村振兴有效衔接过渡期内城乡建设用地增减挂钩节余指标跨省域调剂管理办法",
        "document_no": "自然资发〔2021〕178号",
        "issuing_authority": "自然资源部",
        "publish_date": "2021-01-01",
        "effective_date": "2021-01-01",
        "expiry_date": "2025-12-31",
        "status": "即将失效",
        "region": "全国",
        "category": "政策文件",
        "keywords": "增减挂钩,跨省域调剂,乡村振兴,脱贫攻坚",
        "summary": "设立5年过渡期，继续开展增减挂钩节余指标跨省域调剂。适用范围为国家乡村振兴重点帮扶县。有效期至2025年12月31日，目前自然资源部尚无延续该政策的明确意向。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "2025年12月31日到期，需持续关注后续政策",
    },
    {
        "title": "节约集约利用土地规定",
        "document_no": "自然资源部令第5号",
        "issuing_authority": "自然资源部",
        "publish_date": "2019-01-01",
        "effective_date": "2019-01-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "部门规章",
        "keywords": "节约集约用地,建设用地标准,土地供应,用地审批",
        "summary": "规范建设用地标准控制、土地供应管理、用地审批监管等，推动土地资源节约集约利用。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "2019年修正",
    },
]

# ═══════════ 广东省地方法规和政策文件 ═══════════
guangdong_docs = [
    {
        "title": "广东省土地管理条例",
        "document_no": "广东省第十三届人民代表大会常务委员会公告第113号",
        "issuing_authority": "广东省人民代表大会常务委员会",
        "publish_date": "2022-06-01",
        "effective_date": "2022-08-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "省",
        "category": "法律",
        "keywords": "土地管理,耕地保护,国土空间规划,征地补偿,宅基地,广东",
        "summary": "共8章55条。永久基本农田一般应占耕地总面积80%以上，实行征地补偿费用预存制度，宅基地面积标准：平原/城市郊区≤80㎡，丘陵≤120㎡，山区≤150㎡。同时废止《广东省实施〈中华人民共和国土地管理法〉办法》。",
        "source_type": "手工录入",
        "source_url": "http://nr.gd.gov.cn/gkmlpt/content/3/3979/post_3979057.html",
        "confirmed": 1,
        "notes": "",
    },
    {
        "title": "广东省自然资源厅关于进一步规范征收土地工作的通知",
        "document_no": "粤自然资规字〔2024〕6号",
        "issuing_authority": "广东省自然资源厅",
        "publish_date": "2024-12-19",
        "effective_date": "2025-01-18",
        "expiry_date": "",
        "status": "现行有效",
        "region": "省",
        "category": "政策文件",
        "keywords": "征收土地,征地程序,补偿安置,预公告,广东",
        "summary": "规范征收土地行为，包括合理确定征收范围、依法履行征收土地前期工作程序（预公告、现状调查、社会稳定风险评估、补偿安置方案公告、补偿登记、签订协议）、征收土地申请和批后实施。有效期5年。",
        "source_type": "手工录入",
        "source_url": "https://nr.gd.gov.cn",
        "confirmed": 1,
        "notes": "",
    },
    {
        "title": "广东省自然资源厅关于进一步规范土地征收成片开发工作的通知",
        "document_no": "粤自然资规字〔2024〕7号",
        "issuing_authority": "广东省自然资源厅",
        "publish_date": "2024-12-30",
        "effective_date": "2025-01-29",
        "expiry_date": "",
        "status": "现行有效",
        "region": "省",
        "category": "政策文件",
        "keywords": "成片开发,土地征收,公益性用地,审批程序,广东",
        "summary": "明确成片开发范围须位于城镇建设用地范围内，公益性用地比例要求（广深佛莞中心城区≥40%，其他地区≥30%，城镇开发边界外≥20%），明确省市县三级审批程序。有效期4年。",
        "source_type": "手工录入",
        "source_url": "https://nr.gd.gov.cn",
        "confirmed": 1,
        "notes": "",
    },
    {
        "title": "广东省自然资源厅关于进一步规范国有建设用地使用权出让管理相关工作的通知",
        "document_no": "粤自然资规字〔2024〕8号",
        "issuing_authority": "广东省自然资源厅",
        "publish_date": "2024-10-31",
        "effective_date": "2024-11-30",
        "expiry_date": "",
        "status": "现行有效",
        "region": "省",
        "category": "政策文件",
        "keywords": "国有建设用地,使用权出让,净地出让,招拍挂,广东",
        "summary": "规范土地出让前期工作、出让方案制定、招拍挂公告发布、出让合同管理、信息公开等。强调净地出让、禁止违规设置竞买条件、禁止变相减免出让价款。有效期5年。",
        "source_type": "手工录入",
        "source_url": "https://nr.gd.gov.cn",
        "confirmed": 1,
        "notes": "",
    },
]

all_docs = national_docs + guangdong_docs

print(f"准备导入 {len(all_docs)} 条政策文件...")

for doc in all_docs:
    doc_no = doc.get("document_no", "")
    if doc_no:
        existing = get_document_by_no(doc_no)
        if existing:
            print(f"  跳过（已存在）: 《{doc['title']}》")
            continue
    doc_id = create_document(doc)
    print(f"  已导入: 《{doc['title']}》 (ID={doc_id})")

print()
print("--- 建立新旧关系 ---")

# 自然资发〔2024〕204号 废止 国土资发〔2009〕168号
old = get_document_by_no("国土资发〔2009〕168号")
new = get_document_by_no("自然资发〔2024〕204号")
if old and new:
    create_relation({
        "old_document_id": old["id"],
        "new_document_id": new["id"],
        "relation_type": "废止",
        "relation_basis": "自然资发〔2024〕204号明确废止国土资发〔2009〕168号",
        "relation_date": "2024-09-30",
        "affected_scope": "全文废止",
        "confidence": "人工确认",
        "notes": "",
    })
    print(f"  关系: 自然资发〔2024〕204号 废止 国土资发〔2009〕168号")

# 广东省土地管理条例 替代 广东省实施《中华人民共和国土地管理法》办法
guangdong = get_document_by_no("广东省第十三届人民代表大会常务委员会公告第113号")
if guangdong:
    # 广东省实施《中华人民共和国土地管理法》办法（已废止）- not in our DB currently
    print(f"  提示: 《广东省土地管理条例》替代了原《广东省实施〈中华人民共和国土地管理法〉办法》")

print()
print("导入完成！")
