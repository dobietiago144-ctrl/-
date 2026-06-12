"""业务类型自动分类"""

from config import BUSINESS_TYPE_KEYWORDS


def classify_business_tags(title: str = "", keywords: str = "", full_text: str = "") -> list[str]:
    """根据标题、关键词和正文自动分类业务类型，返回标签列表"""
    scores = {}
    for btype, kws in BUSINESS_TYPE_KEYWORDS.items():
        if btype == "其他":
            continue
        score = 0
        # 标题匹配 +5
        if title:
            for kw in kws:
                if kw in title:
                    score += 5
        # 关键词字段匹配 +3
        if keywords:
            for kw in kws:
                if kw in keywords:
                    score += 3
        # 正文前5000字匹配 +1
        if full_text:
            prefix = full_text[:5000]
            for kw in kws:
                if kw in prefix:
                    score += 1
        if score >= 3:
            scores[btype] = score

    result = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    if not result:
        return []
    return result
