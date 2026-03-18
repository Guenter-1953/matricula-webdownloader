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


def short_pause() -> float:
    return round(random.uniform(1.2, 3.8), 2)


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

    top = int(height * 0.12)
    bottom = int(height * 0.88)
    left = int(width * 0.08)
    right = int(width * 0.92)

    cropped = img[top:bottom, left:right]
    if cropped.size == 0:
        return False

    cv2.imwrite(str(target_path), cropped)
    return True


def preprocess_for_title_ocr(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.threshold(gray, 190, 255, cv2.THRESH_BINARY)[1]
    return gray


def preprocess_for_page_ocr(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)[1]
    return gray


def ocr_image(img, psm: int = 6):
    if pytesseract is None:
        return "", "pytesseract_missing"

    try:
        config = f"--oem 3 --psm {psm}"
        text = pytesseract.image_to_string(img, lang="deu", config=config)
        text = re.sub(r"\s+", " ", text).strip()
        return text, None
    except Exception as e:
        return "", str(e)


def read_title_crop_ocr(path: Path):
    if pytesseract is None:
        return None, "pytesseract_missing"

    img = cv2.imread(str(path))
    if img is None:
        return None, "image_error"

    processed = preprocess_for_title_ocr(img)

    text, error = ocr_image(processed, psm=6)
    if text:
        return text, error

    text, error = ocr_image(processed, psm=11)
    return text, error


def read_page_ocr(path: Path):
    if pytesseract is None:
        return "", "pytesseract_missing"

    img = cv2.imread(str(path))
    if img is None:
        return "", "image_error"

    processed = preprocess_for_page_ocr(img)

    text, error = ocr_image(processed, psm=6)
    if text:
        return text, error

    text, error = ocr_image(processed, psm=11)
    return text, error


def write_text_file(path: Path, text: str):
    path.write_text(text or "", encoding="utf-8")


def extract_ortsteil_from_ocr_text(text):
    if not text:
        return None

    lower = text.lower()

    if "florenberg" in lower:
        return "Florenberg"
    if "edelzell" in lower:
        return "Edelzell"

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
    return text.strip("_")


def prettify_pfarrei_slug(text: str) -> str:
    if not text:
        return "unbekannt"
    text = text.replace("-", "_")
    parts = [p for p in text.split("_") if p]
    return "_".join(part.capitalize() for part in parts)


def extract_book_meta_from_url(url: str) -> dict:
    """
    Beispiel:
    https://data.matricula-online.eu/de/deutschland/fulda/edelzell-engelhelms-christkoenig/1-01/?pg=1

    parts:
    ['de', 'deutschland', 'fulda', 'edelzell-engelhelms-christkoenig', '1-01']
    """
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]

    result = {
        "country": None,
        "bistum": None,
        "pfarre_ort": None,
        "signatur": None,
    }

    try:
        if len(parts) >= 5:
            result["country"] = parts[1]
            result["bistum"] = parts[2]
            result["pfarre_ort"] = prettify_pfarrei_slug(parts[3])
            result["signatur"] = parts[4]
    except Exception:
        pass

    return result


def detect_book_type_from_title_ocr(ocr_text: str) -> str:
    if not ocr_text:
        return "Kirchenbuch"

    lower = ocr_text.lower()

    has_taufe = "tauf" in lower or "bapt" in lower
    has_trauung = "trau" in lower or "heirat" in lower or "matrimon" in lower
    has_tod = "tod" in lower or "sterb" in lower or "mortu" in lower

    types_found = sum([has_taufe, has_trauung, has_tod])

    if types_found >= 2:
        return "Kirchenbuch"
    if has_taufe:
        return "Taufbuch"
    if has_trauung:
        return "Trauungsbuch"
    if has_tod:
        return "Totenbuch"

    return "Kirchenbuch"


def detect_year_range_from_ocr(ocr_text: str):
    if not ocr_text:
        return None, None

    years = sorted({int(y) for y in re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", ocr_text)})
    if not years:
        return None, None
    if len(years) == 1:
        return str(years[0]), str(years[0])
    return str(years[0]), str(years[-1])


def build_initial_meta(url: str) -> dict:
    url_meta = extract_book_meta_from_url(url)

    return {
        "country": url_meta.get("country") or "deutschland",
        "bistum": url_meta.get("bistum") or "unbekannt",
        "pfarre_ort": url_meta.get("pfarre_ort") or "unbekannt",
        "signatur": url_meta.get("signatur") or "unbekannt",
        "buchtyp": "Kirchenbuch",
        "datum_von": None,
        "datum_bis": None,
    }


def save_book_metadata(book_dir: Path, meta: dict, source_url: str):
    data = {
        "country": meta.get("country"),
        "bistum": meta.get("bistum"),
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
        print("[WARN] book.json fehlt für OCR-Anreicherung")
        return

    try:
        update_book_json_with_title_ocr(str(book_json_path), title_ocr_text)
        print("[INFO] book.json mit OCR-Metadaten angereichert")
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
        print(f"[INFO] page_{page_number}.json erzeugt")
    except Exception as e:
        print(f"[WARN] page.json konnte nicht erzeugt werden für Seite {page_number}: {e}")


def maybe_rename_book_dir(book_dir: Path, book_name: str, pdf_path: Path, meta: dict):
    if not should_auto_rename(book_name):
        return book_dir, book_name, pdf_path

    new_name_parts = [
        sanitize(meta.get("pfarre_ort") or "unbekannt"),
        sanitize(meta.get("signatur") or "unbekannt"),
        sanitize(meta.get("buchtyp") or "Kirchenbuch"),
    ]

    if meta.get("datum_von") or meta.get("datum_bis"):
        new_name_parts.append(f"{meta.get('datum_von') or 'xxxx'}_{meta.get('datum_bis') or 'xxxx'}")

    new_name = "_".join([part for part in new_name_parts if part])
    new_dir = BOOKS_DIR / new_name

    if new_dir == book_dir:
        return book_dir, book_name, pdf_path

    if new_dir.exists():
        print(f"[WARN] Zielordner existiert bereits, kein Rename: {new_dir}")
        return book_dir, book_name, pdf_path

    shutil.move(str(book_dir), str(new_dir))
    print(f"[INFO] Buchordner umbenannt: {book_dir.name} -> {new_name}")

    return new_dir, new_name, PDF_DIR / f"{new_name}.pdf"


def run_download_job(job_id, url, book_name, save_job_status):
    book_dir = BOOKS_DIR / book_name
    pdf_path = PDF_DIR / f"{book_name}.pdf"
    debug_job_dir = DEBUG_DIR / f"{book_name}_{job_id}"

    book_dir.mkdir(parents=True, exist_ok=True)
    debug_job_dir.mkdir(parents=True, exist_ok=True)

    meta = build_initial_meta(url)
    start_page = get_page_number_from_url(url)

    save_book_metadata(book_dir, meta, url)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 2200})

        page.goto(url)
        page.wait_for_timeout(5000)

        page_num = start_page
        saved_count = 0
        title_ocr_done = False

        for _ in range(5):
            current_page_url = make_page_url(url, page_num)

            print(f"[INFO] Lade Seite {page_num}: {current_page_url}")
            page.goto(current_page_url)
            page.wait_for_timeout(5000)
            time.sleep(short_pause())
            zoom_out(page)

            raw_path = debug_job_dir / f"raw_{page_num}.png"
            page.screenshot(path=str(raw_path), full_page=True)

            if not title_ocr_done and page_num <= start_page + 4:
                crop_path = debug_job_dir / f"title_page_{page_num}.png"
                crop_ok = save_top_title_crop(raw_path, crop_path)

                if crop_ok:
                    title_ocr_text, title_ocr_error = read_title_crop_ocr(crop_path)
                    write_text_file(debug_job_dir / f"title_page_{page_num}.ocr.txt", title_ocr_text or "")

                    if title_ocr_error:
                        print(f"[WARN] Titel-OCR Fehler auf Seite {page_num}: {title_ocr_error}")
                    else:
                        print(f"[INFO] Titel-OCR Seite {page_num}: {title_ocr_text}")

                    if title_ocr_text and len(title_ocr_text) >= 20:
                        ortsteil = extract_ortsteil_from_ocr_text(title_ocr_text)
                        if ortsteil and ortsteil.lower() not in (meta["pfarre_ort"] or "").lower():
                            meta["pfarre_ort"] = f"{meta['pfarre_ort']}_{ortsteil}"

                        detected_type = detect_book_type_from_title_ocr(title_ocr_text)
                        year_from, year_to = detect_year_range_from_ocr(title_ocr_text)

                        meta["buchtyp"] = detected_type
                        if year_from:
                            meta["datum_von"] = year_from
                        if year_to:
                            meta["datum_bis"] = year_to

                        book_dir, book_name, pdf_path = maybe_rename_book_dir(
                            book_dir=book_dir,
                            book_name=book_name,
                            pdf_path=pdf_path,
                            meta=meta,
                        )

                        save_book_metadata(book_dir, meta, url)
                        enrich_book_json_with_ocr(book_dir, title_ocr_text)
                        title_ocr_done = True

            file_path = book_dir / f"page_{page_num}.png"
            save_screenshot(page, file_path)

            page_ocr_text, page_ocr_error = read_page_ocr(file_path)
            write_text_file(book_dir / f"page_{page_num}.ocr.txt", page_ocr_text or "")

            if page_ocr_error:
                print(f"[WARN] Seiten-OCR Fehler auf Seite {page_num}: {page_ocr_error}")
            else:
                print(f"[INFO] Seiten-OCR Zeichen auf Seite {page_num}: {len(page_ocr_text or '')}")

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
                        "job_id": job_id,
                        "status": "running",
                        "saved_count": saved_count,
                        "current_page": page_num,
                        "book_name": book_name,
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    })
                except Exception as e:
                    print(f"[WARN] save_job_status fehlgeschlagen: {e}")

            page_num += 1
            time.sleep(human_pause())

        save_book_metadata(book_dir, meta, url)
        create_pdf(book_dir, pdf_path)

        if save_job_status:
            try:
                save_job_status(job_id, {
                    "job_id": job_id,
                    "status": "finished",
                    "saved_count": saved_count,
                    "book_name": book_name,
                    "pdf_path": str(pdf_path),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                })
            except Exception as e:
                print(f"[WARN] final save_job_status fehlgeschlagen: {e}")

        browser.close()
