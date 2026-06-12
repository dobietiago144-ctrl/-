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
        "effective_date", "expiry_date", "source_publish_date",
        "pass_date", "latest_revision_date", "revision_history",
        "source_name",
        "status", "region", "category",
        "keywords", "summary", "full_text", "source_type", "source_url",
        "file_path",
        "business_tags", "sensitivity_level", "importance_level",
        "file_name", "file_size", "file_type",
        "confirmed", "notes",
    ]
    values = {k: data.get(k, "") for k in cols}
    if not values.get("document_no"):
        values["document_no"] = None
    # importance_level 默认值
    if not values.get("importance_level"):
        values["importance_level"] = "一般"
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
        "effective_date", "expiry_date", "source_publish_date",
        "pass_date", "latest_revision_date", "revision_history",
        "source_name",
        "status", "region", "category",
        "keywords", "summary", "full_text", "source_type", "source_url",
        "file_path",
        "business_tags", "sensitivity_level", "importance_level",
        "file_name", "file_size", "file_type",
        "confirmed", "notes",
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
    business_type: str = "",
    importance_level: str = "",
    confirmed: int | None = None,
    limit: int = 200,
    offset: int = 0,
    sensitivity_level: str = "",
) -> list[dict]:
    """搜索文件库"""
    conn = get_connection()
    conditions = []
    params = {}
    if keyword:
        conditions.append(
            "(title LIKE :kw OR document_no LIKE :kw "
            "OR issuing_authority LIKE :kw OR keywords LIKE :kw "
            "OR business_tags LIKE :kw OR full_text LIKE :kw "
            "OR source_url LIKE :kw OR source_name LIKE :kw)"
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
    if business_type:
        conditions.append("business_tags LIKE :bt")
        params["bt"] = f"%{business_type}%"
    if importance_level:
        conditions.append("importance_level = :il")
        params["il"] = importance_level
    if sensitivity_level:
        conditions.append("sensitivity_level = :sl")
        params["sl"] = sensitivity_level
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
    business_type: str = "",
    importance_level: str = "",
    confirmed: int | None = None,
    sensitivity_level: str = "",
) -> int:
    """统计文件数量"""
    conn = get_connection()
    conditions = []
    params = {}
    if keyword:
        conditions.append(
            "(title LIKE :kw OR document_no LIKE :kw "
            "OR issuing_authority LIKE :kw OR keywords LIKE :kw "
            "OR business_tags LIKE :kw OR full_text LIKE :kw "
            "OR source_url LIKE :kw OR source_name LIKE :kw)"
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
    if business_type:
        conditions.append("business_tags LIKE :bt")
        params["bt"] = f"%{business_type}%"
    if importance_level:
        conditions.append("importance_level = :il")
        params["il"] = importance_level
    if sensitivity_level:
        conditions.append("sensitivity_level = :sl")
        params["sl"] = sensitivity_level
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
    """新增新旧关系"""
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
    """更新新旧关系"""
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
    """删除新旧关系"""
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
    """获取所有新旧关系（含文件名，用于列表展示）"""
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
        "task_id", "original_reference", "recognized_title",
        "recognized_document_no", "matched_document_id",
        "matched_title", "matched_document_no", "official_title",
        "official_document_no", "match_method", "match_score",
        "document_status", "risk_level", "problem_type",
        "judgment_basis", "suggested_document_id", "suggested_title",
        "suggestion", "confidence", "occurrence_count",
        "location", "is_core_issue", "need_manual_confirm",
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


# ═══════════════════════════════════════════
#  统计聚合
# ═══════════════════════════════════════════

def get_document_stats(
    keyword: str = "",
    status: str = "",
    region: str = "",
    category: str = "",
    business_type: str = "",
    importance_level: str = "",
    sensitivity_level: str = "",
    confirmed: int | None = None,
) -> dict:
    """获取文件统计概览，按状态/敏感级别/业务类型/重要级别聚合"""
    conn = get_connection()
    conditions = []
    params = {}
    if keyword:
        conditions.append(
            "(title LIKE :kw OR document_no LIKE :kw "
            "OR issuing_authority LIKE :kw OR keywords LIKE :kw "
            "OR business_tags LIKE :kw OR full_text LIKE :kw "
            "OR source_url LIKE :kw OR source_name LIKE :kw)"
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
    if business_type:
        conditions.append("business_tags LIKE :bt")
        params["bt"] = f"%{business_type}%"
    if importance_level:
        conditions.append("importance_level = :il")
        params["il"] = importance_level
    if sensitivity_level:
        conditions.append("sensitivity_level = :sl")
        params["sl"] = sensitivity_level
    if confirmed is not None:
        conditions.append("confirmed = :confirmed")
        params["confirmed"] = confirmed
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    where_and = (" WHERE " + " AND ".join(conditions) + " AND ") if conditions else " WHERE "

    total = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM documents{where}", params
    ).fetchone()["cnt"]

    by_status = {}
    for row in conn.execute(
        f"SELECT status, COUNT(*) AS cnt FROM documents{where} GROUP BY status", params
    ).fetchall():
        by_status[row["status"]] = row["cnt"]

    by_sensitivity = {}
    for row in conn.execute(
        f"SELECT sensitivity_level, COUNT(*) AS cnt FROM documents{where} GROUP BY sensitivity_level", params
    ).fetchall():
        by_sensitivity[row["sensitivity_level"]] = row["cnt"]

    by_business_type = {}
    for row in conn.execute(
        f"SELECT business_tags FROM documents{where_and} business_tags != ''", params
    ).fetchall():
        for tag in row["business_tags"].split(","):
            tag = tag.strip()
            if tag:
                by_business_type[tag] = by_business_type.get(tag, 0) + 1

    by_importance = {}
    for row in conn.execute(
        f"SELECT importance_level, COUNT(*) AS cnt FROM documents{where} GROUP BY importance_level", params
    ).fetchall():
        by_importance[row["importance_level"]] = row["cnt"]

    with_file = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM documents{where_and} file_path != ''", params
    ).fetchone()["cnt"]
    without_file = total - with_file

    conn.close()
    return {
        "total": total,
        "by_status": by_status,
        "by_sensitivity": by_sensitivity,
        "by_business_type": by_business_type,
        "by_importance": by_importance,
        "with_file": with_file,
        "without_file": without_file,
    }


def batch_delete_documents(doc_ids: list[int], delete_files: bool = False) -> dict:
    """批量删除文件记录。
    delete_files=True 时同时删除原文件。
    返回 {"deleted": int, "failed": int, "errors": list}
    """
    deleted = 0
    failed = 0
    errors = []
    logs_to_write = []

    conn = get_connection()
    for doc_id in doc_ids:
        try:
            doc = conn.execute(
                "SELECT * FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if not doc:
                errors.append(f"ID {doc_id}: 文件不存在")
                failed += 1
                continue
            doc_dict = dict(doc)
            file_path = doc_dict.get("file_path", "") or ""
            title = doc_dict.get("title", "") or ""
            sensitivity = doc_dict.get("sensitivity_level", "") or ""

            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

            if delete_files and file_path:
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception as e:
                    errors.append(f"ID {doc_id}: 删除原文件失败 - {e}")

            logs_to_write.append({
                "action": "批量删除文件",
                "target_type": "document",
                "target_id": doc_id,
                "file_name": title,
                "sensitivity_level": sensitivity,
                "notes": f"批量删除，是否删除原文件：{'是' if delete_files else '否'}",
            })
            deleted += 1
        except Exception as e:
            errors.append(f"ID {doc_id}: {e}")
            failed += 1
    conn.commit()
    conn.close()

    # 在事务提交后再写操作日志
    for log_data in logs_to_write:
        try:
            log_operation(log_data)
        except Exception:
            pass

    return {"deleted": deleted, "failed": failed, "errors": errors}


def check_duplicate(title: str = "", document_no: str = "", file_name: str = "",
                    file_size: int = 0, full_text: str = "") -> dict:
    """检查重复文件。
    返回 {"is_duplicate": bool, "reason": str, "existing_ids": list}
    """
    import hashlib
    conn = get_connection()
    existing_ids = []

    # 1. 文号相同
    if document_no:
        row = conn.execute(
            "SELECT id FROM documents WHERE document_no = ? AND document_no != ''",
            (document_no,)
        ).fetchone()
        if row:
            existing_ids.append(row["id"])
            conn.close()
            return {"is_duplicate": True, "reason": "文号重复", "existing_ids": existing_ids}

    # 2. 标题完全相同 + 发文单位相同 → 不在此统查，由调用方判断

    # 3. 文件名 + 文件大小相同
    if file_name and file_size > 0:
        row = conn.execute(
            "SELECT id FROM documents WHERE file_name = ? AND file_size = ?",
            (file_name, file_size)
        ).fetchone()
        if row:
            existing_ids.append(row["id"])
            conn.close()
            return {"is_duplicate": True, "reason": "疑似重复（文件名+大小相同）", "existing_ids": existing_ids}

    # 4. full_text hash
    if full_text:
        text_hash = hashlib.md5(full_text.encode("utf-8", errors="replace")).hexdigest()
        all_docs = conn.execute("SELECT id, full_text FROM documents WHERE full_text != ''").fetchall()
        for d in all_docs:
            d_hash = hashlib.md5(d["full_text"].encode("utf-8", errors="replace")).hexdigest()
            if d_hash == text_hash:
                existing_ids.append(d["id"])
                break
        if existing_ids:
            conn.close()
            return {"is_duplicate": True, "reason": "全文内容重复", "existing_ids": existing_ids}

    conn.close()
    return {"is_duplicate": False, "reason": "", "existing_ids": []}


# ═══════════════════════════════════════════
#  operation_logs 表 CRUD
# ═══════════════════════════════════════════

def log_operation(data: dict) -> int:
    """记录操作日志"""
    conn = get_connection()
    cols = [
        "user_name", "action", "target_type", "target_id",
        "file_name", "sensitivity_level", "client_ip", "notes",
    ]
    defaults = {
        "user_name": "本地用户", "action": "", "target_type": "",
        "target_id": None, "file_name": "", "sensitivity_level": "",
        "client_ip": "", "notes": "",
    }
    values = {k: data.get(k, defaults.get(k, "")) for k in cols}
    placeholders = ", ".join([f":{k}" for k in cols])
    sql = f"INSERT INTO operation_logs ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, values)
    conn.commit()
    log_id = cur.lastrowid
    conn.close()
    return log_id


def get_operation_logs(limit: int = 100) -> list[dict]:
    """获取操作日志"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM operation_logs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def migrate_database():
    """数据库迁移：统一处理表结构调整、索引更新，保证旧数据库自动升级"""
    from database.models import CREATE_DOCUMENT_NO_UNIQUE_INDEX
    conn = get_connection()

    # 1. review_results 新字段迁移
    existing_rr = {r[1] for r in conn.execute("PRAGMA table_info(review_results)").fetchall()}
    new_cols = [
        ("recognized_title", "TEXT DEFAULT ''"),
        ("recognized_document_no", "TEXT DEFAULT ''"),
        ("official_title", "TEXT DEFAULT ''"),
        ("official_document_no", "TEXT DEFAULT ''"),
        ("problem_type", "TEXT DEFAULT ''"),
        ("confidence", "TEXT DEFAULT ''"),
        ("occurrence_count", "INTEGER DEFAULT 1"),
        ("location", "TEXT DEFAULT ''"),
        ("is_core_issue", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_def in new_cols:
        if col_name not in existing_rr:
            conn.execute(f"ALTER TABLE review_results ADD COLUMN {col_name} {col_def}")

    # 1.5 documents 新字段迁移（网页导入日期/沿革）
    existing_d = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    doc_new_cols = [
        ("source_publish_date", "TEXT"),
        ("pass_date", "TEXT"),
        ("latest_revision_date", "TEXT"),
        ("revision_history", "TEXT"),
        ("source_name", "TEXT"),
        ("business_tags", "TEXT DEFAULT ''"),
        ("sensitivity_level", "TEXT DEFAULT '公开'"),
        ("importance_level", "TEXT DEFAULT '一般'"),
        ("file_name", "TEXT DEFAULT ''"),
        ("file_size", "INTEGER DEFAULT 0"),
        ("file_type", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in doc_new_cols:
        if col_name not in existing_d:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_def}")

    # 2. review_tasks 新字段迁移
    existing_rt = {r[1] for r in conn.execute("PRAGMA table_info(review_tasks)").fetchall()}
    rt_new_cols = [
        ("task_name", "TEXT"),
        ("uploaded_file_path", "TEXT"),
        ("extracted_text", "TEXT"),
        ("extracted_count", "INTEGER DEFAULT 0"),
        ("risk_high_count", "INTEGER DEFAULT 0"),
        ("risk_medium_count", "INTEGER DEFAULT 0"),
        ("risk_low_count", "INTEGER DEFAULT 0"),
        ("risk_normal_count", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_def in rt_new_cols:
        if col_name not in existing_rt:
            conn.execute(f"ALTER TABLE review_tasks ADD COLUMN {col_name} {col_def}")

    # 3. documents 表 document_no 唯一约束调整
    # 3a. 尝试删除旧的唯一索引（SQLite 可能通过自动索引实现 UNIQUE）
    try:
        conn.execute("DROP INDEX IF EXISTS idx_documents_document_no_unique")
    except Exception:
        pass

    # 3b. 重建 document_no 列为 TEXT（不再 UNIQUE），如果是从旧表迁移
    # SQLite 不支持直接 DROP UNIQUE，用重建表方式处理
    existing_doc = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "document_no" in existing_doc:
        # 检查是否有旧的唯一约束
        table_info = conn.execute("PRAGMA index_list(documents)").fetchall()
        for idx in table_info:
            idx_name = idx["name"]
            if idx["unique"] and str(idx_name).startswith("sqlite_autoindex_documents"):
                # 这是 UNIQUE 列自动生成的索引，需要重建表
                try:
                    conn.execute("BEGIN TRANSACTION")
                    conn.execute("""
                        CREATE TABLE documents_new (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT NOT NULL,
                            document_no TEXT,
                            issuing_authority TEXT,
                            publish_date TEXT,
                            effective_date TEXT,
                            expiry_date TEXT,
                            source_publish_date TEXT,
                            pass_date TEXT,
                            latest_revision_date TEXT,
                            revision_history TEXT,
                            source_name TEXT,
                            status TEXT DEFAULT '待核实',
                            region TEXT,
                            category TEXT,
                            keywords TEXT,
                            summary TEXT,
                            full_text TEXT,
                            source_type TEXT DEFAULT '手工录入',
                            source_url TEXT,
                            file_path TEXT,
                            business_tags TEXT DEFAULT '',
                            sensitivity_level TEXT DEFAULT '公开',
                            importance_level TEXT DEFAULT '一般',
                            file_name TEXT DEFAULT '',
                            file_size INTEGER DEFAULT 0,
                            file_type TEXT DEFAULT '',
                            confirmed INTEGER DEFAULT 0,
                            notes TEXT,
                            created_at TEXT DEFAULT (datetime('now','localtime')),
                            updated_at TEXT DEFAULT (datetime('now','localtime'))
                        )
                    """)
                    # 按字段名迁移，避免新旧表字段数不一致
                    old_cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
                    new_cols_list = [
                        "id", "title", "document_no", "issuing_authority",
                        "publish_date", "effective_date", "expiry_date",
                        "source_publish_date", "pass_date", "latest_revision_date",
                        "revision_history", "source_name",
                        "status", "region", "category",
                        "keywords", "summary", "full_text",
                        "source_type", "source_url", "file_path",
                        "business_tags", "sensitivity_level", "importance_level",
                        "file_name", "file_size", "file_type",
                        "confirmed", "notes", "created_at", "updated_at",
                    ]
                    common = [c for c in new_cols_list if c in old_cols]
                    cols_str = ", ".join(common)
                    conn.execute(f"INSERT INTO documents_new ({cols_str}) SELECT {cols_str} FROM documents")
                    conn.execute("DROP TABLE documents")
                    conn.execute("ALTER TABLE documents_new RENAME TO documents")
                    conn.execute("COMMIT")
                except Exception as e:
                    conn.execute("ROLLBACK")
                    pass
                break

    # 4. 新增部分唯一索引
    try:
        conn.execute(CREATE_DOCUMENT_NO_UNIQUE_INDEX)
    except Exception:
        pass

    # 4.3 历史数据 importance_level 迁移：为空统一设为"一般"
    try:
        conn.execute(
            "UPDATE documents SET importance_level = '一般' WHERE importance_level IS NULL OR importance_level = ''"
        )
    except Exception:
        pass

    # 4.5 确保 policy_monitor_candidates 有新字段 affected_items
    try:
        existing_pmc = {r[1] for r in conn.execute("PRAGMA table_info(policy_monitor_candidates)").fetchall()}
        if "affected_items" not in existing_pmc:
            conn.execute("ALTER TABLE policy_monitor_candidates ADD COLUMN affected_items TEXT DEFAULT ''")
    except Exception:
        pass

    # 5a. 确保 policy_monitor_ignored_urls 表存在
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS policy_monitor_ignored_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT DEFAULT '',
                url_hash TEXT DEFAULT '',
                title TEXT DEFAULT '',
                source_name TEXT DEFAULT '',
                ignored_at TEXT DEFAULT (datetime('now','localtime')),
                notes TEXT DEFAULT ''
            )
        """)
    except Exception:
        pass

    # 5. 确保 operation_logs 表存在
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT DEFAULT '本地用户',
                action TEXT NOT NULL,
                target_type TEXT DEFAULT '',
                target_id INTEGER,
                file_name TEXT DEFAULT '',
                sensitivity_level TEXT DEFAULT '',
                client_ip TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                notes TEXT DEFAULT ''
            )
        """)
    except Exception:
        pass

    # 6. 清理历史非标准文件状态
    from modules.status_utils import get_migration_sql
    for sql in get_migration_sql():
        try:
            conn.execute(sql)
        except Exception:
            pass

    conn.commit()
    conn.close()


def get_anomaly_documents(limit: int = 500) -> list[dict]:
    """获取标题异常的文档记录。

    异常类型：
    - 标题为空
    - 标题为《》、未识别等占位符
    - 标题包含 PDF 解析提示
    - 标题疑似附件/材料清单
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM documents
           WHERE title IS NULL OR title = ''
              OR title IN ('《》', '未识别', '未识别标题', '无标题', '【未识别标题，请补录】')
              OR title LIKE '%PDF共%'
              OR title LIKE '%仅展示前%'
              OR title LIKE '%仅显示前%'
              OR title LIKE '%完整内容将%'
           ORDER BY updated_at DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clean_document_statuses() -> dict:
    """单独清理历史非标准文件状态，可在页面按钮调用。
    返回 {"updated": int, "non_standard_after": int}
    """
    from modules.status_utils import get_migration_sql, STANDARD_STATUSES
    conn = get_connection()
    updated = 0
    for sql in get_migration_sql():
        try:
            cur = conn.execute(sql)
            updated += cur.rowcount
        except Exception:
            pass
    conn.commit()

    # 检查剩余非标准数量
    non_standard = 0
    for row in conn.execute("SELECT status, COUNT(*) AS cnt FROM documents GROUP BY status").fetchall():
        if row["status"] not in STANDARD_STATUSES:
            non_standard += row["cnt"]
    conn.close()

    log_operation({
        "action": "状态清理",
        "target_type": "document",
        "notes": f"清理了 {updated} 条非标准状态，剩余 {non_standard} 条",
    })
    return {"updated": updated, "non_standard_after": non_standard}


# 保留旧函数名以兼容，内部委托给 migrate_database
def migrate_review_results_add_columns():
    migrate_database()
