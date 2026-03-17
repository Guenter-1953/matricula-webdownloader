from playwright.sync_api import sync_playwright
from pathlib import Path
import img2pdf
import hashlib
import random
import time
import cv2
import re


DATA_DIR = Path("/app/data")
BOOKS_DIR = DATA_DIR / "books"
PDF_DIR = DATA_DIR / "pdf"


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


def find_next_button(page):
    selectors = [
        "button[title='Nächste Seite']",
        "button[title='Next page']",
        "[aria-label='Nächste Seite']",
        "[aria-label='Next page']",
        "button:has-text('Nächste Seite')",
        "button:has-text('Next page')",
        "button:has-text('Next')",
    ]

    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

    return None


def zoom_out(page) -> None:
    try:
        page.mouse.move(800, 600)
        page.wait_for_timeout(400)

        for _ in range(3):
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(600)
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
            text = page.locator(sel).first.inner_text(timeout=2000)
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


def run_download_job(job_id, url, book_name, save_job_status):
    book_dir = BOOKS_DIR / book_name
    pdf_path = PDF_DIR / f"{book_name}.pdf"

    book_dir.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    total_pages = None

    def update(status, message="", pages=0):
        payload = {
            "job_id": job_id,
            "url": url,
            "book_name": book_name,
            "status": status,
            "message": message,
            "pages": pages,
            "created_at": __import__("datetime").datetime.now().isoformat(timespec="seconds")
        }

        if total_pages is not None:
            payload["total_pages"] = total_pages

        save_job_status(job_id, payload)

    update("läuft", "Browser wird gestartet.", 0)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 2200})

        try:
            update("läuft", "Buch wird geöffnet.", 0)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            total_pages = detect_total_pages(page)

            if total_pages:
                update("läuft", f"Buch geöffnet. Insgesamt {total_pages} Seiten erkannt.", 0)
            else:
                update("läuft", "Buch geöffnet. Gesamtseitenzahl konnte nicht erkannt werden.", 0)

            update("läuft", "Ansicht wird verkleinert.", 0)
            zoom_out(page)

            page_num = 1
            last_hash = None

            while True:
                file_path = book_dir / f"page_{page_num:04d}.png"

                if total_pages:
                    update("läuft", f"Seite {page_num} von {total_pages} wird geladen.", page_num)
                else:
                    update("läuft", f"Seite {page_num} wird geladen.", page_num)

                save_screenshot(page, file_path)
                current_hash = hash_file(file_path)

                if current_hash == last_hash:
                    file_path.unlink(missing_ok=True)
                    update("fertig", "Keine neue Seite mehr erkannt. Download abgeschlossen.", page_num - 1)
                    break

                last_hash = current_hash

                if total_pages:
                    update("läuft", f"Seite {page_num} von {total_pages} gespeichert.", page_num)
                else:
                    update("läuft", f"Seite {page_num} gespeichert.", page_num)

                next_button = find_next_button(page)

                if not next_button:
                    update("läuft", "Keine weitere Seite gefunden. PDF wird erzeugt.", page_num)
                    break

                try:
                    wait_seconds = human_pause()

                    if total_pages:
                        update(
                            "läuft",
                            f"Seite {page_num} von {total_pages} fertig. Warte {wait_seconds} Sekunden bis zur nächsten Seite.",
                            page_num
                        )
                    else:
                        update(
                            "läuft",
                            f"Seite {page_num} fertig. Warte {wait_seconds} Sekunden bis zur nächsten Seite.",
                            page_num
                        )

                    time.sleep(wait_seconds)
                    next_button.click()
                    page.wait_for_timeout(1500)
                except Exception:
                    update("läuft", "Weiterblättern nicht möglich. PDF wird erzeugt.", page_num)
                    break

                page_num += 1

            update("läuft", "PDF wird erzeugt.", page_num)
            create_pdf(book_dir, pdf_path)
            update("fertig", "Download abgeschlossen.", page_num)

        except Exception as e:
            update("fehler", str(e), 0)

        finally:
            browser.close()