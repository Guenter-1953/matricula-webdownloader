import re
import json
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any


@dataclass
class BookMetadata:
    title_original: str
    title_normalized: str
    primary_book_type: Optional[str]
    year_from: Optional[int]
    year_to: Optional[int]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_book_type(text: str) -> Optional[str]:
    lower = text.lower()

    if "tauf" in lower or "bapt" in lower:
        return "taufe"
    if "trau" in lower or "heirat" in lower:
        return "trauung"
    if "tod" in lower or "sterb" in lower:
        return "tod"

    return None


def detect_years(text: str):
    matches = re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", text)
    years = sorted({int(y) for y in matches})

    if not years:
        return None, None, 0.0

    if len(years) == 1:
        return years[0], years[0], 0.5

    return years[0], years[-1], 0.8


def parse_book_metadata_from_ocr(ocr_text: str) -> BookMetadata:
    normalized = normalize_text(ocr_text)

    book_type = detect_book_type(normalized)
    y_from, y_to, conf = detect_years(normalized)

    return BookMetadata(
        title_original=ocr_text,
        title_normalized=normalized,
        primary_book_type=book_type,
        year_from=y_from,
        year_to=y_to,
        confidence=conf,
    )


def enrich_existing_book_json(book_json: Dict[str, Any], ocr_text: str) -> Dict[str, Any]:
    parsed = parse_book_metadata_from_ocr(ocr_text)

    book_json["ocr_title"] = ocr_text
    book_json["parsed_metadata"] = parsed.to_dict()

    return book_json


def enrich_book_json_file(book_json_path: str, ocr_text: str) -> Dict[str, Any]:
    with open(book_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    enriched = enrich_existing_book_json(data, ocr_text)

    with open(book_json_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    return enriched
