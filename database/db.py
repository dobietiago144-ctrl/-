"""数据库连接管理和 CRUD 操作"""

import sqlite3
import os
from config import DB_PATH


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库，创建所有表"""
    from database.models import ALL_TABLES
    conn = get_connection()
    for sql in ALL_TABLES:
        conn.execute(sql)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════
#  documents 表 CRUD
# ═══════════════════════════════════════════

def create_document(data: dict) -> int:
    """新增文件，返回新记录 ID"""
    conn = get_connection()
    cols = [
        "title", "document_no", "issuing_authority", "publish_date",
        "effective_date", "expiry_date", "status", "region", "category",
        "keywords", "summary", "full_text", "source_type", "source_url",
        "file_path", "confirmed", "notes",
    ]
    values = {k: data.get(k, "") for k in cols}
    placeholders = ", ".join([f":{k}" for k in cols])
    sql = f"INSERT INTO documents ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, values)
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return doc_id


def update_document(doc_id: int, data: dict):
    """更新文件"""
    conn = get_connection()
    allowed = [
        "title", "document_no", "issuing_authority", "publish_date",
        "effective_date", "expiry_date", "status", "region", "category",
        "keywords", "summary", "full_text", "source_type", "source_url",
        "file_path", "confirmed", "notes",
    ]
    sets = []
    values = {"id": doc_id}
    for k in allowed:
        if k in data:
            sets.append(f"{k} = :{k}")
            values[k] = data[k]
    sets.append("updated_at = datetime('now','localtime')")
    if sets:
        sql = f"UPDATE documents SET {', '.join(sets)} WHERE id = :id"
        conn.execute(sql, values)
        conn.commit()
    conn.close()


def delete_document(doc_id: int):
    """删除文件（级联删除关联关系）"""
    conn = get_connection()
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


def get_document(doc_id: int) -> dict | None:
    """获取单个文件"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_documents(
    keyword: str = "",
    status: str = "",
    region: str = "",
    category: str = "",
    confirmed: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """搜索文件库"""
    conn = get_connection()
    conditions = []
    params = {}
    if keyword:
        conditions.append(
            "(title LIKE :kw OR document_no LIKE :kw "
            "OR issuing_authority LIKE :kw OR keywords LIKE :kw)"
        )
        params["kw"] = f"%{keyword}%"
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if region:
        conditions.append("region = :region")
        params["region"] = region
    if category:
        conditions.append("category = :category")
        params["category"] = category
    if confirmed is not None:
        conditions.append("confirmed = :confirmed")
        params["confirmed"] = confirmed
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    params["limit"] = limit
    params["offset"] = offset
    sql = f"SELECT * FROM documents{where} ORDER BY updated_at DESC LIMIT :limit OFFSET :offset"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_documents(
    keyword: str = "",
    status: str = "",
    region: str = "",
    category: str = "",
    confirmed: int | None = None,
) -> int:
    """统计文件数量"""
    conn = get_connection()
    conditions = []
    params = {}
    if keyword:
        conditions.append(
            "(title LIKE :kw OR document_no LIKE :kw "
            "OR issuing_authority LIKE :kw OR keywords LIKE :kw)"
        )
        params["kw"] = f"%{keyword}%"
    if status:
        conditions.append("status = :status")
        params["status"] = status
    if region:
        conditions.append("region = :region")
        params["region"] = region
    if category:
        conditions.append("category = :category")
        params["category"] = category
    if confirmed is not None:
        conditions.append("confirmed = :confirmed")
        params["confirmed"] = confirmed
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    row = conn.execute(f"SELECT COUNT(*) AS cnt FROM documents{where}", params).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_all_documents(status: str = "") -> list[dict]:
    """获取全部文件（用于导出），可按状态筛选"""
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM documents WHERE status = ? ORDER BY updated_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document_by_no(document_no: str) -> dict | None:
    """按文号精确查找"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM documents WHERE document_no = ?", (document_no,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_document_by_title(title: str) -> dict | None:
    """按标题精确查找"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM documents WHERE title = ?", (title,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_titles() -> list[dict]:
    """获取所有文件标题（用于模糊匹配）"""
    conn = get_connection()
    rows = conn.execute("SELECT id, title, document_no, status FROM documents").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════
#  document_relations 表 CRUD
# ═══════════════════════════════════════════

def create_relation(data: dict) -> int:
    """新增传承关系"""
    conn = get_connection()
    cols = [
        "old_document_id", "new_document_id", "relation_type",
        "relation_basis", "relation_date", "affected_scope",
        "confidence", "notes",
    ]
    values = {k: data.get(k, "") for k in cols}
    placeholders = ", ".join([f":{k}" for k in cols])
    sql = f"INSERT INTO document_relations ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, values)
    conn.commit()
    rel_id = cur.lastrowid
    conn.close()
    return rel_id


def update_relation(rel_id: int, data: dict):
    """更新传承关系"""
    conn = get_connection()
    allowed = [
        "old_document_id", "new_document_id", "relation_type",
        "relation_basis", "relation_date", "affected_scope",
        "confidence", "notes",
    ]
    sets = []
    values = {"id": rel_id}
    for k in allowed:
        if k in data:
            sets.append(f"{k} = :{k}")
            values[k] = data[k]
    sets.append("updated_at = datetime('now','localtime')")
    if sets:
        sql = f"UPDATE document_relations SET {', '.join(sets)} WHERE id = :id"
        conn.execute(sql, values)
        conn.commit()
    conn.close()


def delete_relation(rel_id: int):
    """删除传承关系"""
    conn = get_connection()
    conn.execute("DELETE FROM document_relations WHERE id = ?", (rel_id,))
    conn.commit()
    conn.close()


def get_relations_for_document(doc_id: int) -> dict:
    """获取一个文件的所有关系（上游+下游）"""
    conn = get_connection()
    # 作为旧文件 → 被哪些新文件替代
    downstream = conn.execute(
        """SELECT r.*, d.title AS new_title, d.document_no AS new_document_no
           FROM document_relations r
           JOIN documents d ON r.new_document_id = d.id
           WHERE r.old_document_id = ?""", (doc_id,)
    ).fetchall()
    # 作为新文件 → 替代了哪些旧文件
    upstream = conn.execute(
        """SELECT r.*, d.title AS old_title, d.document_no AS old_document_no
           FROM document_relations r
           JOIN documents d ON r.old_document_id = d.id
           WHERE r.new_document_id = ?""", (doc_id,)
    ).fetchall()
    conn.close()
    return {
        "downstream": [dict(r) for r in downstream],
        "upstream": [dict(r) for r in upstream],
    }


def get_all_relations() -> list[dict]:
    """获取所有传承关系（含文件名，用于列表展示）"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.*,
                  o.title AS old_title, o.document_no AS old_document_no,
                  n.title AS new_title, n.document_no AS new_document_no
           FROM document_relations r
           JOIN documents o ON r.old_document_id = o.id
           JOIN documents n ON r.new_document_id = n.id
           ORDER BY r.updated_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_replacement(old_doc_id: int) -> list[dict]:
    """查找替代某旧文件的新文件列表"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.*, d.title, d.document_no, d.status
           FROM document_relations r
           JOIN documents d ON r.new_document_id = d.id
           WHERE r.old_document_id = ?""", (old_doc_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════
#  review_tasks 表 CRUD
# ═══════════════════════════════════════════

def create_review_task(data: dict) -> int:
    """创建审查任务"""
    conn = get_connection()
    cols = [
        "task_name", "uploaded_file_name", "uploaded_file_path",
        "extracted_text", "extracted_count", "risk_high_count",
        "risk_medium_count", "risk_low_count", "risk_normal_count",
    ]
    values = {k: data.get(k, "") for k in cols}
    placeholders = ", ".join([f":{k}" for k in cols])
    sql = f"INSERT INTO review_tasks ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, values)
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


def update_review_task(task_id: int, data: dict):
    """更新审查任务统计"""
    conn = get_connection()
    allowed = [
        "extracted_count", "risk_high_count", "risk_medium_count",
        "risk_low_count", "risk_normal_count",
    ]
    sets = []
    values = {"id": task_id}
    for k in allowed:
        if k in data:
            sets.append(f"{k} = :{k}")
            values[k] = data[k]
    if sets:
        sql = f"UPDATE review_tasks SET {', '.join(sets)} WHERE id = :id"
        conn.execute(sql, values)
        conn.commit()
    conn.close()


def get_review_task(task_id: int) -> dict | None:
    """获取审查任务"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM review_tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_review_tasks(limit: int = 50) -> list[dict]:
    """获取审查任务列表"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM review_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_review_task(task_id: int):
    """删除审查任务（级联删除审查结果）"""
    conn = get_connection()
    conn.execute("DELETE FROM review_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════
#  review_results 表 CRUD
# ═══════════════════════════════════════════

def create_review_result(data: dict) -> int:
    """新增单条审查结果"""
    conn = get_connection()
    cols = [
        "task_id", "original_reference", "matched_document_id",
        "matched_title", "matched_document_no", "match_method",
        "match_score", "document_status", "risk_level",
        "judgment_basis", "suggested_document_id", "suggested_title",
        "suggestion", "need_manual_confirm",
    ]
    values = {k: data.get(k, None) for k in cols}
    placeholders = ", ".join([f":{k}" for k in cols])
    sql = f"INSERT INTO review_results ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, values)
    conn.commit()
    result_id = cur.lastrowid
    conn.close()
    return result_id


def get_review_results(task_id: int) -> list[dict]:
    """获取某次审查的全部结果"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM review_results WHERE task_id = ? ORDER BY id", (task_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """获取首页统计数据"""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) AS cnt FROM documents").fetchone()["cnt"]
    valid = conn.execute(
        "SELECT COUNT(*) AS cnt FROM documents WHERE status = '现行有效'"
    ).fetchone()["cnt"]
    abolished = conn.execute(
        "SELECT COUNT(*) AS cnt FROM documents WHERE status IN ('已废止','已失效')"
    ).fetchone()["cnt"]
    unconfirmed = conn.execute(
        "SELECT COUNT(*) AS cnt FROM documents WHERE confirmed = 0"
    ).fetchone()["cnt"]
    review_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM review_tasks"
    ).fetchone()["cnt"]
    conn.close()
    return {
        "total": total,
        "valid": valid,
        "abolished": abolished,
        "unconfirmed": unconfirmed,
        "review_count": review_count,
    }
