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


def parse_positive_int(value):
    text = str(value or "").strip()
    if not text:
        return None

    try:
        number = int(text)
    except Exception:
        return None

    if number < 1:
        return None

    return number


def normalize_page_range(start_page, end_page):
    start_value = parse_positive_int(start_page)
    end_value = parse_positive_int(end_page)

    if start_value is not None and end_value is not None and end_value < start_value:
        start_value, end_value = end_value, start_value

    return start_value, end_value


def calculate_total_pages_target(start_page, end_page, default_value=15):
    if start_page is not None and end_page is not None:
        return max((end_page - start_page + 1), 1)

    if start_page is not None and end_page is None:
        return default_value

    if start_page is None and end_page is not None:
        return end_page

    return default_value


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
    status = normalize_status_label(payload.get("status", ""))

    if status == "fertig":
        return "fertig"
    if status == "fehler":
        return "fehler"
    if status == "abgebrochen":
        return "abgebrochen"

    message = str(payload.get("message", "")).lower()

    if "pdf" in message:
        return "pdf"
    if "nachlade" in message or "retry" in message or "nachgeladen" in message:
        return "retry"
    if "metadaten" in message:
        return "metadaten"
    if "prüfe startseite" in message or "startseite" in message:
        return "startseite"
    if "lade quellseite" in message or "gespeichert"
