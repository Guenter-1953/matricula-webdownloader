from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


BOOKS_DIR = Path("/app/data/books")
PDF_DIR = Path("/app/data/pdf")

TECH_BOOK_PATTERN = re.compile(r"^book_[A-Za-z0-9]+$")


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def sanitize(text: str) -> str:
    text = text or ""
    text = text.replace("ß", "ss")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^\w\-]", "", text)
    return text.strip("_")


def sanitize_part(text: str, max_len: int) -> str:
    cleaned = sanitize(text)
    if not cleaned:
        return ""
    return cleaned[:max_len].strip("_")


def build_display_name(meta: dict) -> str | None:
    pfarre = sanitize_part(meta.get("pfarre") or "", 40)
    signatur = sanitize_part(meta.get("signatur") or "", 20)
    buchtyp = sanitize_part(meta.get("buchtyp") or "", 40)
    jahr_von = sanitize_part(meta.get("jahr_von") or "", 10)
    jahr_bis = sanitize_part(meta.get("jahr_bis") or "", 10)

    parts = [part for part in [pfarre, signatur, buchtyp] if part]

    if jahr_von or jahr_bis:
        parts.append(f"{jahr_von or 'xxxx'}_{jahr_bis or 'xxxx'}")

    if not parts:
        return None

    return "_".join(parts)


def normalized_source_url(meta: dict) -> str:
    return normalize_text(meta.get("normalized_source_url") or meta.get("source_url"))


def page_count(folder: Path) -> int:
    return len(list(folder.glob("page_*.png")))


def pdf_path_for(folder_name: str) -> Path:
    return PDF_DIR / f"{folder_name}.pdf"


def book_identity(meta: dict) -> tuple[str, str, str, str]:
    return (
        normalize_text(meta.get("pfarre")),
        normalize_text(meta.get("signatur")),
        normalize_text(meta.get("buchtyp")),
        normalized_source_url(meta),
    )


def find_named_target_for(meta: dict, current_folder: Path) -> Path | None:
    wanted_identity = book_identity(meta)

    for folder in sorted(BOOKS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        if folder == current_folder:
            continue
        if TECH_BOOK_PATTERN.fullmatch(folder.name):
            continue

        other_meta = load_json(folder / "book.json")
        if not other_meta:
            continue

        if book_identity(other_meta) == wanted_identity and wanted_identity != ("", "", "", ""):
            return folder

    return None


def remove_empty_technical_folder(folder: Path) -> bool:
    items = list(folder.iterdir())

    if not items:
        folder.rmdir()
        return True

    if len(items) == 1 and items[0].name == "book.json":
        items[0].unlink(missing_ok=True)
        folder.rmdir()
        return True

    return False


def move_pdf_if_present(old_name: str, new_name: str) -> str | None:
    old_pdf = pdf_path_for(old_name)
    new_pdf = pdf_path_for(new_name)

    if not old_pdf.exists():
        return None

    if new_pdf.exists():
        old_pdf.unlink(missing_ok=True)
        return f"altes PDF {old_pdf.name} entfernt, da {new_pdf.name} schon existiert"

    shutil.move(str(old_pdf), str(new_pdf))
    return f"PDF umbenannt: {old_pdf.name} -> {new_pdf.name}"


def rename_folder(folder: Path, target_name: str) -> list[str]:
    messages: list[str] = []

    if folder.name == target_name:
        messages.append("Ordnername bereits korrekt")
        return messages

    target = BOOKS_DIR / target_name
    if target.exists():
        messages.append(f"Zielordner existiert bereits: {target_name}")
        return messages

    old_name = folder.name
    shutil.move(str(folder), str(target))
    messages.append(f"Ordner umbenannt: {old_name} -> {target_name}")

    pdf_message = move_pdf_if_present(old_name, target_name)
    if pdf_message:
        messages.append(pdf_message)

    return messages


def cleanup_one_folder(folder: Path) -> list[str]:
    messages: list[str] = [f"Prüfe {folder.name}"]

    if not TECH_BOOK_PATTERN.fullmatch(folder.name):
        messages.append("übersprungen: kein technischer book_* Ordner")
        return messages

    if remove_empty_technical_folder(folder):
        messages.append("leerer technischer Ordner entfernt")
        return messages

    meta = load_json(folder / "book.json")
    if not meta:
        messages.append("übersprungen: kein lesbares book.json")
        return messages

    target_folder = find_named_target_for(meta, folder)
    if target_folder is not None:
        current_pages = page_count(folder)
        target_pages = page_count(target_folder)

        if current_pages == 0:
            shutil.rmtree(folder)
            messages.append(
                f"technischer Ordner entfernt, weil Zielordner schon existiert: "
                f"{target_folder.name} (Seiten dort: {target_pages})"
            )

            old_pdf = pdf_path_for(folder.name)
            if old_pdf.exists():
                old_pdf.unlink(missing_ok=True)
                messages.append(f"technisches PDF entfernt: {old_pdf.name}")

            return messages

        messages.append(
            f"nicht automatisch entfernt: enthält {current_pages} Seiten, "
            f"aber Zielordner {target_folder.name} existiert schon mit {target_pages} Seiten"
        )
        return messages

    display_name = build_display_name(meta)
    if not display_name:
        messages.append("übersprungen: aus Metadaten kein sinnvoller Zielname ableitbar")
        return messages

    messages.extend(rename_folder(folder, display_name))
    return messages


def main():
    if not BOOKS_DIR.exists():
        print("BOOKS_DIR nicht gefunden")
        return

    folders = sorted([folder for folder in BOOKS_DIR.iterdir() if folder.is_dir()])

    print("=== AUFRÄUMEN TECHNISCHER BOOK-ORDNER ===")
    print(f"Gefundene Ordner: {len(folders)}")
    print("")

    for folder in folders:
        for line in cleanup_one_folder(folder):
            print(line)
        print("---")


if __name__ == "__main__":
    main()
