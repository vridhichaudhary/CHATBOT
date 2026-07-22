"""
db.py — PostgreSQL (Supabase) database schema, CRUD helpers, and 7-day auto-cleanup.

Replaces the previous SQLite implementation. All data now lives in Supabase
PostgreSQL, so it survives Render's ephemeral file system restarts.
"""
import uuid
import os
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

DATABASE_URL   = os.getenv("DATABASE_URL", "")
SUPABASE_URL   = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
STORAGE_BUCKET = "lab-reports"

# Keep DB_PATH as a dummy for backward compat with chat.py's SQL agent
DB_PATH = "lab_results_pg"


def get_conn() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def init_db():
    """Create tables if they don't exist (PostgreSQL syntax)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id          TEXT PRIMARY KEY,
            upload_date        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            report_date        TEXT NOT NULL,
            shift              TEXT NOT NULL,
            uploaded_by        TEXT,
            original_file_name TEXT,
            storage_path       TEXT,
            expires_at         TIMESTAMPTZ NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lab_results (
            result_id        SERIAL PRIMARY KEY,
            report_id        TEXT    NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
            report_date      TEXT    NOT NULL,
            shift            TEXT    NOT NULL,
            sample_name      TEXT,
            parameter_name   TEXT    NOT NULL,
            parameter_value  TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_lr_report    ON lab_results(report_id);
        CREATE INDEX IF NOT EXISTS idx_lr_sample    ON lab_results(sample_name);
        CREATE INDEX IF NOT EXISTS idx_lr_param     ON lab_results(parameter_name);
        CREATE INDEX IF NOT EXISTS idx_r_date_shift ON lab_results(report_date, shift);
    """)
    conn.commit()
    cur.close()
    conn.close()


# ── CRUD ──────────────────────────────────────────────────────────────────────

def insert_report(report_date: str, shift: str, uploaded_by: str,
                  original_file_name: str, file_path: str,
                  storage_path: str = "") -> str:
    """Insert a report row. Returns the new report_id."""
    now        = datetime.now()
    report_id  = str(uuid.uuid4())
    expires_at = (now + timedelta(days=7)).isoformat()
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        """INSERT INTO reports
           (report_id, upload_date, report_date, shift, uploaded_by,
            original_file_name, storage_path, expires_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (report_id, now.isoformat(), report_date, shift, uploaded_by,
         original_file_name, storage_path, expires_at)
    )
    conn.commit()
    cur.close()
    conn.close()
    return report_id


def insert_lab_results(report_id: str, rows: list[dict]):
    """Bulk-insert parsed lab result rows."""
    if not rows:
        return
    conn = get_conn()
    cur  = conn.cursor()
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO lab_results
           (report_id, report_date, shift, sample_name, parameter_name, parameter_value)
           VALUES (%(report_id)s, %(report_date)s, %(shift)s,
                   %(sample_name)s, %(parameter_name)s, %(parameter_value)s)""",
        [{"report_id": report_id, **r} for r in rows]
    )
    conn.commit()
    cur.close()
    conn.close()


def get_all_reports() -> list[dict]:
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT r.*,
               COUNT(lr.result_id) AS result_count
        FROM   reports r
        LEFT JOIN lab_results lr ON r.report_id = lr.report_id
        GROUP  BY r.report_id
        ORDER  BY r.upload_date DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def delete_report(report_id: str):
    """Delete a report, its lab data, and the file from Supabase Storage."""
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    row = cur.execute(
        "SELECT storage_path FROM reports WHERE report_id=%s", (report_id,)
    )
    row = cur.fetchone()
    if row and row.get("storage_path"):
        try:
            sb = get_supabase()
            sb.storage.from_(STORAGE_BUCKET).remove([row["storage_path"]])
        except Exception:
            pass
    cur.execute("DELETE FROM reports WHERE report_id=%s", (report_id,))
    conn.commit()
    cur.close()
    conn.close()


def query_results(report_date: str | None = None,
                  shift: str | None = None,
                  sample_filter: str | None = None,
                  parameter_filter: str | None = None) -> list[dict]:
    """Flexible query function used by the chatbot."""
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    sql = """
        SELECT lr.report_date, lr.shift, lr.sample_name,
               lr.parameter_name, lr.parameter_value
        FROM   lab_results lr
        WHERE  1=1
    """
    params: list = []
    if report_date:
        sql += " AND lr.report_date = %s"
        params.append(report_date)
    if shift:
        sql += " AND UPPER(lr.shift) = %s"
        params.append(shift.upper())
    if sample_filter:
        sql += " AND LOWER(lr.sample_name) LIKE %s"
        params.append(f"%{sample_filter.lower()}%")
    if parameter_filter:
        sql += " AND LOWER(lr.parameter_name) LIKE %s"
        params.append(f"%{parameter_filter.lower()}%")
    sql += " ORDER BY lr.report_date DESC, lr.shift, lr.sample_name, lr.parameter_name"

    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ── 7-day automatic cleanup ───────────────────────────────────────────────────

def run_cleanup() -> int:
    """Delete all reports older than 7 days from DB and Supabase Storage."""
    now  = datetime.now().isoformat()
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT report_id, storage_path FROM reports WHERE expires_at < %s", (now,)
    )
    expired = cur.fetchall()

    sb = get_supabase() if expired else None
    for row in expired:
        if row.get("storage_path"):
            try:
                sb.storage.from_(STORAGE_BUCKET).remove([row["storage_path"]])
            except Exception:
                pass
        cur.execute("DELETE FROM reports WHERE report_id=%s", (row["report_id"],))

    conn.commit()
    cur.close()
    conn.close()
    return len(expired)
