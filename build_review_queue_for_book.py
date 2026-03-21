import json
import sys
from pathlib import Path

from review_queue import add_page


MIN_TEXT_LENGTH_REQUIRED = 300


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def should_add_to_review(page_data: dict) -> tuple[bool, dict]:
    needs_ai = page_data.get("needs_ai_review", False)
    text_length = page_data.get("ocr_char_count")

    reason = {
        "needs_ai_review": needs_ai,
        "ocr_char_count": text_length,
        "min_text_length_required": MIN_TEXT_LENGTH_REQUIRED,
    }

    if needs_ai:
        return True, reason

    if text_length is None:
        return True, reason

    if text_length < MIN_TEXT_LENGTH_REQUIRED:
        return True, reason

    return False, reason


def find_page_json_files(book_dir: Path) -> list[Path]:
    return sorted(book_dir.glob("page_*.json"))


def build_review_queue_for_book(book_dir: Path) -> dict:
    page_files = find_page_json_files(book_dir)

    checked_count = 0
    added_count = 0
    already_present_count = 0
    skipped_count = 0

    for page_file in page_files:
        checked_count += 1
        page_data = load_json(page_file)

        image_path = page_data.get("image_path")
        if not image_path:
            image_name = page_data.get("image_file")
            if image_name:
                image_path = str(book_dir / image_name)

        if not image_path:
            skipped_count += 1
            continue

        should_add, reason = should_add_to_review(page_data)

        if not should_add:
            skipped_count += 1
            continue

        result = add_page(image_path=image_path, reason=reason)

        if result["status"] == "added":
            added_count += 1
        else:
            already_present_count += 1

    return {
        "book_dir": str(book_dir),
        "checked_pages": checked_count,
        "added_to_queue": added_count,
        "already_present": already_present_count,
        "skipped": skipped_count,
    }


def main():
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python build_review_queue_for_book.py /app/data/books/BUCHNAME")
        sys.exit(1)

    book_dir = Path(sys.argv[1])

    if not book_dir.is_dir():
        print(f"Buchordner nicht gefunden: {book_dir}")
        sys.exit(1)

    result = build_review_queue_for_book(book_dir)

    print("=== REVIEW-QUEUE FÜR BUCH ===")
    print("Buch:")
    print(result["book_dir"])
    print("Geprüfte Seiten:")
    print(result["checked_pages"])
    print("Zur Queue hinzugefügt:")
    print(result["added_to_queue"])
    print("Bereits vorhanden:")
    print(result["already_present"])
    print("Übersprungen:")
    print(result["skipped"])


if __name__ == "__main__":
    main()
