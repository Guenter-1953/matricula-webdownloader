from playwright.sync_api import sync_playwright
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import img2pdf
import hashlib
import random
import time
import cv2
import re
import json


DATA_DIR = Path("/app/data")
BOOKS_DIR = DATA_DIR / "books"
PDF_DIR = DATA_DIR / "pdf"
DEBUG_DIR = DATA_DIR / "debug"

BOOKS_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def human_pause() -> int:
    return random.randint(8, 18)


def auto_crop_image(path: Path) -> None:
    img = cv2.imread(str(path))
    if img is None:
        return

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blur, 200, 255, cv2.THRESH_BINARY_INV)[1]

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return

    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)
    cropped = img[y:y + h, x:x + w]
    cv2.imwrite(str(path), cropped)


def zoom_out(page) -> None:
    try:
        page.mouse.move(800, 600)
        page.wait_for_timeout(500)

        for _ in range(3):
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(900)
    except Exception:
        pass


def save_screenshot(page, path: Path) -> None:
    page.screenshot(path=str(path), full_page=True)
    auto_crop_image(path)


def create_pdf(book_dir: Path, pdf_path: Path) -> None:
    images = sorted(book_dir.glob("page_*.png"))
    if not images:
        return

    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert([str(p) for p in images]))


def detect_total_pages(page):
    possible_selectors = [
        "body",
        ".ui-panel",
        ".ui-layout-east",
        ".ui-layout-center",
        "[class*='page']",
        "[class*='viewer']",
        "[class*='list']",
        "[class*='navigation']",
    ]

    patterns = [
        r"(\d+)\s*/\s*(\d+)",
        r"Seite\s+\d+\s+von\s+(\d+)",
        r"Page\s+\d+\s+of\s+(\d+)",
    ]

    for sel in possible_selectors:
        try:
            text = page.locator(sel).first.inner_text(timeout=3000)
            if not text:
                continue

            for pattern in patterns:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    if len(m.groups()) == 2:
                        return int(m.group(2))
                    if len(m.groups()) == 1:
                        return int(m.group(1))
        except Exception:
            pass

    return None


def format_eta(seconds: int | None) -> str | None:
    if seconds is None or seconds < 0:
        return None

    if seconds < 60:
        return f"{seconds}s"

    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"

    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def get_page_number_from_url(url: str) -> int:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    try:
        return int(query.get("pg", ["1"])[0])
    except Exception:
        return 1


def make_page_url(url: str, page_number: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["pg"] = [str(page_number)]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def is_probably_valid_book_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def get_image_info(page):
    info = {
        "img_count": 0,
        "first_img_src": None,
        "canvas_count": 0,
        "title": None,
        "body_excerpt": None,
    }

    try:
        imgs = page.locator("img")
        info["img_count"] = imgs.count()
        if info["img_count"] > 0:
            try:
                info["first_img_src"] = imgs.first.get_attribute("src")
            except Exception:
                pass
    except Exception:
        pass

    try:
        canvases = page.locator("canvas")
        info["canvas_count"] = canvases.count()
    except Exception:
        pass

    try:
        info["title"] = page.title()
    except Exception:
        pass

    try:
        body_text = page.locator("body").inner_text(timeout=2000)
        info["body_excerpt"] = body_text[:1000]
    except Exception:
        pass

    return info


def run_download_job(job_id, url, book_name, save_job_status):
    book_dir = BOOKS_DIR / book_name
    pdf_path = PDF_DIR / f"{book_name}.pdf"
    debug_job_dir = DEBUG_DIR / f"{book_name}_{job_id}"

    book_dir.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    debug_job_dir.mkdir(parents=True, exist_ok=True)

    total_pages = None
    created_at = datetime.now().isoformat(timespec="seconds")
    start_ts = time.time()
    debug_rows = []

    def update(status, message="", pages=0):
        payload = {
            "job_id": job_id,
            "url": url,
            "book_name": book_name,
            "status": status,
            "message": message,
            "pages": pages,
            "created_at": created_at,
            "updated_at": datetime.now().isoformat(timespec="seconds")
        }

        if total_pages is not None:
            payload["total_pages"] = total_pages

            if pages > 0 and total_pages > 0:
                progress_percent = int((pages / total_pages) * 100)
                payload["progress_percent"] = min(progress_percent, 100)

                elapsed = max(1, int(time.time() - start_ts))
                pages_per_second = pages / elapsed
                remaining_pages = max(0, total_pages - pages)

                if pages_per_second > 0 and remaining_pages > 0:
                    eta_seconds = int(remaining_pages / pages_per_second)
                    payload["eta_seconds"] = eta_seconds
                    payload["eta_text"] = format_eta(eta_seconds)
                else:
                    payload["eta_seconds"] = 0
                    payload["eta_text"] = "0s"
            else:
                payload["progress_percent"] = 0
                payload["eta_seconds"] = None
                payload["eta_text"] = None

        save_job_status(job_id, payload)

    def write_debug():
        debug_file = debug_job_dir / "debug.json"
        debug_file.write_text(
            json.dumps(debug_rows, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    if not is_probably_valid_book_url(url):
        update("fehler", f"Ungültige URL: {url}", 0)
        return

    update("läuft", "Browser wird gestartet.", 0)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 2200})

        try:
            start_page = get_page_number_from_url(url)

            update("läuft", f"Buch wird geöffnet ab Seite {start_page}.", 0)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            zoom_out(page)

            total_pages = detect_total_pages(page)

            if total_pages:
                update("läuft", f"Buch geöffnet. Insgesamt {total_pages} Seiten erkannt.", 0)
            else:
                update("läuft", "Buch geöffnet. Gesamtseitenzahl konnte nicht erkannt werden.", 0)

            page_num = start_page
            saved_count = 0
            last_hash = None

            for _ in range(3):
                target_url = make_page_url(url, page_num)

                wait_seconds = human_pause()
                update("läuft", f"Öffne Seite {page_num} nach {wait_seconds}s Wartezeit.", saved_count)
                time.sleep(wait_seconds)

                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(7000)
                zoom_out(page)
                page.wait_for_timeout(2000)

                raw_path = debug_job_dir / f"raw_page_{page_num:04d}.png"
                page.screenshot(path=str(raw_path), full_page=True)
                raw_hash = hash_file(raw_path)

                file_path = book_dir / f"page_{page_num:04d}.png"
                save_screenshot(page, file_path)
                cropped_hash = hash_file(file_path)

                info = get_image_info(page)
                info["target_page"] = page_num
                info["target_url"] = target_url
                info["page_url_after_load"] = page.url
                info["raw_hash"] = raw_hash
                info["cropped_hash"] = cropped_hash
                info["saved_count_before"] = saved_count
                debug_rows.append(info)
                write_debug()

                if last_hash is not None and cropped_hash == last_hash:
                    update("fehler", f"Seite {page_num} ist weiterhin identisch zur vorherigen Seite. Debug-Dateien wurden gespeichert.", saved_count)
                    return

                last_hash = cropped_hash
                saved_count += 1
                update("läuft", f"Seite {page_num} gespeichert.", saved_count)

                page_num += 1

            update("fertig", f"Debug-Test abgeschlossen. {saved_count} Seiten gespeichert.", saved_count)
            create_pdf(book_dir, pdf_path)

        except Exception as e:
            update("fehler", str(e), 0)

        finally:
            write_debug()
            browser.close()
