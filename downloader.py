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
import shutil
import sys

try:
    import pytesseract
except Exception:
    pytesseract = None


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.metadata_pipeline import (
    update_book_json_with_title_ocr,
    create_page_json_for_page,
)


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


def save_top_title_crop(source_path: Path, target_path: Path) -> bool:
    img = cv2.imread(str(source_path))
    if img is None:
        return False

    height, width = img.shape[:2]

    top = 0
    bottom = int(height * 0.28)
    left = int(width * 0.08)
    right = int(width * 0.92)

    cropped = img[top:bottom, left:right]
    if cropped.size == 0:
        return False

    cv2.imwrite(str(target_path), cropped)
    return True


def preprocess_for_ocr(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)[1]
    return gray


def read_title_crop_ocr(path: Path):
    if pytesseract is None:
        return None, "pytesseract_missing"

    img = cv2.imread(str(path))
    if img is None:
        return None, "image_error"

    gray = preprocess_for_ocr(img)

    try:
        text = pytesseract.image_to_string(gray, lang="deu")
        text = re.sub(r"\s+", " ", text).strip()
        return text, None
    except Exception as e:
        return None, str(e)


def read_page_ocr(path: Path):
    if pytesseract is None:
        return "", "pytesseract_missing"

    img = cv2.imread(str(path))
    if img is None:
        return "", "image_error"

    gray = preprocess_for_ocr(img)

    try:
        text = pytesseract.image_to_string(gray, lang="deu")
        text = re.sub(r"\s+", " ", text).strip()
        return text, None
    except Exception as e:
        return "", str(e)


def extract_ortsteil_from_ocr_text(text):
    if not text:
        return None

    lower = text.lower()

    if "florenberg" in lower:
        return "Florenberg"

    return None


def zoom_out(page):
    try:
        for _ in range(3):
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(800)
    except Exception:
        pass


def save_screenshot(page, path: Path):
    page.screenshot(path=str(path), full_page=True)
    auto_crop_image(path)


def create_pdf(book_dir: Path, pdf_path: Path):
    images = sorted(book_dir.glob("page_*.png"))
    if not images:
        return

    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert([str(p) for p in images]))


def get_page_number_from_url(url: str) -> int:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return int(query.get("pg", ["1"])[0])


def make_page_url(url: str, page_number: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["pg"] = [str(page_number)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def should_auto_rename(book_name: str) -> bool:
    return bool(re.fullmatch(r"book_[a-zA-Z0-9]+", book_name))


def sanitize(text: str):
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\-]", "", text)
    return text


def save_book_metadata(book_dir: Path, meta: dict, source_url: str):
    data = {
        "country": "deutschland",
        "bistum": "fulda",
        "pfarre": meta.get("pfarre_ort"),
        "signatur": meta.get("signatur"),
        "buchtyp": meta.get("buchtyp"),
        "jahr_von": meta.get("datum_von"),
        "jahr_bis": meta.get("datum_bis"),
        "source_url": source_url,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    file_path = book_dir / "book.json"
    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def enrich_book_json_with_ocr(book_dir: Path, title_ocr_text: str):
    book_json_path = book_dir / "book.json"

    if not book_json_path.exists():
        return

    try:
        update_book_json_with_title_ocr(str(book_json_path), title_ocr_text)
    except Exception as e:
        print(f"[WARN] book.json OCR-Anreicherung fehlgeschlagen: {e}")


def create_page_metadata(
    book_dir: Path,
    page_number: int,
    image_path: Path,
    source_url: str,
    ocr_text: str,
):
    try:
        create_page_json_for_page(
            book_folder=str(book_dir),
            page_number=page_number,
            image_file=image_path.name,
            image_path=str(image_path),
            ocr_text=ocr_text or "",
            source_url=source_url,
        )
    except Exception as e:
        print(f"[WARN] page.json konnte nicht erzeugt werden für Seite {page_number}: {e}")


def run_download_job(job_id, url, book_name, save_job_status):
    book_dir = BOOKS_DIR / book_name
    pdf_path = PDF_DIR / f"{book_name}.pdf"
    debug_job_dir = DEBUG_DIR / f"{book_name}_{job_id}"

    book_dir.mkdir(parents=True, exist_ok=True)
    debug_job_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 2200})

        start_page = get_page_number_from_url(url)
        page.goto(url)
        page.wait_for_timeout(5000)

        meta = {
            "pfarre_ort": "Pilgerzell_Hl_Dreifaltigkeit",
            "signatur": "2-04",
            "buchtyp": "Taufbuch",
            "datum_von": "1844",
            "datum_bis": "1873"
        }

        page_num = start_page
        saved_count = 0

        for _ in range(3):
            current_page_url = make_page_url(url, page_num)

            page.goto(current_page_url)
            page.wait_for_timeout(5000)
            zoom_out(page)

            raw_path = debug_job_dir / f"raw_{page_num}.png"
            page.screenshot(path=str(raw_path), full_page=True)

            if page_num == start_page + 1:
                crop_path = debug_job_dir / "title.png"
                crop_ok = save_top_title_crop(raw_path, crop_path)

                if crop_ok:
                    ocr_text, ocr_error = read_title_crop_ocr(crop_path)

                    if ocr_error:
                        print(f"[WARN] Titel-OCR Fehler: {ocr_error}")

                    ortsteil = extract_ortsteil_from_ocr_text(ocr_text)

                    if ortsteil:
                        meta["pfarre_ort"] += f"_{ortsteil}"

                    if should_auto_rename(book_name):
                        new_name = "_".join([
                            sanitize(meta["pfarre_ort"]),
                            meta["signatur"],
                            sanitize(meta["buchtyp"]),
                            f"{meta['datum_von']}_{meta['datum_bis']}"
                        ])

                        new_dir = BOOKS_DIR / new_name
                        if not new_dir.exists():
                            shutil.move(str(book_dir), str(new_dir))
                            book_dir = new_dir
                            book_name = new_name
                            pdf_path = PDF_DIR / f"{book_name}.pdf"

                    save_book_metadata(book_dir, meta, url)

                    if ocr_text:
                        enrich_book_json_with_ocr(book_dir, ocr_text)

            file_path = book_dir / f"page_{page_num}.png"
            save_screenshot(page, file_path)

            page_ocr_text, page_ocr_error = read_page_ocr(file_path)
            if page_ocr_error:
                print(f"[WARN] Seiten-OCR Fehler auf Seite {page_num}: {page_ocr_error}")

            create_page_metadata(
                book_dir=book_dir,
                page_number=page_num,
                image_path=file_path,
                source_url=current_page_url,
                ocr_text=page_ocr_text,
            )

            saved_count += 1

            if save_job_status:
                try:
                    save_job_status(job_id, {
                        "status": "running",
                        "saved_count": saved_count,
                        "current_page": page_num,
                        "book_name": book_name,
                    })
                except Exception as e:
                    print(f"[WARN] save_job_status fehlgeschlagen: {e}")

            page_num += 1
            time.sleep(1)

        book_json = book_dir / "book.json"
        if not book_json.exists():
            save_book_metadata(book_dir, meta, url)

        create_pdf(book_dir, pdf_path)

        if save_job_status:
            try:
                save_job_status(job_id, {
                    "status": "finished",
                    "saved_count": saved_count,
                    "book_name": book_name,
                    "pdf_path": str(pdf_path),
                })
            except Exception as e:
                print(f"[WARN] final save_job_status fehlgeschlagen: {e}")

        browser.close()
