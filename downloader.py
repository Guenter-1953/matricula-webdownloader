from playwright.sync_api import sync_playwright
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import img2pdf
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

from services.metadata_pipeline import create_page_json_for_page


DATA_DIR = Path("/app/data")
BOOKS_DIR = DATA_DIR / "books"
PDF_DIR = DATA_DIR / "pdf"
DEBUG_DIR = DATA_DIR / "debug"

BOOKS_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


DEBUG_PAGE_COUNT = 3
RIGHT_CROP_PX = 300


def log(msg: str):
    print(f"[DEBUG] {msg}")


def human_pause() -> float:
    return round(random.uniform(1.0, 2.0), 2)


def short_pause() -> float:
    return round(random.uniform(0.4, 0.9), 2)


def write_text_file(path: Path, text: str):
    path.write_text(text or "", encoding="utf-8")


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def create_pdf(book_dir: Path, pdf_path: Path):
    images = sorted(book_dir.glob("page_*.png"))
    if not images:
        log(f"Keine Bilder für PDF in {book_dir}")
        return

    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert([str(p) for p in images]))

    log(f"PDF erzeugt: {pdf_path}")


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


def sanitize(text: str) -> str:
    text = text or ""
    text = text.replace("ß", "ss")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\-]", "", text)
    return text.strip("_")


def prettify_slug(text: str) -> str:
    if not text:
        return "unbekannt"
    text = text.replace("-", "_")
    parts = [p for p in text.split("_") if p]
    return "_".join(part.capitalize() for part in parts)


def extract_book_meta_from_url(url: str) -> dict:
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
            result["pfarre_ort"] = prettify_slug(parts[3])
            result["signatur"] = parts[4]
    except Exception as e:
        log(f"extract_book_meta_from_url Fehler: {e}")

    log(f"URL-Metadaten erkannt: {result}")
    return result


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def detect_book_type_from_text(text: str) -> str:
    lower = (text or "").lower()

    has_taufe = "tauf" in lower or "bapt" in lower
    has_trauung = "trau" in lower or "heirat" in lower or "matrimon" in lower
    has_tod = "tod" in lower or "sterb" in lower or "mortu" in lower

    count = sum([has_taufe, has_trauung, has_tod])

    if count >= 2:
        return "Kirchenbuch"
    if has_taufe:
        return "Taufbuch"
    if has_trauung:
        return "Trauungsbuch"
    if has_tod:
        return "Totenbuch"

    return "Kirchenbuch"


def detect_year_range_from_text(text: str):
    years = sorted({int(y) for y in re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", text or "")})
    if not years:
        return None, None
    if len(years) == 1:
        return str(years[0]), str(years[0])
    return str(years[0]), str(years[-1])


def extract_dom_text_candidates(page) -> dict:
    candidates = {
        "title": "",
        "body_text": "",
        "h1": "",
        "h2": "",
        "page_title": "",
    }

    try:
        candidates["page_title"] = normalize_whitespace(page.title())
    except Exception:
        pass

    selectors = [
        "body",
        "h1",
        "h2",
        ".content",
        ".page-title",
        ".title",
        "main",
    ]

    for selector in selectors:
        try:
            elements = page.locator(selector)
            count = min(elements.count(), 3)
            texts = []
            for i in range(count):
                txt = normalize_whitespace(elements.nth(i).inner_text(timeout=700))
                if txt:
                    texts.append(txt)
            joined = " | ".join(texts)

            if selector == "body" and joined:
                candidates["body_text"] = joined
            elif selector == "h1" and joined:
                candidates["h1"] = joined
            elif selector == "h2" and joined:
                candidates["h2"] = joined
        except Exception:
            pass

    combined = " | ".join(
        value for value in [
            candidates["page_title"],
            candidates["h1"],
            candidates["h2"],
            candidates["body_text"][:3000] if candidates["body_text"] else "",
        ]
        if value
    )
    candidates["title"] = normalize_whitespace(combined)

    log(f"DOM page_title: {candidates['page_title'][:150]}")
    log(f"DOM body_text Anfang: {candidates['body_text'][:200]}")
    return candidates


def build_initial_meta(url: str) -> dict:
    url_meta = extract_book_meta_from_url(url)

    meta = {
        "country": url_meta.get("country") or "deutschland",
        "bistum": url_meta.get("bistum") or "unbekannt",
        "pfarre_ort": url_meta.get("pfarre_ort") or "unbekannt",
        "signatur": url_meta.get("signatur") or "unbekannt",
        "buchtyp": "Kirchenbuch",
        "datum_von": None,
        "datum_bis": None,
        "dom_title_text": "",
    }
    log(f"Initiale Metadaten: {meta}")
    return meta


def enrich_meta_from_dom(meta: dict, dom_candidates: dict) -> dict:
    text = normalize_whitespace(
        " | ".join([
            dom_candidates.get("page_title", ""),
            dom_candidates.get("h1", ""),
            dom_candidates.get("h2", ""),
            dom_candidates.get("body_text", "")[:4000],
        ])
    )

    if text:
        meta["dom_title_text"] = text

    detected_type = detect_book_type_from_text(text)
    year_from, year_to = detect_year_range_from_text(text)

    if detected_type:
        meta["buchtyp"] = detected_type
    if year_from:
        meta["datum_von"] = year_from
    if year_to:
        meta["datum_bis"] = year_to

    log(f"Metadaten nach DOM-Anreicherung: {meta}")
    return meta


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
        "dom_title_text": meta.get("dom_title_text", ""),
    }

    save_json(book_dir / "book.json", data)
    log(f"book.json gespeichert in {book_dir}")


def make_unique_target_dir(base_name: str) -> Path:
    base_dir = BOOKS_DIR / base_name
    if not base_dir.exists():
        return base_dir

    counter = 2
    while True:
        candidate = BOOKS_DIR / f"{base_name}_dup{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def maybe_rename_book_dir(book_dir: Path, book_name: str, pdf_path: Path, meta: dict):
    log(f"Rename-Prüfung: aktueller book_name={book_name}")

    new_name_parts = [
        sanitize(meta.get("pfarre_ort") or "unbekannt"),
        sanitize(meta.get("signatur") or "unbekannt"),
        sanitize(meta.get("buchtyp") or "Kirchenbuch"),
    ]

    if meta.get("datum_von") or meta.get("datum_bis"):
        new_name_parts.append(f"{meta.get('datum_von') or 'xxxx'}_{meta.get('datum_bis') or 'xxxx'}")

    display_name = "_".join([part for part in new_name_parts if part])

    if not display_name or "None" in display_name:
        log("Neuer Name ungültig, daher kein Rename")
        return book_dir, book_name, pdf_path, False, book_name

    if not should_auto_rename(book_name):
        log("Kein Auto-Rename, da Buchname kein technischer Platzhalter ist")
        return book_dir, book_name, pdf_path, False, book_name

    target_dir = make_unique_target_dir(display_name)
    final_fs_name = target_dir.name

    if target_dir == book_dir:
        log("Rename nicht nötig, Zielordner entspricht aktuellem Ordner")
        return book_dir, book_name, pdf_path, False, display_name

    shutil.move(str(book_dir), str(target_dir))
    log(f"Buchordner umbenannt: {book_dir.name} -> {final_fs_name}")

    return target_dir, final_fs_name, PDF_DIR / f"{final_fs_name}.pdf", True, display_name


def read_page_ocr_debug(path: Path):
    if pytesseract is None:
        return "", "pytesseract_missing"

    img = cv2.imread(str(path))
    if img is None:
        return "", "image_error"

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    try:
        text = pytesseract.image_to_string(gray, lang="deu", config="--oem 3 --psm 11")
        text = normalize_whitespace(text)
        return text, None
    except Exception as e:
        return "", str(e)


def detect_viewer_clip(page, debug_job_dir: Path = None, page_num: int = None):
    script = """
    () => {
        const all = Array.from(document.querySelectorAll('img, canvas, svg'));
        const candidates = [];

        for (const el of all) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);

            if (!rect) continue;

            const info = {
                tag: el.tagName.toLowerCase(),
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height,
                area: rect.width * rect.height,
                className: el.className ? String(el.className) : '',
                id: el.id ? String(el.id) : '',
                display: style.display,
                visibility: style.visibility,
                opacity: Number(style.opacity || '1')
            };

            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;

            info.centerX = centerX;
            info.centerY = centerY;
            info.minSizeOk = rect.width >= 800 && rect.height >= 800;
            info.centerOk = !(centerX < viewportWidth * 0.25 || centerX > viewportWidth * 0.75);
            info.centerYOk = !(centerY < viewportHeight * 0.20 || centerY > viewportHeight * 0.90);
            info.visibleOk = !(rect.right <= 0 || rect.bottom <= 0 || rect.left >= viewportWidth || rect.top >= viewportHeight);
            info.styleOk = !(style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') === 0);

            candidates.push(info);
        }

        const filtered = candidates.filter(c =>
            c.minSizeOk && c.centerOk && c.centerYOk && c.visibleOk && c.styleOk
        );

        filtered.sort((a, b) => b.area - a.area);

        return {
            all: candidates,
            filtered: filtered,
            best: filtered.length ? filtered[0] : null
        };
    }
    """

    try:
        result = page.evaluate(script)

        if debug_job_dir and page_num is not None:
            save_json(debug_job_dir / f"viewer_candidates_page_{page_num}.json", result)

        all_count = len(result.get("all", []))
        filtered_count = len(result.get("filtered", []))
        best = result.get("best")

        log(f"Viewer-Kandidaten gesamt: {all_count}, gefiltert: {filtered_count}")

        if not best:
            log("Kein Viewer-Kandidat nach Filterung gefunden")
            return None

        clip = {
            "x": max(0, best["left"]),
            "y": max(0, best["top"]),
            "width": best["width"],
            "height": best["height"],
        }

        log(
            "Viewer-Kandidat gewählt: "
            f"tag={best.get('tag')} "
            f"id={best.get('id')} "
            f"class={best.get('className')} "
            f"x={clip['x']} y={clip['y']} w={clip['width']} h={clip['height']}"
        )
        return clip

    except Exception as e:
        log(f"detect_viewer_clip Fehler: {e}")
        return None


def apply_right_crop_to_clip(clip: dict) -> dict:
    if not clip:
        return clip

    cropped_width = max(300, clip["width"] - RIGHT_CROP_PX)

    new_clip = {
        "x": clip["x"],
        "y": clip["y"],
        "width": cropped_width,
        "height": clip["height"],
    }

    log(
        "Rechtsbeschnitt angewendet: "
        f"alt_w={clip['width']} neu_w={new_clip['width']} crop_px={RIGHT_CROP_PX}"
    )
    return new_clip


def save_viewer_screenshot(page, raw_path: Path, final_path: Path, debug_job_dir: Path, page_num: int):
    clip = detect_viewer_clip(page, debug_job_dir=debug_job_dir, page_num=page_num)

    if clip:
        try:
            cropped_clip = apply_right_crop_to_clip(clip)
            page.screenshot(path=str(raw_path), clip=cropped_clip)
            shutil.copy(str(raw_path), str(final_path))
            log(f"Viewer-Clip-Screenshot gespeichert für Seite {page_num}: {raw_path.name}")
            return
        except Exception as e:
            log(f"Viewer-Clip-Screenshot fehlgeschlagen, Fallback full page: {e}")

    page.screenshot(path=str(raw_path), full_page=True)
    shutil.copy(str(raw_path), str(final_path))
    log(f"Full-Page-Fallback-Screenshot gespeichert für Seite {page_num}: {raw_path.name}")


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
        log(f"page_{page_number}.json erzeugt")
    except Exception as e:
        log(f"page.json konnte nicht erzeugt werden für Seite {page_number}: {e}")


def update_status(save_job_status, job_id, book_name, status, message, saved_count=0, current_page=None, pdf_path=None):
    log(
        f"Statusupdate: job_id={job_id} "
        f"book_name={book_name} status={status} "
        f"saved_count={saved_count} current_page={current_page} message={message}"
    )

    if not save_job_status:
        return

    payload = {
        "job_id": job_id,
        "book_name": book_name,
        "status": status,
        "message": message,
        "saved_count": saved_count,
        "pages": saved_count,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    if current_page is not None:
        payload["current_page"] = current_page
    if pdf_path is not None:
        payload["pdf_path"] = str(pdf_path)

    try:
        save_job_status(job_id, payload)
    except Exception as e:
        log(f"save_job_status fehlgeschlagen: {e}")


def run_download_job(job_id, url, book_name, save_job_status):
    book_dir = BOOKS_DIR / book_name
    pdf_path = PDF_DIR / f"{book_name}.pdf"
    debug_job_dir = DEBUG_DIR / f"{book_name}_{job_id}"

    book_dir.mkdir(parents=True, exist_ok=True)
    debug_job_dir.mkdir(parents=True, exist_ok=True)

    meta = build_initial_meta(url)
    start_page = get_page_number_from_url(url)

    log(f"Job gestartet: job_id={job_id} book_name={book_name} start_page={start_page}")

    update_status(
        save_job_status=save_job_status,
        job_id=job_id,
        book_name=book_name,
        status="running",
        message="Initialisiere Download ...",
        saved_count=0,
        current_page=start_page,
    )

    save_book_metadata(book_dir, meta, url)

    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page(viewport={"width": 2200, "height": 1600})

            update_status(
                save_job_status=save_job_status,
                job_id=job_id,
                book_name=book_name,
                status="running",
                message="Lese Buch-Metadaten ...",
                saved_count=0,
                current_page=start_page,
            )

            page.goto(url)
            page.wait_for_timeout(2000)

            dom_candidates = extract_dom_text_candidates(page)
            write_text_file(
                debug_job_dir / "dom_candidates.txt",
                json.dumps(dom_candidates, indent=2, ensure_ascii=False)
            )

            meta = enrich_meta_from_dom(meta, dom_candidates)

            old_book_name = book_name
            book_dir, fs_book_name, pdf_path, renamed, display_name = maybe_rename_book_dir(
                book_dir=book_dir,
                book_name=book_name,
                pdf_path=pdf_path,
                meta=meta,
            )

            if renamed:
                log(f"Dateisystem-Name geändert: {old_book_name} -> {fs_book_name}")
                log(f"Anzeigename für Job: {display_name}")
                book_name = display_name
                update_status(
                    save_job_status=save_job_status,
                    job_id=job_id,
                    book_name=book_name,
                    status="running",
                    message="Buchname wurde automatisch ermittelt.",
                    saved_count=0,
                    current_page=start_page,
                )
            else:
                # Auch ohne Rename soll der schöne Name im Job stehen
                if display_name and display_name != old_book_name:
                    log(f"Kein Rename nötig/möglich, aber Anzeigename wird gesetzt: {display_name}")
                    book_name = display_name
                    update_status(
                        save_job_status=save_job_status,
                        job_id=job_id,
                        book_name=book_name,
                        status="running",
                        message="Buchname wurde automatisch ermittelt.",
                        saved_count=0,
                        current_page=start_page,
                    )
                else:
                    log(f"Jobname unverändert: {book_name}")

            save_book_metadata(book_dir, meta, url)

            page_num = start_page
            saved_count = 0

            for _ in range(DEBUG_PAGE_COUNT):
                current_page_url = make_page_url(url, page_num)

                update_status(
                    save_job_status=save_job_status,
                    job_id=job_id,
                    book_name=book_name,
                    status="running",
                    message=f"Lade Seite {page_num} ...",
                    saved_count=saved_count,
                    current_page=page_num,
                )

                log(f"Lade Seite {page_num}: {current_page_url}")
                page.goto(current_page_url)
                page.wait_for_timeout(3500)
                time.sleep(short_pause())

                raw_page_path = debug_job_dir / f"raw_{page_num}.png"
                final_page_path = book_dir / f"page_{page_num}.png"

                save_viewer_screenshot(
                    page=page,
                    raw_path=raw_page_path,
                    final_path=final_page_path,
                    debug_job_dir=debug_job_dir,
                    page_num=page_num,
                )

                page_ocr_text, page_ocr_error = read_page_ocr_debug(raw_page_path)
                write_text_file(book_dir / f"page_{page_num}.ocr.txt", page_ocr_text or "")
                write_text_file(debug_job_dir / f"page_{page_num}.ocr.txt", page_ocr_text or "")

                if page_ocr_error:
                    log(f"OCR-Debug Fehler Seite {page_num}: {page_ocr_error}")
                else:
                    log(f"OCR-Debug Zeichen Seite {page_num}: {len(page_ocr_text or '')}")

                create_page_metadata(
                    book_dir=book_dir,
                    page_number=page_num,
                    image_path=final_page_path,
                    source_url=current_page_url,
                    ocr_text=page_ocr_text,
                )

                saved_count += 1

                update_status(
                    save_job_status=save_job_status,
                    job_id=job_id,
                    book_name=book_name,
                    status="running",
                    message=f"Seite {page_num} gespeichert",
                    saved_count=saved_count,
                    current_page=page_num,
                )

                page_num += 1
                time.sleep(human_pause())

            update_status(
                save_job_status=save_job_status,
                job_id=job_id,
                book_name=book_name,
                status="running",
                message="Erzeuge PDF ...",
                saved_count=saved_count,
                current_page=page_num - 1,
            )

            save_book_metadata(book_dir, meta, url)
            create_pdf(book_dir, pdf_path)

            update_status(
                save_job_status=save_job_status,
                job_id=job_id,
                book_name=book_name,
                status="finished",
                message="Download abgeschlossen.",
                saved_count=saved_count,
                current_page=page_num - 1,
                pdf_path=pdf_path,
            )

            browser.close()
            log(f"Job erfolgreich beendet: job_id={job_id} book_name={book_name}")

    except Exception as e:
        update_status(
            save_job_status=save_job_status,
            job_id=job_id,
            book_name=book_name,
            status="error",
            message=f"Fehler: {e}",
            saved_count=0,
            current_page=start_page,
        )
        log(f"Job mit Fehler beendet: {e}")
        raise
