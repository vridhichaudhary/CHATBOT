"""
server.py — Flask backend for the IOCL Laboratory Results Assistant.
Serves the HTML frontend and exposes REST API endpoints.
"""
import os
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, request, jsonify, render_template
from lab_assistant.db import (init_db, run_cleanup, get_all_reports,
                               delete_report, insert_report,
                               insert_lab_results, get_conn)
from lab_assistant.parsers import parse_file
from lab_assistant.chat import answer as lab_answer

app = Flask(__name__, template_folder="templates", static_folder="static")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
MODEL_WATERFALL = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
UPLOADS_DIR = Path("data/uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Initialise DB and clean expired files on startup
init_db()
_cleaned = run_cleanup()


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    reports = get_all_reports()
    total_records = sum(r.get("result_count", 0) for r in reports)
    morning = sum(1 for r in reports if r.get("shift") == "M")
    evening = sum(1 for r in reports if r.get("shift") == "E")

    conn = get_conn()
    samples = conn.execute(
        "SELECT COUNT(DISTINCT sample_name) FROM lab_results"
    ).fetchone()[0]
    conn.close()

    return jsonify({
        "total_reports":   len(reports),
        "total_records":   total_records,
        "morning_count":   morning,
        "evening_count":   evening,
        "unique_samples":  samples,
        "recent_reports":  reports[:8],
        "cleaned_on_boot": _cleaned,
    })


@app.route("/api/reports")
def api_reports():
    return jsonify(get_all_reports())


@app.route("/api/reports/<report_id>", methods=["DELETE"])
def api_delete_report(report_id):
    delete_report(report_id)
    return jsonify({"success": True})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    file = request.files.get("file")
    report_date_str = request.form.get("report_date", str(date.today()))
    uploaded_by     = request.form.get("uploaded_by", "Unknown").strip() or "Unknown"

    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400

    try:
        file_bytes = file.read()
        rows, meta = parse_file(file_bytes, file.filename)
    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {e}"}), 500

    # Shift is auto-detected from the document — never asked from user
    report_date = meta.get("report_date") or report_date_str
    shift       = meta.get("shift") or "Unknown"

    if not rows:
        return jsonify({
            "error": "No data rows extracted. "
                     "Please verify the file contains a data table."
        }), 400

    # Persist original file
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_"
                        for c in file.filename)
    file_path = UPLOADS_DIR / f"{report_date}_{shift}_{safe_name}"
    file_path.write_bytes(file_bytes)

    report_id = insert_report(
        report_date=report_date,
        shift=shift,
        uploaded_by=uploaded_by,
        original_file_name=file.filename,
        file_path=str(file_path),
    )
    insert_lab_results(report_id, rows)

    return jsonify({
        "success":          True,
        "report_id":        report_id,
        "records_extracted": len(rows),
        "detected_date":    report_date,
        "detected_shift":   "Evening" if shift == "E" else
                            "Morning" if shift == "M" else shift,
        "file_name":        file.filename,
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data     = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()

    if not question:
        return jsonify({"error": "No question provided"}), 400

    if not GOOGLE_API_KEY:
        return jsonify({"error": "Google API key not configured on the server."}), 500

    for model in MODEL_WATERFALL:
        try:
            response = lab_answer(question, api_key=GOOGLE_API_KEY, model=model)
            return jsonify({"response": response})
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                continue   # try next model
            return jsonify({"error": err}), 500

    return jsonify({
        "error": "All AI models are temporarily rate-limited. "
                 "Please wait a moment and try again."
    }), 429


if __name__ == "__main__":
    app.run(debug=True, port=5001, host="0.0.0.0")
