from flask import Flask, render_template, request, redirect, send_from_directory, jsonify
from pathlib import Path
import json
import threading
import uuid
from datetime import datetime, timedelta
from downloader import run_download_job
from utils.version import get_git_version

app = Flask(__name__)

BUILD_DATE = "2026-03-16"


def get_app_version_text():
    git_version = get_git_version()
    return f"{git_version} • {BUILD_DATE}"


DATA_DIR = Path("/app/data")
BOOKS_DIR = DATA_DIR / "books"
PDF_DIR = DATA_DIR / "pdf"
JOBS_DIR = DATA_DIR / "jobs"

BOOKS_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def save_job_status(job_id, status):
    job_file = JOBS_DIR / f"{job_id}.json"
    job_file.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")


def load_job_status(job_id):
    job_file = JOBS_DIR / f"{job_id}.json"
    if not job_file.exists():
        return None
    return json.loads(job_file.read_text(encoding="utf-8"))


def cleanup_old_jobs():
    now = datetime.now()

    for job_file in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))
            created_at = job.get("created_at")
            status = str(job.get("status", "")).lower()

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

            status = str(job.get("status", "")).lower()
            created_at = job.get("created_at")

            if created_at and status in ("gestartet", "läuft"):
                try:
                    created_dt = datetime.fromisoformat(created_at)
                    if created_dt < cutoff:
                        job["status"] = "abgebrochen"
                        job["message"] = "Job war zu lange aktiv und wurde als abgebrochen markiert."
                        save_job_status(job["job_id"], job)
                except Exception:
                    pass

            jobs.append(job)
        except Exception:
            pass

    jobs = sorted(jobs, key=lambda x: x.get("created_at", ""), reverse=True)
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
    return render_template(
        "index.html",
        active_page="start",
        books=books,
        jobs=jobs,
        pdfs=[],
        auto_refresh=True,
        version=get_app_version_text()
    )


@app.route("/books")
def books_overview():
    cleanup_old_jobs()
    books = load_books()
    return render_template(
        "index.html",
        active_page="books",
        books=books,
        jobs=[],
        pdfs=[],
        auto_refresh=False,
        version=get_app_version_text()
    )


@app.route("/pdfs")
def pdfs_overview():
    cleanup_old_jobs()
    pdfs = load_pdfs()
    return render_template(
        "index.html",
        active_page="pdfs",
        books=[],
        jobs=[],
        pdfs=pdfs,
        auto_refresh=False,
        version=get_app_version_text()
    )


@app.route("/jobs")
def jobs_overview():
    cleanup_old_jobs()
    jobs = load_all_jobs()
    return render_template(
        "index.html",
        active_page="jobs",
        books=[],
        jobs=jobs,
        pdfs=[],
        auto_refresh=True,
        version=get_app_version_text()
    )


@app.route("/start", methods=["POST"])
def start_download():
    url = request.form.get("book_url", "").strip()

    if not url:
        return redirect("/")

    job_id = str(uuid.uuid4())[:8]
    book_name = request.form.get("book_name", "").strip()

    status = {
        "job_id": job_id,
        "url": url,
        "book_name": book_name or f"book_{job_id}",
        "status": "gestartet",
        "message": "Job wurde angelegt.",
        "created_at": now_iso(),
        "pages": 0
    }
    save_job_status(job_id, status)

    def worker():
        run_download_job(job_id, url, book_name or f"book_{job_id}", save_job_status)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    return redirect("/")


@app.route("/job/<job_id>")
def job_status(job_id):
    status = load_job_status(job_id)
    if not status:
        return jsonify({"error": "Job nicht gefunden"}), 404
    return jsonify(status)


@app.route("/books/<book_name>")
def show_book(book_name):
    book_dir = BOOKS_DIR / book_name
    if not book_dir.exists():
        return "Buch nicht gefunden", 404

    images = sorted([p.name for p in book_dir.glob("page_*.png")])
    pdf_name = f"{book_name}.pdf"
    pdf_exists = (PDF_DIR / pdf_name).exists()

    return render_template(
        "book.html",
        book_name=book_name,
        images=images,
        pdf_exists=pdf_exists,
        pdf_name=pdf_name
    )


@app.route("/books/<book_name>/<filename>")
def serve_book_image(book_name, filename):
    return send_from_directory(BOOKS_DIR / book_name, filename)


@app.route("/pdf/<filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
