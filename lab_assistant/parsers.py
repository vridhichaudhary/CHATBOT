"""
parsers.py — File parsers for HTML, Excel/CSV, and PDF lab report files.

Rules:
- Dynamic column detection (no hardcoded parameter names).
- Blank/null values are NEVER stored.
- Each non-empty cell → one {sample_name, parameter_name, parameter_value} record.
"""
import re
import io
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


# ── Utility ───────────────────────────────────────────────────────────────────

_BLANK = {"", "nan", "none", "-", "--", "n/a", "na", "#n/a", "nil"}

def _clean(v) -> str | None:
    """Return None if blank, else return string value."""
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in _BLANK:
        return None
    return s


def _df_to_rows(df: pd.DataFrame) -> list[dict]:
    """
    Convert a DataFrame to a list of lab result rows.
    Assumption: column[0] is Sample Name; rest are parameter columns.
    Only non-empty values are emitted.
    """
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty or df.shape[1] < 2:
        return []

    # Flatten MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(c) for c in col if str(c) != "nan").strip()
                      for col in df.columns]

    # Ensure string columns
    df.columns = [str(c).strip() for c in df.columns]

    sample_col = df.columns[0]
    param_cols = df.columns[1:]

    rows = []
    for _, row in df.iterrows():
        sample = _clean(row[sample_col])
        if not sample:
            continue

        for param in param_cols:
            val = _clean(row[param])
            if val is None:
                continue
            param_name = str(param).strip()
            if not param_name or param_name.lower() in _BLANK:
                continue
            rows.append({
                "sample_name":     sample,
                "parameter_name":  param_name,
                "parameter_value": val,
            })
    return rows


# ── Auto-detect shift & date from filename / content ─────────────────────────

_SHIFT_RE = re.compile(r"\b(morning|evening|m\b|e\b)\b", re.I)
_DATE_RE  = re.compile(r"(\d{2})[.\-/](\d{2})[.\-/](\d{4})")   # dd.mm.yyyy

def detect_metadata(file_name: str, content_text: str = "") -> dict:
    """
    Try to extract shift and report_date from the filename and/or file content.
    Returns dict with keys 'shift' (None/'M'/'E') and 'report_date' (None/ISO str).
    """
    text = file_name + " " + content_text

    # Shift
    shift = None
    m = _SHIFT_RE.search(text)
    if m:
        w = m.group(1).lower()
        shift = "E" if w in ("evening", "e") else "M"

    # Date (dd.mm.yyyy)
    report_date = None
    dm = _DATE_RE.search(text)
    if dm:
        dd, mm, yyyy = dm.groups()
        report_date = f"{yyyy}-{mm}-{dd}"   # ISO

    return {"shift": shift, "report_date": report_date}


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_html(file_bytes: bytes) -> tuple[list[dict], dict]:
    """Parse .html / .htm lab report. Returns (rows, detected_metadata)."""
    text = file_bytes.decode("utf-8", errors="ignore")
    meta = detect_metadata("", text)

    rows = []
    try:
        tables = pd.read_html(io.StringIO(text), flavor="lxml")
    except Exception:
        tables = []

    for df in tables:
        rows.extend(_df_to_rows(df))

    return rows, meta


def parse_excel(file_bytes: bytes, file_name: str) -> tuple[list[dict], dict]:
    """Parse .xlsx / .xls lab report. Returns (rows, detected_metadata)."""
    meta = detect_metadata(file_name)

    rows = []
    try:
        xls = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, header=0)
        for _sheet, df in xls.items():
            rows.extend(_df_to_rows(df))
    except Exception:
        pass

    return rows, meta


def parse_csv(file_bytes: bytes, file_name: str) -> tuple[list[dict], dict]:
    """Parse .csv lab report."""
    meta = detect_metadata(file_name)
    rows = []
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
        rows.extend(_df_to_rows(df))
    except Exception:
        pass
    return rows, meta


def parse_pdf(file_bytes: bytes, file_name: str) -> tuple[list[dict], dict]:
    """Parse PDF lab report using pdfplumber."""
    import pdfplumber

    meta = detect_metadata(file_name)
    content_text = ""
    rows = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            content_text += page.extract_text() or ""
            for table in (page.extract_tables() or []):
                if not table or len(table) < 2:
                    continue
                headers = [str(h).strip() if h else "" for h in table[0]]
                for row_data in table[1:]:
                    sample = _clean(row_data[0]) if row_data else None
                    if not sample:
                        continue
                    for idx, param in enumerate(headers[1:], 1):
                        if idx >= len(row_data):
                            continue
                        val = _clean(row_data[idx])
                        if val is None or not param.strip():
                            continue
                        rows.append({
                            "sample_name":     sample,
                            "parameter_name":  param.strip(),
                            "parameter_value": val,
                        })

    # refine metadata from text
    if not meta["shift"] or not meta["report_date"]:
        extra = detect_metadata(file_name, content_text)
        meta["shift"] = meta["shift"] or extra["shift"]
        meta["report_date"] = meta["report_date"] or extra["report_date"]

    return rows, meta


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_file(file_bytes: bytes,
               file_name: str) -> tuple[list[dict], dict]:
    """Route file to correct parser. Returns (rows, detected_metadata)."""
    ext = Path(file_name).suffix.lower().lstrip(".")
    if ext in ("html", "htm"):
        return parse_html(file_bytes)
    elif ext in ("xlsx", "xls"):
        return parse_excel(file_bytes, file_name)
    elif ext == "csv":
        return parse_csv(file_bytes, file_name)
    elif ext == "pdf":
        return parse_pdf(file_bytes, file_name)
    else:
        raise ValueError(f"Unsupported file type: .{ext}")
