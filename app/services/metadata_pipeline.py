import json
import os
from typing import Any, Dict, Optional

from services.book_metadata import enrich_existing_book_json
from services.page_metadata import build_and_save_page_metadata, page_json_filename_for_image


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_book_json_with_title_ocr(book_json_path: str, title_ocr_text: str) -> Dict[str, Any]:
    data = load_json(book_json_path)
    enriched = enrich_existing_book_json(data, title_ocr_text)
    save_json(book_json_path, enriched)
    return enriched


def create_page_json_for_page(
    book_folder: str,
    page_number: int,
    image_file: str,
    image_path: str,
    ocr_text: str,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    page_json_name = page_json_filename_for_image(image_file)
    page_json_path = os.path.join(book_folder, page_json_name)

    cleaned_ocr_text = ""
    if ocr_text:
        cleaned_ocr_text = " ".join(line.strip() for line in ocr_text.splitlines() if line.strip())

    return build_and_save_page_metadata(
        page_number=page_number,
        source_image=image_path,
        image_file=image_file,
        image_path=image_path,
        ocr_text=ocr_text,
        cleaned_ocr_text=cleaned_ocr_text,
        output_path=page_json_path,
        source_url=source_url,
        status="ok",
    )
