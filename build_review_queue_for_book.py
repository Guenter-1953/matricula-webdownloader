import json
import sys
from pathlib import Path

from review_queue import add_page


MIN_CONFIDENCE_REQUIRED = 55.0
MIN_TEXT_LENGTH_REQUIRED = 300


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_ocr_values(page_data: dict) -> tuple[float | None, int | None]:
    confidence = None
    text_length = None

    ocr = page_data.get("ocr", {})
    if isinstance(ocr, dict):
        raw_conf = ocr.get("confidence")
        raw_text = ocr.get("text")

        try:
            if raw_conf is not None:
                confidence = float(raw_conf)
        except Exception:
            confidence = None

        if isinstance(raw_text, str):
            text_length = len(raw_text.strip())

    if text_length is None:
        raw_text_top = page_data.get("ocr_text")
        if isinstance(raw_text_top, str):
            text_length = len(raw_text_top.strip())

    return confidence, text_length


def should_add_to_review(confidence: float | None, text_length: int | None) -> bool:
    if confidence is None:
        return True
    if confidence < MIN_CONFIDENCE_REQUIRED:
        return True
    if text_length is None:
        return True
    if text_length < MIN_TEXT_LENGTH_REQUIRED:
        return True
    return False


def find_page_json_files(book_dir: Path) -> list[Path]:
    files = []
    for path in sorted(book_dir.glob("page_*.json")):
        if path.is_file():
            files.append(path)
    return files


def build_review_queue_for_book(book_dir: Path) -> dict:
    page_files = find_page_json_files(book_dir)

    checked_count = 0
    added_count = 0
    already_present_count = 0
    skipped_count = 0
    results = []

    for page_file in page_files:
        checked_count += 1
        page_data = load_json(page_file)

        confidence, text_length = extract_ocr_values(page_data)

        image_path = page_data.get("image_path")
        if not image_path:
            image_name = page_data.get("image_file")
            if image_name:
                image_path = str(book_dir / image_name)

        if not image_path:
            skipped_count += 1
            results.append({
                "page_json": str(page_file),
                "status": "skipped_missing_image_path",
            })
            continue

        if not should_add_to_review(confidence, text_length):
            skipped_count += 1
            results.append({
                "page_json": str(page_file),
                "source_image": image_path,
                "status": "skipped_good_enough",
                "reason": {
                    "min_confidence_required": MIN_CONFIDENCE_REQUIRED,
                    "min_text_length_required": MIN_TEXT_LENGTH_REQUIRED,
                    "actual_confidence": confidence,
                    "actual_text_length": text_length,
                },
            })
            continue

        reason = {
            "min_confidence_required": MIN_CONFIDENCE_REQUIRED,
            "min_text_length_required": MIN_TEXT_LENGTH_REQUIRED,
            "actual_confidence": confidence,
            "actual_text_length": text_length,
        }

        queue_result = add_page(image_path=image_path, reason=reason)

        if queue_result["status"] == "added":
            added_count += 1
        else:
            already_present_count += 1

        results.append({
            "page_json": str(page_file),
            "source_image": image_path,
            "status": queue_result["status"],
            "reason": reason,
        })

    return {
        "book_dir": str(book_dir),
        "checked_pages": checked_count,
        "added_to_queue": added_count,
        "already_present": already_present_count,
        "skipped": skipped_count,
        "results": results,
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
