"""数据库表定义和初始化"""

CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
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
);
"""

CREATE_RELATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS document_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    old_document_id INTEGER NOT NULL,
    new_document_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    relation_basis TEXT,
    relation_date TEXT,
    affected_scope TEXT,
    confidence TEXT DEFAULT '待核实',
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (old_document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (new_document_id) REFERENCES documents(id) ON DELETE CASCADE
);
"""

CREATE_REVIEW_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS review_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT,
    uploaded_file_name TEXT,
    uploaded_file_path TEXT,
    extracted_text TEXT,
    extracted_count INTEGER DEFAULT 0,
    risk_high_count INTEGER DEFAULT 0,
    risk_medium_count INTEGER DEFAULT 0,
    risk_low_count INTEGER DEFAULT 0,
    risk_normal_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""

CREATE_REVIEW_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS review_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    original_reference TEXT,
    recognized_title TEXT DEFAULT '',
    recognized_document_no TEXT DEFAULT '',
    matched_document_id INTEGER,
    matched_title TEXT,
    matched_document_no TEXT,
    official_title TEXT DEFAULT '',
    official_document_no TEXT DEFAULT '',
    match_method TEXT,
    match_score REAL,
    document_status TEXT,
    risk_level TEXT,
    problem_type TEXT DEFAULT '',
    judgment_basis TEXT,
    suggested_document_id INTEGER,
    suggested_title TEXT,
    suggestion TEXT,
    confidence TEXT DEFAULT '',
    occurrence_count INTEGER DEFAULT 1,
    location TEXT DEFAULT '',
    is_core_issue INTEGER DEFAULT 0,
    need_manual_confirm INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (task_id) REFERENCES review_tasks(id) ON DELETE CASCADE
);
"""

CREATE_OPERATION_LOGS_TABLE = """
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
);
"""

CREATE_POLICY_MONITOR_IGNORED_URLS_TABLE = """
CREATE TABLE IF NOT EXISTS policy_monitor_ignored_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT DEFAULT '',
    url_hash TEXT DEFAULT '',
    title TEXT DEFAULT '',
    source_name TEXT DEFAULT '',
    ignored_at TEXT DEFAULT (datetime('now','localtime')),
    notes TEXT DEFAULT ''
);
"""

CREATE_POLICY_MONITOR_CANDIDATES_TABLE = """
CREATE TABLE IF NOT EXISTS policy_monitor_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT DEFAULT '',
    source_domain TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    title TEXT DEFAULT '',
    document_no TEXT DEFAULT '',
    publish_date TEXT DEFAULT '',
    source_publish_date TEXT DEFAULT '',
    source_name_text TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    full_text TEXT DEFAULT '',
    candidate_type TEXT DEFAULT '其他',
    detected_keywords TEXT DEFAULT '',
    relation_type_guess TEXT DEFAULT '',
    relation_basis_text TEXT DEFAULT '',
    matched_document_id INTEGER,
    matched_title TEXT DEFAULT '',
    confidence TEXT DEFAULT '',
    affected_items TEXT DEFAULT '',
    status TEXT DEFAULT '待抓取',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    notes TEXT DEFAULT ''
);
"""

ALL_TABLES = [
    CREATE_DOCUMENTS_TABLE,
    CREATE_RELATIONS_TABLE,
    CREATE_REVIEW_TASKS_TABLE,
    CREATE_REVIEW_RESULTS_TABLE,
    CREATE_OPERATION_LOGS_TABLE,
    CREATE_POLICY_MONITOR_CANDIDATES_TABLE,
    CREATE_POLICY_MONITOR_IGNORED_URLS_TABLE,
]

# 部分唯一索引：仅对非空、非空字符串的 document_no 做唯一约束
CREATE_DOCUMENT_NO_UNIQUE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_document_no_unique
ON documents(document_no)
WHERE document_no IS NOT NULL AND document_no != '';
"""
