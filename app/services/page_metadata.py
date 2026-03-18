import os
import re
import json
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Any


@dataclass
class PageMetadata:
    schema_version: int
    page_number: int
    image_file: str
    image_path: str
    source_url: Optional[str]
    ocr_text: str
    ocr_char_count: int
    likely_record_type: Optional[str]
    record_type_confidence: float
    years_found: List[int] = field(default_factory=list)
    earliest_year: Optional[int] = None
    latest_year: Optional[int] = None
    candidate_names: List[str] = field(default_factory=list)
    needs_ai_review: bool = True
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_ocr_text(text: str) -> str:
    text = text or ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def detect_record_type(text: str) -> (Optional[str], float):
    lower = text.lower()

    scores = {
        "taufe": 0,
        "trauung": 0,
        "tod": 0,
    }

    for pattern in [r"\btauf", r"\bbapt", r"\bgeburt"]:
        scores["taufe"] += len(re.findall(pattern, lower, flags=re.IGNORECASE))

    for pattern in [r"\btrau", r"\bheirat", r"\behe", r"\bmatrimon"]:
        scores["trauung"] += len(re.findall(pattern, lower, flags=re.IGNORECASE))

    for pattern in [r"\btod", r"\bsterb", r"\bbegr", r"\bmortu", r"\bdefunct"]:
        scores["tod"] += len(re.findall(pattern, lower, flags=re.IGNORECASE))

    best_type = None
    best_score = 0

    for key, value in scores.items():
        if value > best_score:
            best_type = key
            best_score = value

    total = sum(scores.values())
    confidence = round(best_score / total, 3) if total > 0 else 0.0

    return best_type, confidence


def extract_years(text: str) -> List[int]:
    years = sorted({int(y) for y in re.findall(r"\b(1[5-9]\d{2}|20\d{2})\b", text)})
    return years


def extract_candidate_names(text: str, limit: int = 30) -> List[str]:
    pattern = r"\b([A-ZÄÖÜ][a-zäöüß]{2,}(?:\s+[A-ZÄÖÜ][a-zäöüß]{2,}){1,3})\b"
    matches = re.findall(pattern, text)

    stopwords = {
        "Matricula Online",
        "Deutschland Fulda",
        "Startseite Deutschland",
        "Kirchenbuch Taufe",
        "Kirchenbuch Trauung",
        "Kirchenbuch Tod",
    }

    result = []
    seen = set()

    for match in matches:
        name = match.strip()
        if name in stopwords:
            continue
        if len(name) > 60:
            continue
        if name not in seen:
            seen.add(name)
            result.append(name)

    return result[:limit]


def build_page_metadata(
    page_number: int,
    image_file: str,
    image_path: str,
    ocr_text: str,
    source_url: Optional[str] = None,
) -> PageMetadata:
    normalized = normalize_ocr_text(ocr_text)
    record_type, record_confidence = detect_record_type(normalized)
    years = extract_years(normalized)
    candidate_names = extract_candidate_names(normalized)

    notes: List[str] = []

    if not normalized:
        notes.append("Kein OCR-Text vorhanden.")
    if not record_type:
        notes.append("Seitentyp konnte nicht erkannt werden.")
    if not years:
        notes.append("Keine Jahreszahl erkannt.")
    if not candidate_names:
        notes.append("Keine Namenskandidaten erkannt.")

    return PageMetadata(
        schema_version=1,
        page_number=page_number,
        image_file=image_file,
        image_path=image_path,
        source_url=source_url,
        ocr_text=normalized,
        ocr_char_count=len(normalized),
        likely_record_type=record_type,
        record_type_confidence=record_confidence,
        years_found=years,
        earliest_year=years[0] if years else None,
        latest_year=years[-1] if years else None,
        candidate_names=candidate_names,
        needs_ai_review=True,
        notes=notes,
    )


def page_json_filename_for_image(image_file: str) -> str:
    base, _ = os.path.splitext(image_file)
    return f"{base}.json"


def save_page_metadata_json(output_path: str, metadata: PageMetadata) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata.to_dict(), f, ensure_ascii=False, indent=2)


def build_and_save_page_metadata(
    page_number: int,
    image_file: str,
    image_path: str,
    ocr_text: str,
    output_json_path: str,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    metadata = build_page_metadata(
        page_number=page_number,
        image_file=image_file,
        image_path=image_path,
        ocr_text=ocr_text,
        source_url=source_url,
    )
    save_page_metadata_json(output_path=output_json_path, metadata=metadata)
    return metadata.to_dict()
