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


DEBUG_PAGE_COUNT = 15
SMART_SKIP_LIMIT = 8

SERVICE_UNAVAILABLE_PATTERNS = [
    "service unavailable",
    "temporarily unable to service your request",
    "please try again later",
    "apache/2.4",
]


def log(msg: str):
    print(f"[DEBUG] {msg}")


def human_pause() -> float:
    return round(random.uniform(8.0, 18.0), 2)


def short_pause() -> float:
    return round(random.uniform(1.2, 3.8), 2)


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


def normalize_source_url(url: str) -> str:
    if not url:
        return ""

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.pop("pg", None)

    normalized_query = urlencode(sorted((key, value) for key, values in query.items() for value in values))
    normalized_path = parsed.path.rstrip("/")

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        normalized_path,
        parsed.params,
        normalized_query,
        ""
    ))


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


def normalize_compare_value(value) -> str:
    return normalize_whitespace(str(value or "")).lower()


def contains_service_unavailable_text(text: str) -> bool:
    lower = (text or "").lower()
    return any(pattern in lower for pattern in SERVICE_UNAVAILABLE_PATTERNS)


def page_shows_service_unavailable(page) -> bool:
    try:
        parts = []

        try:
            parts.append(page.title() or "")
        except Exception:
            pass

        try:
            parts.append(page.locator("body").inner_text(timeout=1000) or "")
        except Exception:
            pass

        try:
            parts.append(page.content() or "")
        except Exception:
            pass

        combined = "\n".join(parts)
        return contains_service_unavailable_text(combined)
    except Exception as e:
        log(f"page_shows_service_unavailable Fehler: {e}")
        return False


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
        "normalized_source_url": normalize_source_url(source_url),
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


def build_book_identity(meta: dict, source_url: str) -> dict:
    return {
        "normalized_source_url": normalize_source_url(source_url),
        "country": normalize_compare_value(meta.get("country")),
        "bistum": normalize_compare_value(meta.get("bistum")),
        "pfarre": normalize_compare_value(meta.get("pfarre_ort")),
        "signatur": normalize_compare_value(meta.get("signatur")),
    }


def load_book_json(book_dir: Path) -> dict | None:
    path = book_dir / "book.json"
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"book.json konnte nicht gelesen werden in {book_dir}: {e}")
        return None


def is_same_book_identity(existing_data: dict, wanted_identity: dict) -> bool:
    existing_normalized_url = normalize_compare_value(
        existing_data.get("normalized_source_url") or normalize_source_url(existing_data.get("source_url", ""))
    )
    wanted_normalized_url = normalize_compare_value(wanted_identity.get("normalized_source_url"))

    if existing_normalized_url and wanted_normalized_url and existing_normalized_url == wanted_normalized_url:
        return True

    existing_country = normalize_compare_value(existing_data.get("country"))
    existing_bistum = normalize_compare_value(existing_data.get("bistum"))
    existing_pfarre = normalize_compare_value(existing_data.get("pfarre"))
    existing_signatur = normalize_compare_value(existing_data.get("signatur"))

    return (
        existing_country == wanted_identity.get("country")
        and existing_bistum == wanted_identity.get("bistum")
        and existing_pfarre == wanted_identity.get("pfarre")
        and existing_signatur == wanted_identity.get("signatur")
        and bool(existing_signatur)
    )


def find_existing_book_dir(meta: dict, source_url: str, exclude_dir: Path | None = None) -> Path | None:
    wanted_identity = build_book_identity(meta, source_url)

    for candidate in sorted(BOOKS_DIR.glob("*")):
        if not candidate.is_dir():
            continue
        if exclude_dir is not None and candidate.resolve() == exclude_dir.resolve():
            continue

        existing_data = load_book_json(candidate)
        if not existing_data:
            continue

        if is_same_book_identity(existing_data, wanted_identity):
            log(f"Bestehender Buchordner erkannt: {candidate}")
            return candidate

    return None


def cleanup_empty_dir(path: Path):
    try:
        if path.exists() and path.is_dir() and not any(path.iterdir()):
            path.rmdir()
            log(f"Leerer Ordner entfernt: {path}")
    except Exception as e:
        log(f"Leerer Ordner konnte nicht entfernt werden {path}: {e}")


def maybe_attach_to_existing_book(book_dir: Path, book_name: str, pdf_path: Path, meta: dict, source_url: str):
    existing_dir = find_existing_book_dir(meta=meta, source_url=source_url, exclude_dir=book_dir)
    if existing_dir is None:
        return book_dir, book_name, pdf_path, False

    if existing_dir.resolve() == book_dir.resolve():
        return book_dir, book_name, pdf_path, False

    cleanup_empty_dir(book_dir)

    existing_name = existing_dir.name
    existing_pdf_path = PDF_DIR / f"{existing_name}.pdf"

    log(f"Neue Seiten werden an bestehenden Buchordner angehängt: {existing_name}")
    return existing_dir, existing_name, existing_pdf_path, True


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
            info.centerOk = !(centerX < viewportWidth * 0.20 || centerX > viewportWidth * 0.80);
            info.centerYOk = !(centerY < viewportHeight * 0.15 || centerY > viewportHeight * 0.90);
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


def center_viewer_canvas(page):
    script = """
    () => {
        try {
            const canvases = Array.from(document.querySelectorAll('canvas'));
            const bigCanvas = canvases
                .map(c => ({ el: c, rect: c.getBoundingClientRect() }))
                .filter(x => x.rect.width > 800 && x.rect.height > 800)
                .sort((a, b) => (b.rect.width * b.rect.height) - (a.rect.width * a.rect.height))[0];

            if (!bigCanvas) {
                return { ok: false, reason: 'no_big_canvas' };
            }

            const rect = bigCanvas.rect;

            return {
                ok: true,
                x: Math.max(50, rect.left + rect.width * 0.42),
                y: Math.max(50, rect.top + rect.height * 0.50),
                width: rect.width,
                height: rect.height
            };
        } catch (e) {
            return { ok: false, reason: String(e) };
        }
    }
    """

    try:
        result = page.evaluate(script)
        log(f"Viewer-Zentrierung Ergebnis: {result}")

        if not result.get("ok"):
            return

        page.mouse.click(result["x"], result["y"])
        page.wait_for_timeout(400)

        start_x = result["x"]
        start_y = result["y"]
        end_x = max(120, start_x - 120)

        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(end_x, start_y, steps=10)
        page.mouse.up()
        page.wait_for_timeout(600)

    except Exception as e:
        log(f"Viewer-Zentrierung fehlgeschlagen: {e}")


def save_viewer_screenshot(page, raw_path: Path, final_path: Path, debug_job_dir: Path, page_num: int):
    center_viewer_canvas(page)

    clip = detect_viewer_clip(page, debug_job_dir=debug_job_dir, page_num=page_num)

    if clip:
        try:
            page.screenshot(path=str(raw_path), clip=clip)
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
    local_page_number: int,
    source_page_number: int,
    image_path: Path,
    source_url: str,
    ocr_text: str,
):
    try:
        create_page_json_for_page(
            book_folder=str(book_dir),
            page_number=local_page_number,
            image_file=image_path.name,
            image_path=str(image_path),
            ocr_text=ocr_text or "",
            source_url=source_url,
        )

        page_json_path = book_dir / f"page_{local_page_number:04d}.json"
        if page_json_path.exists():
            data = json.loads(page_json_path.read_text(encoding="utf-8"))
            data["source_page_number"] = source_page_number
            page_json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        log(f"page_{local_page_number:04d}.json erzeugt (source_page_number={source_page_number})")
    except Exception as e:
        log(f"page.json konnte nicht erzeugt werden für lokale Seite {local_page_number}: {e}")


def update_status(
    save_job_status,
    job_id,
    book_name,
    status,
    message,
    saved_count=0,
    current_page=None,
    pdf_path=None,
    total_pages_target=None,
    start_page=None,
    end_page=None,
):
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
    if total_pages_target is not None:
        payload["total_pages_target"] = total_pages_target
    if start_page is not None:
        payload["start_page"] = start_page
    if end_page is not None:
        payload["end_page"] = end_page

    try:
        save_job_status(job_id, payload)
    except Exception as e:
        log(f"save_job_status fehlgeschlagen: {e}")


def detect_table_structure(gray_img) -> dict:
    inv = 255 - gray_img
    _, bw = cv2.threshold(inv, 140, 255, cv2.THRESH_BINARY)

    h, w = gray_img.shape[:2]
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 18)))
    hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 18), 1))

    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, vert_kernel)
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hor_kernel)

    vertical_ratio = float((vertical > 0).mean())
    horizontal_ratio = float((horizontal > 0).mean())

    col_density = (vertical > 0).mean(axis=0)
    row_density = (horizontal > 0).mean(axis=1)

    strong_vertical_bands = int((col_density > 0.08).sum())
    strong_horizontal_bands = int((row_density > 0.08).sum())

    return {
        "vertical_ratio": round(vertical_ratio, 5),
        "horizontal_ratio": round(horizontal_ratio, 5),
        "strong_vertical_bands": strong_vertical_bands,
        "strong_horizontal_bands": strong_horizontal_bands,
    }


def analyze_page_content_type(image_path: Path) -> dict:
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {
            "is_content": True,
            "reason": "Bild konnte nicht gelesen werden, nehme Inhaltsseite an.",
            "dark_ratio": None,
            "line_bands": None,
        }

    blur = cv2.GaussianBlur(img, (3, 3), 0)
    dark_mask = blur < 210
    dark_ratio = float(dark_mask.mean())

    row_density = dark_mask.mean(axis=1)
    line_bands = int((row_density > 0.03).sum())

    h = img.shape[0]
    upper = blur[:int(h * 0.30), :]
    middle = blur[int(h * 0.30):int(h * 0.70), :]
    lower = blur[int(h * 0.70):, :]

    upper_dark_ratio = float((upper < 210).mean()) if upper.size else 0.0
    middle_dark_ratio = float((middle < 210).mean()) if middle.size else 0.0
    lower_dark_ratio = float((lower < 210).mean()) if lower.size else 0.0

    table_info = detect_table_structure(blur)

    has_table = (
        table_info["vertical_ratio"] > 0.01 or
        table_info["horizontal_ratio"] > 0.01 or
        table_info["strong_vertical_bands"] >= 6 or
        table_info["strong_horizontal_bands"] >= 6
    )

    looks_like_title = (
        not has_table and (
            dark_ratio < 0.12 or
            middle_dark_ratio < 0.12 or
            lower_dark_ratio < 0.10
        )
    )

    is_content = has_table and not looks_like_title

    result = {
        "is_content": is_content,
        "reason": "Tabellarische Inhaltsseite erkannt" if is_content else "Titel-/Vorspannseite erkannt",
        "dark_ratio": round(dark_ratio, 5),
        "upper_dark_ratio": round(upper_dark_ratio, 5),
        "middle_dark_ratio": round(middle_dark_ratio, 5),
        "lower_dark_ratio": round(lower_dark_ratio, 5),
        "line_bands": line_bands,
        "has_table": has_table,
        "table_vertical_ratio": table_info["vertical_ratio"],
        "table_horizontal_ratio": table_info["horizontal_ratio"],
        "strong_vertical_bands": table_info["strong_vertical_bands"],
        "strong_horizontal_bands": table_info["strong_horizontal_bands"],
    }

    log(
        f"Bildanalyse {image_path.name}: "
        f"is_content={result['is_content']} "
        f"has_table={result['has_table']} "
        f"dark_ratio={result['dark_ratio']} "
        f"v_ratio={result['table_vertical_ratio']} "
        f"h_ratio={result['table_horizontal_ratio']} "
        f"v_bands={result['strong_vertical_bands']} "
        f"h_bands={result['strong_horizontal_bands']}"
    )
    return result


def find_first_content_page(page, base_url: str, start_page: int, debug_job_dir: Path, job_id: str, book_name: str, save_job_status):
    for probe_page in range(start_page, start_page + SMART_SKIP_LIMIT):
        current_page_url = make_page_url(base_url, probe_page)

        update_status(
            save_job_status=save_job_status,
            job_id=job_id,
            book_name=book_name,
            status="running",
            message=f"Prüfe Startseite {probe_page} ...",
            saved_count=0,
            current_page=probe_page,
        )

        log(f"Prüfe mögliche Startseite {probe_page}: {current_page_url}")
        page.goto(current_page_url)
        page.wait_for_timeout(3500)
        time.sleep(short_pause())

        if page_shows_service_unavailable(page):
            log(f"Service-Unavailable bei Startseitenprüfung {probe_page}, überspringe Probe")
            continue

        probe_raw = debug_job_dir / f"probe_raw_{probe_page}.png"
        probe_final = debug_job_dir / f"probe_page_{probe_page}.png"

        save_viewer_screenshot(
            page=page,
            raw_path=probe_raw,
            final_path=probe_final,
            debug_job_dir=debug_job_dir,
            page_num=probe_page,
        )

        analysis = analyze_page_content_type(probe_final)
        save_json(debug_job_dir / f"probe_page_{probe_page}.analysis.json", analysis)

        if analysis["is_content"]:
            log(f"Erste Inhaltsseite gefunden: {probe_page}")
            return probe_page

        log(f"Seite {probe_page} übersprungen: {analysis['reason']}")

    log(f"Keine eindeutige Inhaltsseite gefunden, verwende Startseite {start_page}")
    return start_page


def process_source_page(
    page,
    book_dir: Path,
    debug_job_dir: Path,
    local_page_num: int,
    source_page_num: int,
    current_page_url: str,
) -> tuple[bool, str]:
    final_page_path = book_dir / f"page_{local_page_num:04d}.png"
    final_json_path = book_dir / f"page_{local_page_num:04d}.json"

    if final_page_path.exists() and final_json_path.exists():
        log(f"Seite {local_page_num:04d} existiert bereits, überspringe erneutes Speichern")
        return True, "already_exists"

    page.goto(current_page_url)
    page.wait_for_timeout(3500)
    time.sleep(short_pause())

    if page_shows_service_unavailable(page):
        log(f"Service-Unavailable im HTML erkannt bei Quellseite {source_page_num}")
        return False, "service_unavailable_html"

    raw_page_path = debug_job_dir / f"raw_source_{source_page_num}.png"

    save_viewer_screenshot(
        page=page,
        raw_path=raw_page_path,
        final_path=final_page_path,
        debug_job_dir=debug_job_dir,
        page_num=source_page_num,
    )

    page_ocr_text, page_ocr_error = read_page_ocr_debug(raw_page_path)

    if contains_service_unavailable_text(page_ocr_text):
        log(f"Service-Unavailable im OCR erkannt bei Quellseite {source_page_num}")
        try:
            if final_page_path.exists():
                final_page_path.unlink()
        except Exception:
            pass
        return False, "service_unavailable_ocr"

    write_text_file(book_dir / f"page_{local_page_num:04d}.ocr.txt", page_ocr_text or "")
    write_text_file(debug_job_dir / f"page_{local_page_num:04d}.ocr.txt", page_ocr_text or "")

    if page_ocr_error:
        log(f"OCR-Debug Fehler Quellseite {source_page_num}: {page_ocr_error}")
    else:
        log(f"OCR-Debug Zeichen Quellseite {source_page_num}: {len(page_ocr_text or '')}")

    create_page_metadata(
        book_dir=book_dir,
        local_page_number=local_page_num,
        source_page_number=source_page_num,
        image_path=final_page_path,
        source_url=current_page_url,
        ocr_text=page_ocr_text,
    )

    return True, "ok"


def retry_failed_pages(
    page,
    failed_pages: list,
    book_dir: Path,
    debug_job_dir: Path,
    job_id: str,
    book_name: str,
    save_job_status,
    saved_count: int,
    total_pages_target: int,
    requested_start_page: int | None = None,
    requested_end_page: int | None = None,
) -> tuple[int, list]:
    remaining_failed = []

    for failed in failed_pages:
        source_page_num = failed["source_page_number"]
        local_page_num = source_page_num
        current_page_url = failed["source_url"]

        update_status(
            save_job_status=save_job_status,
            job_id=job_id,
            book_name=book_name,
            status="running",
            message=f"Nachladeversuch für Quellseite {source_page_num} ...",
            saved_count=saved_count,
            current_page=source_page_num,
            total_pages_target=total_pages_target,
            start_page=requested_start_page,
            end_page=requested_end_page,
        )

        success = False
        reason = "retry_not_started"

        for attempt in range(1, 4):
            log(
                f"Nachladeversuch {attempt}/3 für "
                f"Seite {local_page_num:04d} "
                f"(Quelle {source_page_num})"
            )

            success, reason = process_source_page(
                page=page,
                book_dir=book_dir,
                debug_job_dir=debug_job_dir,
                local_page_num=local_page_num,
                source_page_num=source_page_num,
                current_page_url=current_page_url,
            )

            if success:
                saved_count += 1
                update_status(
                    save_job_status=save_job_status,
                    job_id=job_id,
                    book_name=book_name,
                    status="running",
                    message=f"Nachgeladen: Seite {local_page_num:04d} (Quelle {source_page_num})",
                    saved_count=saved_count,
                    current_page=source_page_num,
                    total_pages_target=total_pages_target,
                    start_page=requested_start_page,
                    end_page=requested_end_page,
                )
                break

            log(f"Nachladeversuch fehlgeschlagen: {reason}")
            time.sleep(5 + attempt * 3)

        if not success:
            failed_copy = dict(failed)
            failed_copy["final_reason"] = reason
            remaining_failed.append(failed_copy)

        time.sleep(human_pause())

    return saved_count, remaining_failed


def determine_page_plan(
    url: str,
    requested_start_page: int | None = None,
    requested_end_page: int | None = None,
) -> dict:
    url_start_page = get_page_number_from_url(url)

    if requested_start_page is not None:
        effective_start_page = requested_start_page
    else:
        effective_start_page = url_start_page

    if requested_start_page is not None and requested_end_page is not None:
        if requested_end_page < requested_start_page:
            requested_start_page, requested_end_page = requested_end_page, requested_start_page
        total_pages_to_fetch = max(requested_end_page - requested_start_page + 1, 1)
    elif requested_start_page is not None and requested_end_page is None:
        total_pages_to_fetch = DEBUG_PAGE_COUNT
    elif requested_start_page is None and requested_end_page is not None:
        total_pages_to_fetch = max(requested_end_page, 1)
    else:
        total_pages_to_fetch = DEBUG_PAGE_COUNT

    return {
        "url_start_page": url_start_page,
        "requested_start_page": requested_start_page,
        "requested_end_page": requested_end_page,
        "effective_start_page": effective_start_page,
        "total_pages_to_fetch": total_pages_to_fetch,
    }


def run_download_job(
    job_id,
    url,
    book_name,
    save_job_status,
    start_page=None,
    end_page=None,
):
    book_dir = BOOKS_DIR / book_name
    pdf_path = PDF_DIR / f"{book_name}.pdf"
    debug_job_dir = DEBUG_DIR / f"{book_name}_{job_id}"

    book_dir.mkdir(parents=True, exist_ok=True)
    debug_job_dir.mkdir(parents=True, exist_ok=True)

    meta = build_initial_meta(url)
    page_plan = determine_page_plan(
        url=url,
        requested_start_page=start_page,
        requested_end_page=end_page,
    )

    url_start_page = page_plan["url_start_page"]
    requested_start_page = page_plan["requested_start_page"]
    requested_end_page = page_plan["requested_end_page"]
    effective_start_page = page_plan["effective_start_page"]
    total_pages_to_fetch = page_plan["total_pages_to_fetch"]

    log(
        f"Job gestartet: job_id={job_id} "
        f"book_name={book_name} "
        f"url_start_page={url_start_page} "
        f"requested_start_page={requested_start_page} "
        f"requested_end_page={requested_end_page} "
        f"effective_start_page={effective_start_page} "
        f"total_pages_to_fetch={total_pages_to_fetch}"
    )

    update_status(
        save_job_status=save_job_status,
        job_id=job_id,
        book_name=book_name,
        status="running",
        message="Initialisiere Download ...",
        saved_count=0,
        current_page=effective_start_page,
        total_pages_target=total_pages_to_fetch,
        start_page=requested_start_page,
        end_page=requested_end_page,
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
                current_page=effective_start_page,
                total_pages_target=total_pages_to_fetch,
                start_page=requested_start_page,
                end_page=requested_end_page,
            )

            meta_url = make_page_url(url, 1)
            log(f"Lade Metadaten immer von Seite 1: {meta_url}")
            page.goto(meta_url)
            page.wait_for_timeout(2500)

            dom_candidates = extract_dom_text_candidates(page)
            write_text_file(
                debug_job_dir / "dom_candidates.txt",
                json.dumps(dom_candidates, indent=2, ensure_ascii=False)
            )

            meta = enrich_meta_from_dom(meta, dom_candidates)

            book_dir, attached_book_name, attached_pdf_path, attached = maybe_attach_to_existing_book(
                book_dir=book_dir,
                book_name=book_name,
                pdf_path=pdf_path,
                meta=meta,
                source_url=url,
            )

            if attached:
                book_name = attached_book_name
                pdf_path = attached_pdf_path

                update_status(
                    save_job_status=save_job_status,
                    job_id=job_id,
                    book_name=book_name,
                    status="running",
                    message="Bestehender Buchordner erkannt, neue Seiten werden angehängt.",
                    saved_count=0,
                    current_page=effective_start_page,
                    total_pages_target=total_pages_to_fetch,
                    start_page=requested_start_page,
                    end_page=requested_end_page,
                )
            else:
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
                        current_page=effective_start_page,
                        total_pages_target=total_pages_to_fetch,
                        start_page=requested_start_page,
                        end_page=requested_end_page,
                    )
                else:
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
                            current_page=effective_start_page,
                            total_pages_target=total_pages_to_fetch,
                            start_page=requested_start_page,
                            end_page=requested_end_page,
                        )
                    else:
                        log(f"Jobname unverändert: {book_name}")

            save_book_metadata(book_dir, meta, url)

            if requested_start_page is not None:
                content_start_page = requested_start_page
                log(f"Expliziter Startseitenbereich gesetzt, verwende Startseite {content_start_page}")
            else:
                content_start_page = find_first_content_page(
                    page=page,
                    base_url=url,
                    start_page=effective_start_page,
                    debug_job_dir=debug_job_dir,
                    job_id=job_id,
                    book_name=book_name,
                    save_job_status=save_job_status,
                )

            log(f"Download beginnt ab Inhaltsseite {content_start_page}")

            saved_count = 0
            failed_pages = []

            for offset in range(total_pages_to_fetch):
                source_page_num = content_start_page + offset
                local_page_num = source_page_num

                if requested_end_page is not None and source_page_num > requested_end_page:
                    break

                current_page_url = make_page_url(url, source_page_num)

                final_page_path = book_dir / f"page_{local_page_num:04d}.png"
                final_json_path = book_dir / f"page_{local_page_num:04d}.json"

                if final_page_path.exists() and final_json_path.exists():
                    log(f"Seite {local_page_num:04d} existiert bereits → überspringe")
                    update_status(
                        save_job_status=save_job_status,
                        job_id=job_id,
                        book_name=book_name,
                        status="running",
                        message=f"Seite {local_page_num:04d} existiert bereits und wurde übersprungen.",
                        saved_count=saved_count,
                        current_page=source_page_num,
                        total_pages_target=total_pages_to_fetch,
                        start_page=requested_start_page,
                        end_page=requested_end_page,
                    )
                    continue

                update_status(
                    save_job_status=save_job_status,
                    job_id=job_id,
                    book_name=book_name,
                    status="running",
                    message=f"Lade Quellseite {source_page_num} ...",
                    saved_count=saved_count,
                    current_page=source_page_num,
                    total_pages_target=total_pages_to_fetch,
                    start_page=requested_start_page,
                    end_page=requested_end_page,
                )

                log(f"Lade Quellseite {source_page_num}: {current_page_url}")

                success, reason = process_source_page(
                    page=page,
                    book_dir=book_dir,
                    debug_job_dir=debug_job_dir,
                    local_page_num=local_page_num,
                    source_page_num=source_page_num,
                    current_page_url=current_page_url,
                )

                if success:
                    saved_count += 1
                    if reason == "already_exists":
                        message = f"Seite {local_page_num:04d} war bereits vorhanden."
                    else:
                        message = f"Seite {local_page_num:04d} gespeichert (Quelle {source_page_num})"

                    update_status(
                        save_job_status=save_job_status,
                        job_id=job_id,
                        book_name=book_name,
                        status="running",
                        message=message,
                        saved_count=saved_count,
                        current_page=source_page_num,
                        total_pages_target=total_pages_to_fetch,
                        start_page=requested_start_page,
                        end_page=requested_end_page,
                    )
                else:
                    failed_pages.append({
                        "local_page_number": local_page_num,
                        "source_page_number": source_page_num,
                        "source_url": current_page_url,
                        "initial_reason": reason,
                    })
                    update_status(
                        save_job_status=save_job_status,
                        job_id=job_id,
                        book_name=book_name,
                        status="running",
                        message=f"Quellseite {source_page_num} fehlgeschlagen, wird später erneut versucht.",
                        saved_count=saved_count,
                        current_page=source_page_num,
                        total_pages_target=total_pages_to_fetch,
                        start_page=requested_start_page,
                        end_page=requested_end_page,
                    )

                time.sleep(human_pause())

            remaining_failed = []

            if failed_pages:
                save_json(debug_job_dir / "failed_pages_initial.json", failed_pages)

                update_status(
                    save_job_status=save_job_status,
                    job_id=job_id,
                    book_name=book_name,
                    status="running",
                    message=f"Starte Nachladeversuche für {len(failed_pages)} Fehlerseiten ...",
                    saved_count=saved_count,
                    current_page=failed_pages[0]["source_page_number"],
                    total_pages_target=total_pages_to_fetch,
                    start_page=requested_start_page,
                    end_page=requested_end_page,
                )

                saved_count, remaining_failed = retry_failed_pages(
                    page=page,
                    failed_pages=failed_pages,
                    book_dir=book_dir,
                    debug_job_dir=debug_job_dir,
                    job_id=job_id,
                    book_name=book_name,
                    save_job_status=save_job_status,
                    saved_count=saved_count,
                    total_pages_target=total_pages_to_fetch,
                    requested_start_page=requested_start_page,
                    requested_end_page=requested_end_page,
                )

                save_json(
                    debug_job_dir / "failed_pages_retry_result.json",
                    {
                        "initial_failed_count": len(failed_pages),
                        "remaining_failed_count": len(remaining_failed),
                        "remaining_failed_pages": remaining_failed,
                    },
                )

            last_processed_source_page = content_start_page + max(total_pages_to_fetch - 1, 0)

            update_status(
                save_job_status=save_job_status,
                job_id=job_id,
                book_name=book_name,
                status="running",
                message="Erzeuge PDF ...",
                saved_count=saved_count,
                current_page=last_processed_source_page,
                total_pages_target=total_pages_to_fetch,
                start_page=requested_start_page,
                end_page=requested_end_page,
            )

            save_book_metadata(book_dir, meta, url)
            create_pdf(book_dir, pdf_path)

            finish_message = "Download abgeschlossen."
            if attached:
                finish_message = "Download abgeschlossen, Seiten wurden an bestehendes Buch angehängt."
            if remaining_failed:
                finish_message = (
                    f"Download abgeschlossen, aber {len(remaining_failed)} Seiten "
                    f"konnten nicht nachgeladen werden."
                )

            update_status(
                save_job_status=save_job_status,
                job_id=job_id,
                book_name=book_name,
                status="finished",
                message=finish_message,
                saved_count=saved_count,
                current_page=last_processed_source_page,
                pdf_path=pdf_path,
                total_pages_target=total_pages_to_fetch,
                start_page=requested_start_page,
                end_page=requested_end_page,
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
            current_page=effective_start_page,
            total_pages_target=total_pages_to_fetch,
            start_page=requested_start_page,
            end_page=requested_end_page,
        )
        log(f"Job mit Fehler beendet: {e}")
        raise
