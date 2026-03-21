from flask import Flask, render_template, request, redirect, send_from_directory, jsonify
from pathlib import Path
import json
import threading
import uuid
from datetime import datetime, timedelta
from downloader import run_download_job

app = Flask(__name__)

APP_DISPLAY_VERSION = "v1.1.2"
BUILD_DATE = "2026-03-21"

DATA_DIR = Path("/app/data")
BOOKS_DIR = DATA_DIR / "books"
PDF_DIR = DATA_DIR / "pdf"
JOBS_DIR = DATA_DIR / "jobs"
VERSION_FILE = Path("/app/version.json")

BOOKS_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def format_seconds_hms(seconds):
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def normalize_status_label(status: str) -> str:
    value = str(status or "").strip().lower()

    mapping = {
        "started": "gestartet",
        "starting": "gestartet",
        "running": "läuft",
        "finished": "fertig",
        "done": "fertig",
        "error": "fehler",
        "failed": "fehler",
        "cancelled": "abgebrochen",
        "canceled": "abgebrochen",
        "aborted": "abgebrochen",
        "gestartet": "gestartet",
        "läuft": "läuft",
        "fertig": "fertig",
        "fehler": "fehler",
        "abgebrochen": "abgebrochen",
    }

    return mapping.get(value, value or "unbekannt")


def status_css_class(status: str) -> str:
    value = normalize_status_label(status)

    mapping = {
        "gestartet": "starting",
        "läuft": "running",
        "fertig": "finished",
        "fehler": "error",
        "abgebrochen": "cancelled",
    }

    return mapping.get(value, "unknown")


def infer_phase(payload: dict) -> str:
    if payload.get("phase"):
        return str(payload["phase"])

    message = str(payload.get("message", "")).lower()
    status = normalize_status_label(payload.get("status", ""))

    if "pdf" in message:
        return "pdf"
    if "nachlade" in message or "retry" in message or "nachgeladen" in message:
        return "retry"
    if "metadaten" in message:
        return "metadaten"
    if "prüfe startseite" in message or "startseite" in message:
        return "startseite"
    if "lade quellseite" in message or "gespeichert" in message:
        return "download"
    if status == "fertig":
        return "fertig"
    if status == "fehler":
        return "fehler"
    if status == "abgebrochen":
        return "abgebrochen"
    if status == "gestartet":
        return "gestartet"
    return "läuft"


def phase_label(phase: str) -> str:
    mapping = {
        "gestartet": "Gestartet",
        "metadaten": "Metadaten",
        "startseite": "Startseite suchen",
        "download": "Download",
        "retry": "Nachladen",
        "pdf": "PDF erzeugen",
        "fertig": "Fertig",
        "fehler": "Fehler",
        "abgebrochen": "Abgebrochen",
        "läuft": "Läuft",
    }
    return mapping.get(str(phase or "").lower(), str(phase or "").capitalize())


def enrich_job_metrics(job: dict) -> dict:
    job = dict(job or {})

    status = normalize_status_label(job.get("status"))
    job["status"] = status
    job["status_class"] = status_css_class(status)

    pages = job.get("pages", job.get("saved_count", 0))
    saved_count = job.get("saved_count", pages)

    try:
        pages = int(pages or 0)
    except Exception:
        pages = 0

    try:
        saved_count = int(saved_count or 0)
    except Exception:
        saved_count = 0

    job["pages"] = pages
    job["saved_count"] = saved_count

    started_at = job.get("started_at") or job.get("created_at")
    finished_at = job.get("finished_at")

    if not started_at:
        started_at = now_iso()

    job["created_at"] = started_at
    job["started_at"] = started_at
    if finished_at:
        job["finished_at"] = finished_at

    started_dt = parse_iso(started_at)
    finished_dt = parse_iso(finished_at)

    runtime_seconds = None
    if started_dt is not None:
        if status in ("fertig", "fehler", "abgebrochen") and finished_dt is not None:
            runtime_seconds = max(0, int((finished_dt - started_dt).total_seconds()))
        else:
            runtime_seconds = max(0, int((datetime.now() - started_dt).total_seconds()))

    job["runtime_seconds"] = runtime_seconds
    job["runtime_text"] = format_seconds_hms(runtime_seconds)

    avg_seconds = None
    if runtime_seconds is not None and saved_count > 0:
        avg_seconds = round(runtime_seconds / saved_count, 1)

    job["avg_seconds_per_page"] = avg_seconds
    job["avg_seconds_per_page_text"] = None if avg_seconds is None else f"{avg_seconds:.1f} s"

    total_pages_target = job.get("total_pages_target", 15)
    try:
        total_pages_target = int(total_pages_target or 15)
    except Exception:
        total_pages_target = 15

    if total_pages_target < saved_count:
        total_pages_target = saved_count

    job["total_pages_target"] = total_pages_target

    phase = infer_phase(job)
    job["phase"] = phase
    job["phase_label"] = phase_label(phase)

    estimated_remaining_seconds = None
    if status in ("gestartet", "läuft") and avg_seconds is not None and phase in ("download", "startseite", "metadaten"):
        remaining_pages = max(total_pages_target - saved_count, 0)
        estimated_remaining_seconds = int(round(remaining_pages * avg_seconds))

    job["estimated_remaining_seconds"] = estimated_remaining_seconds
    job["estimated_remaining_text"] = format_seconds_hms(estimated_remaining_seconds)

    if status in ("fertig", "fehler", "abgebrochen"):
        job["current_page"] = None

    return job


def load_version_info():
    version = APP_DISPLAY_VERSION
    date = BUILD_DATE

    if VERSION_FILE.exists():
        try:
            data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
            version = str(data.get("version") or version)
            date = str(data.get("date") or date)
        except Exception:
            pass

    return {
        "version": version,
        "date": date,
        "text": f"{version} • {date}",
    }


def save_job_status(job_id, status):
    job_file = JOBS_DIR / f"{job_id}.json"

    existing = {}
    if job_file.exists():
        try:
            existing = json.loads(job_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    incoming = dict(status or {})
    payload = dict(existing)
    payload.update(incoming)

    payload["job_id"] = payload.get("job_id", job_id)

    normalized_status = normalize_status_label(payload.get("status"))
    payload["status"] = normalized_status
    payload["status_class"] = status_css_class(normalized_status)

    original_started_at = existing.get("started_at") or existing.get("created_at") or incoming.get("started_at") or incoming.get("created_at") or now_iso()

    payload["created_at"] = original_started_at
    payload["started_at"] = original_started_at
    payload["pages"] = payload.get("pages", payload.get("saved_count", 0))
    payload["saved_count"] = payload.get("saved_count", payload.get("pages", 0))
    payload["message"] = payload.get("message", "")
    payload["phase"] = infer_phase(payload)
    payload["total_pages_target"] = payload.get("total_pages_target", existing.get("total_pages_target", 15))

    if normalized_status in ("fertig", "fehler", "abgebrochen"):
        payload["finished_at"] = existing.get("finished_at") or incoming.get("finished_at") or now_iso()

    payload = enrich_job_metrics(payload)

    job_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def load_job_status(job_id):
    job_file = JOBS_DIR / f"{job_id}.json"
    if not job_file.exists():
        return None

    job = json.loads(job_file.read_text(encoding="utf-8"))
    return enrich_job_metrics(job)


def cleanup_old_jobs():
    now = datetime.now()

    for job_file in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))
            created_at = job.get("started_at") or job.get("created_at")
            status = normalize_status_label(job.get("status", ""))

            if not created_at:
                continue

            created_dt = datetime.fromisoformat(created_at)
            age = now - created_dt

            if status == "fertig" and age > timedelta(days=7):
                job_file.unlink(missing_ok=True)
            elif status in ("fehler", "abgebrochen") and age > timedelta(days=2):
                job_file.unlink(missing_ok=True)
        except Exception:
            pass


def load_all_jobs():
    jobs = []
    cutoff = datetime.now() - timedelta(minutes=10)

    for job_file in sorted(JOBS_DIR.glob("*.json")):
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))

            status = normalize_status_label(job.get("status", ""))
            started_at = job.get("started_at") or job.get("created_at")

            if started_at and status in ("gestartet", "läuft"):
                try:
                    started_dt = datetime.fromisoformat(started_at)
                    if started_dt < cutoff:
                        job["status"] = "abgebrochen"
                        job["status_class"] = status_css_class("abgebrochen")
                        job["message"] = "Job war zu lange aktiv und wurde als abgebrochen markiert."
                        save_job_status(job["job_id"], job)
                        job = json.loads(job_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            jobs.append(enrich_job_metrics(job))
        except Exception:
            pass

    jobs = sorted(jobs, key=lambda x: x.get("started_at", x.get("created_at", "")), reverse=True)
    return jobs


def load_books():
    books = []
    for folder in sorted(BOOKS_DIR.glob("*")):
        if folder.is_dir():
            pdf_name = f"{folder.name}.pdf"
            pdf_exists = (PDF_DIR / pdf_name).exists()
            image_count = len(list(folder.glob("page_*.png")))
            books.append({
                "name": folder.name,
                "image_count": image_count,
                "pdf_exists": pdf_exists,
                "pdf_name": pdf_name
            })
    return books


def load_pdfs():
    pdfs = []
    for pdf_file in sorted(PDF_DIR.glob("*.pdf")):
        pdfs.append({
            "name": pdf_file.name
        })
    return pdfs


@app.route("/")
def index():
    cleanup_old_jobs()
    books = load_books()
    jobs = load_all_jobs()
    version_info = load_version_info()
    return render_template(
        "index.html",
        active_page="start",
        books=books,
        jobs=jobs,
        pdfs=[],
        auto_refresh=True,
        version=version_info["text"],
        version_info=version_info
    )


@app.route("/books")
def books_overview():
    cleanup_old_jobs()
    books = load_books()
    version_info = load_version_info()
    return render_template(
        "index.html",
        active_page="books",
        books=books,
        jobs=[],
        pdfs=[],
        auto_refresh=False,
        version=version_info["text"],
        version_info=version_info
    )


@app.route("/pdfs")
def pdfs_overview():
    cleanup_old_jobs()
    pdfs = load_pdfs()
    version_info = load_version_info()
    return render_template(
        "index.html",
        active_page="pdfs",
        books=[],
        jobs=[],
        pdfs=pdfs,
        auto_refresh=False,
        version=version_info["text"],
        version_info=version_info
    )


@app.route("/jobs")
def jobs_overview():
    cleanup_old_jobs()
    jobs = load_all_jobs()
    version_info = load_version_info()
    return render_template(
        "index.html",
        active_page="jobs",
        books=[],
        jobs=jobs,
        pdfs=[],
        auto_refresh=True,
        version=version_info["text"],
        version_info=version_info
    )


@app.route("/start", methods=["POST"])
def start_download():
    url = request.form.get("book_url", "").strip()

    if not url:
        return redirect("/")

    job_id = str(uuid.uuid4())[:8]
    manual_book_name = request.form.get("book_name", "").strip()

    internal_book_name = manual_book_name or f"book_{job_id}"
    display_book_name = manual_book_name or "Automatisch ermitteln..."

    started = now_iso()

    status = {
        "job_id": job_id,
        "url": url,
        "book_name": display_book_name,
        "status": "gestartet",
        "status_class": "starting",
        "message": "Job wurde angelegt.",
        "created_at": started,
        "started_at": started,
        "pages": 0,
        "saved_count": 0,
        "current_page": None,
        "phase": "gestartet",
        "total_pages_target": 15,
    }
    save_job_status(job_id, status)

    def worker():
        run_download_job(job_id, url, internal_book_name, save_job_status)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return redirect("/")


@app.route("/job/<job_id>")
def job_status(job_id):
    status = load_job_status(job_id)
    if not status:
        return jsonify({"error": "Job nicht gefunden"}), 404
    return jsonify(status)


@app.route("/api/jobs")
def api_jobs():
    cleanup_old_jobs()
    jobs = load_all_jobs()
    return jsonify(jobs)


@app.route("/books/<book_name>")
def show_book(book_name):
    book_dir = BOOKS_DIR / book_name
    if not book_dir.exists():
        return "Buch nicht gefunden", 404

    images = sorted([p.name for p in book_dir.glob("page_*.png")])
    pdf_name = f"{book_name}.pdf"
    pdf_exists = (PDF_DIR / pdf_name).exists()
    version_info = load_version_info()

    return render_template(
        "book.html",
        book_name=book_name,
        images=images,
        pdf_exists=pdf_exists,
        pdf_name=pdf_name,
        version=version_info["text"],
        version_info=version_info
    )


@app.route("/books/<book_name>/<filename>")
def serve_book_image(book_name, filename):
    return send_from_directory(BOOKS_DIR / book_name, filename)


@app.route("/pdf/<filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
