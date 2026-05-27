"""数据库表定义和初始化"""

CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    document_no TEXT UNIQUE,
    issuing_authority TEXT,
    publish_date TEXT,
    effective_date TEXT,
    expiry_date TEXT,
    status TEXT DEFAULT '待核实',
    region TEXT,
    category TEXT,
    keywords TEXT,
    summary TEXT,
    full_text TEXT,
    source_type TEXT DEFAULT '手工录入',
    source_url TEXT,
    file_path TEXT,
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
    matched_document_id INTEGER,
    matched_title TEXT,
    matched_document_no TEXT,
    match_method TEXT,
    match_score REAL,
    document_status TEXT,
    risk_level TEXT,
    judgment_basis TEXT,
    suggested_document_id INTEGER,
    suggested_title TEXT,
    suggestion TEXT,
    need_manual_confirm INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (task_id) REFERENCES review_tasks(id) ON DELETE CASCADE
);
"""

ALL_TABLES = [
    CREATE_DOCUMENTS_TABLE,
    CREATE_RELATIONS_TABLE,
    CREATE_REVIEW_TASKS_TABLE,
    CREATE_REVIEW_RESULTS_TABLE,
]
