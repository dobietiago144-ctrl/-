"""第二批种子数据 + 修正已有文件分类"""
from database.db import init_db, create_document, get_document_by_no, update_document

init_db()

# ═══════════════════════════════════════════
# 先修正已有文件分类
# ═══════════════════════════════════════════
fixes = [
    ("广东省土地管理条例", "地方性法规"),
    ("广东省自然资源厅关于进一步规范征收土地工作的通知", "规范性文件"),
    ("广东省自然资源厅关于进一步规范土地征收成片开发工作的通知", "规范性文件"),
    ("广东省自然资源厅关于进一步规范国有建设用地使用权出让管理相关工作的通知", "规范性文件"),
    ("巩固拓展脱贫攻坚成果同乡村振兴有效衔接过渡期内城乡建设用地增减挂钩节余指标跨省域调剂管理办法", "规范性文件"),
    ("城乡建设用地增减挂钩试点管理办法", "规范性文件"),
    ("自然资源部 农业农村部关于改革完善耕地占补平衡管理的通知", "规范性文件"),
    ("国土资源部 农业部关于加强占补平衡补充耕地质量建设与管理的通知", "规范性文件"),
]

for title, new_cat in fixes:
    doc = get_document_by_no(None)  # can't search by title directly
    # use raw query
    import database.db as db
    all_docs = db.get_all_documents()
    for d in all_docs:
        if d["title"] == title:
            db.update_document(d["id"], {"category": new_cat})
            print(f"  已修正: 《{title}》 → {new_cat}")
            break

# ═══════════════════════════════════════════
# 第二批：常用法律法规
# ═══════════════════════════════════════════
new_docs = [
    # --- 法律 ---
    {
        "title": "中华人民共和国城乡规划法",
        "document_no": "主席令第七十四号",
        "issuing_authority": "全国人民代表大会常务委员会",
        "publish_date": "2007-10-28",
        "effective_date": "2008-01-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "法律",
        "keywords": "城乡规划,控制性详细规划,修建性详细规划,一书两证,规划许可",
        "summary": "2007年通过，2019年第三次修正。确立城乡规划体系（城镇体系规划/城市规划/镇规划/乡规划/村庄规划），实行选址意见书、建设用地规划许可证、建设工程规划许可证、乡村建设规划许可证制度。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "2019年第三次修正。与土地管理法衔接，是土地审批中规划符合性审查的核心依据。",
    },
    {
        "title": "中华人民共和国农村土地承包法",
        "document_no": "主席令第十七号",
        "issuing_authority": "全国人民代表大会常务委员会",
        "publish_date": "2002-08-29",
        "effective_date": "2003-03-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "法律",
        "keywords": "农村土地承包,耕地承包期,草地承包期,林地承包期,三权分置,经营权流转",
        "summary": "2002年通过，2018年第二次修正。耕地承包期30年，草地30-50年，林地30-70年。确立所有权/承包权/经营权三权分置，允许经营权抵押担保。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "2018年修正，新增三权分置制度。与土地管理法关于宅基地和集体建设用地管理互为补充。",
    },
    {
        "title": "中华人民共和国矿产资源法",
        "document_no": "主席令第三十六号",
        "issuing_authority": "全国人民代表大会常务委员会",
        "publish_date": "1986-03-19",
        "effective_date": "1986-10-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "法律",
        "keywords": "矿产资源,矿业权,探矿权,采矿权,有偿取得,储量管理",
        "summary": "1986年通过，1996年修正，2024年修订。确立探矿权采矿权有偿取得制度、矿产资源国家所有原则、储量管理制度。2024年修订版强化了矿区生态修复和安全生产要求。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "2024年11月第十四届全国人大常委会第十二次会议修订通过，是矿产资源管理的基本法。",
    },
    {
        "title": "中华人民共和国环境保护法",
        "document_no": "主席令第九号",
        "issuing_authority": "全国人民代表大会常务委员会",
        "publish_date": "1989-12-26",
        "effective_date": "2015-01-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "法律",
        "keywords": "环境保护,环境影响评价,三同时,生态保护红线,环境监测,信息公开",
        "summary": "2014年修订（史上最严环保法），确立生态保护红线制度、按日连续处罚、查封扣押、限产停产等措施，建设项目须环评审批，防治设施三同时。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "土地整治、增减挂钩等项目中需开展环评的依据。",
    },

    # --- 行政法规 ---
    {
        "title": "基本农田保护条例",
        "document_no": "国务院令第257号",
        "issuing_authority": "国务院",
        "publish_date": "1998-12-27",
        "effective_date": "1999-01-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "行政法规",
        "keywords": "基本农田,保护条例,五不准,占补平衡,禁止占用",
        "summary": "1998年发布，2011年修订。基本农田实行五不准：不准非农建设占用、不准以退耕还林为名减少面积、不准占用进行绿化造林、不准挖塘养鱼和畜禽养殖、不准毁坏耕作层。划定后任何单位和个人不得改变或占用。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "永久基本农田保护的核心法规，与《土地管理法》配套实施。",
    },
    {
        "title": "土地复垦条例",
        "document_no": "国务院令第592号",
        "issuing_authority": "国务院",
        "publish_date": "2011-03-05",
        "effective_date": "2011-03-05",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "行政法规",
        "keywords": "土地复垦,生产建设活动损毁,复垦义务人,复垦费,历史遗留损毁",
        "summary": "谁损毁谁复垦，复垦义务人须编制复垦方案、预存复垦费。历史遗留损毁土地由县级以上政府组织复垦。复垦后优先用于农业。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "增减挂钩项目拆旧区复垦、临时用地复垦的依据。",
    },
    {
        "title": "不动产登记暂行条例",
        "document_no": "国务院令第656号",
        "issuing_authority": "国务院",
        "publish_date": "2014-11-24",
        "effective_date": "2015-03-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "行政法规",
        "keywords": "不动产登记,统一登记,土地登记,房屋登记,林权登记,海域登记",
        "summary": "整合分散在各部门的土地、房屋、林地、草地、海域等不动产登记职责，实行统一登记制度。2019年修订，2024年第二次修订。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "土地供应后产权登记的依据。2019年、2024年两次修订。",
    },
    {
        "title": "地质灾害防治条例",
        "document_no": "国务院令第394号",
        "issuing_authority": "国务院",
        "publish_date": "2003-11-24",
        "effective_date": "2004-03-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "行政法规",
        "keywords": "地质灾害,调查,监测,预报,防治规划,危险性评估,治理责任",
        "summary": "因工程建设等人为活动引发的地质灾害由责任单位治理。在地质灾害易发区内进行工程建设应进行危险性评估，配套治理工程须与主体工程同时设计、施工、验收。",
        "source_type": "手工录入",
        "source_url": "https://www.gov.cn",
        "confirmed": 1,
        "notes": "土地整治项目选址前须做地灾评估的法规依据。",
    },

    # --- 部门规章 ---
    {
        "title": "闲置土地处置办法",
        "document_no": "国土资源部令第53号",
        "issuing_authority": "国土资源部",
        "publish_date": "2012-06-01",
        "effective_date": "2012-07-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "部门规章",
        "keywords": "闲置土地,动工开发,满一年,满两年,闲置费,无偿收回",
        "summary": "未动工满1年征缴土地闲置费（出让或划拨价款的20%），未动工满2年无偿收回。政府原因导致闲置的，可协商有偿收回或置换。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "土地批后监管最常引用的部门规章之一。",
    },
    {
        "title": "建设项目用地预审管理办法",
        "document_no": "国土资源部令第68号",
        "issuing_authority": "国土资源部",
        "publish_date": "2016-11-29",
        "effective_date": "2017-01-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "部门规章",
        "keywords": "用地预审,建设项目,选址,符合规划,占补平衡,初审",
        "summary": "建设项目审批/核准/备案前须完成用地预审。审查内容：是否符合土地利用总体规划、是否符合供地政策、用地标准是否合规、占补平衡方案。2016年修正。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "2016年第三次修正。所有建设项目用地前置审批程序。",
    },
    {
        "title": "土地权属争议调查处理办法",
        "document_no": "国土资源部令第17号",
        "issuing_authority": "国土资源部",
        "publish_date": "2003-01-03",
        "effective_date": "2003-03-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "部门规章",
        "keywords": "土地权属,争议,调解,处理决定,行政复议",
        "summary": "个人之间/个人与单位之间争议由乡级或县级政府处理，单位之间由县级以上政府处理。对处理决定不服可申请行政复议或提起行政诉讼。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "",
    },

    # --- 规范性文件 ---
    {
        "title": "自然资源部 农业农村部 国家林业和草原局关于严格耕地用途管制有关问题的通知",
        "document_no": "自然资发〔2021〕166号",
        "issuing_authority": "自然资源部、农业农村部、国家林业和草原局",
        "publish_date": "2021-11-27",
        "effective_date": "2021-11-27",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "规范性文件",
        "keywords": "耕地用途管制,进出平衡,一般耕地,永久基本农田,占补平衡,种粮",
        "summary": "一般耕地主要用于粮棉油糖菜等农产品生产，永久基本农田重点用于粮食生产。永久基本农田不得转为林地/草地/园地等其他农用地及农业设施建设用地。实行耕地进出平衡。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "与自然资发〔2024〕204号配套，前者管进出平衡和用途，后者管占补平衡。自然资源系统最常引用的通知之一。",
    },
    {
        "title": "自然资源部办公厅关于进一步规范临时用地管理的通知",
        "document_no": "自然资办发〔2021〕42号",
        "issuing_authority": "自然资源部办公厅",
        "publish_date": "2021-09-06",
        "effective_date": "2021-09-06",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "规范性文件",
        "keywords": "临时用地,使用期限,复垦,审批权限,不得修建永久建筑",
        "summary": "临时用地使用期限一般不超过2年，能源/交通/水利等建设周期较长的不超过4年。不得修建永久性建（构）筑物，到期后1年内完成复垦。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "",
    },
    {
        "title": "自然资源部关于进一步做好用地用海要素保障的通知",
        "document_no": "自然资发〔2023〕89号",
        "issuing_authority": "自然资源部",
        "publish_date": "2023-06-09",
        "effective_date": "2023-06-09",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "规范性文件",
        "keywords": "用地保障,用海保障,要素保障,用地审批,先行用地",
        "summary": "优化建设项目用地审批，明确先行用地范围，简化用地预审程序，强化重大项目用地保障。有效期至2025年12月31日。",
        "source_type": "手工录入",
        "source_url": "https://www.mnr.gov.cn",
        "confirmed": 1,
        "notes": "有效期至2025年12月31日，届时可能有延续或调整政策。",
    },

    # --- 技术标准 ---
    {
        "title": "土地利用现状分类",
        "document_no": "GB/T 21010-2017",
        "issuing_authority": "国家质量监督检验检疫总局、国家标准化管理委员会",
        "publish_date": "2017-11-01",
        "effective_date": "2017-11-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "技术标准",
        "keywords": "土地利用分类,地类,耕地,建设用地,未利用地,12个一级类",
        "summary": "国家标准，将土地分为12个一级类、73个二级类。一级类包括：耕地、园地、林地、草地、商服用地、工矿仓储用地、住宅用地、公共管理与公共服务用地、特殊用地、交通运输用地、水域及水利设施用地、其他土地。",
        "source_type": "手工录入",
        "source_url": "https://std.samr.gov.cn",
        "confirmed": 1,
        "notes": "所有土地整治项目地类认定的基础标准。",
    },
    {
        "title": "高标准农田建设 通则",
        "document_no": "GB/T 30600-2022",
        "issuing_authority": "国家市场监督管理总局、国家标准化管理委员会",
        "publish_date": "2022-03-09",
        "effective_date": "2022-10-01",
        "expiry_date": "",
        "status": "现行有效",
        "region": "全国",
        "category": "技术标准",
        "keywords": "高标准农田建设,田块整治,灌溉排水,田间道路,农田防护,地力提升",
        "summary": "2022年修订版，规定了高标准农田建设的田块整治、土壤改良、灌溉与排水、田间道路、农田防护与生态环境保持、农田输配电等技术要求。",
        "source_type": "手工录入",
        "source_url": "https://std.samr.gov.cn",
        "confirmed": 1,
        "notes": "土地整治项目设计的重要技术标准。",
    },

    # --- 广东省地方 ---
    {
        "title": "广东省耕地保护经济补偿办法",
        "document_no": "粤自然资规字〔2023〕1号",
        "issuing_authority": "广东省自然资源厅、广东省财政厅",
        "publish_date": "2023-03-15",
        "effective_date": "2023-04-14",
        "expiry_date": "",
        "status": "现行有效",
        "region": "省",
        "category": "规范性文件",
        "keywords": "耕地保护,经济补偿,补偿标准,省级补助,广东",
        "summary": "建立耕地保护经济补偿机制，对承担永久基本农田保护任务的农村集体经济组织和农户给予经济补偿，省级财政按标准给予补助。有效期5年。",
        "source_type": "手工录入",
        "source_url": "https://nr.gd.gov.cn",
        "confirmed": 1,
        "notes": "",
    },
]

# ═══════════════════════════════════════════
# 导入
# ═══════════════════════════════════════════
print(f"准备导入 {len(new_docs)} 条新文件...")

added = 0
skipped = 0
for doc in new_docs:
    doc_no = doc.get("document_no", "")
    if doc_no:
        existing = get_document_by_no(doc_no)
        if existing:
            print(f"  跳过（已存在）: 《{doc['title']}》")
            skipped += 1
            continue
    doc_id = create_document(doc)
    print(f"  已导入: 《{doc['title']}》 ({doc['category']})")
    added += 1

print()
print(f"新增 {added} 条, 跳过 {skipped} 条")
print("导入完成！")
