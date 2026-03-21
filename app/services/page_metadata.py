from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


MIN_OCR_CHAR_COUNT = 300


SERVICE_UNAVAILABLE_PATTERNS = [
    "service unavailable",
    "temporarily unable to service your request",
    "please try again later",
    "apache/2.4",
]

TITLE_PAGE_PATTERNS = [
    "matricula online",
    "bestände",
    "landkarte",
    "ortssuche",
    "matricula unterstützen",
    "startseite",
    "kirchenbuch",
]

REGISTER_HINT_PATTERNS = [
    "getauft",
    "taufe",
    "taufen",
    "copuliert",
    "copulation",
    "getraut",
    "trauung",
    "begraben",
    "beerdigt",
    "gestorben",
    "verstorben",
    "index",
    "register",
    "alphabetisch",
]


class ConfidenceLevel(str, Enum):
    SICHER = "sicher"
    WAHRSCHEINLICH = "wahrscheinlich"
    UNSICHER = "unsicher"
    OFFEN = "offen"


class PageKind(str, Enum):
    TITLE_PAGE = "title_page"
    BAPTISM = "baptism"
    MARRIAGE = "marriage"
    BURIAL = "burial"
    INDEX = "index"
    REGISTER = "register"
    MIXED = "mixed"
    UNKNOWN = "unknown"
    OTHER = "other"


@dataclass(slots=True)
class ReviewQuestion:
    """
    Einzelne Unsicherheit oder offene Frage zur Seite.
    """

    field: str
    confidence: ConfidenceLevel
    reason: str
    question: str
    excerpt: Optional[str] = None
    current_reading: Optional[str] = None
    alternatives: list[str] = field(default_factory=list)

    def normalized(self) -> "ReviewQuestion":
        return ReviewQuestion(
            field=_clean_inline_text(self.field) or "",
            confidence=self.confidence,
            reason=_clean_inline_text(self.reason) or "",
            question=_clean_inline_text(self.question) or "",
            excerpt=_clean_multiline_text(self.excerpt),
            current_reading=_clean_inline_text(self.current_reading),
            alternatives=[
                cleaned
                for cleaned in (_clean_inline_text(item) for item in self.alternatives)
                if cleaned
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        item = self.normalized()
        return {
            "field": item.field,
            "confidence": item.confidence.value,
            "reason": item.reason,
            "question": item.question,
            "excerpt": item.excerpt,
            "current_reading": item.current_reading,
            "alternatives": item.alternatives,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewQuestion":
        return cls(
            field=str(data.get("field", "") or ""),
            confidence=parse_confidence(data.get("confidence")),
            reason=str(data.get("reason", "") or ""),
            question=str(data.get("question", "") or ""),
            excerpt=_none_if_blank(data.get("excerpt")),
            current_reading=_none_if_blank(data.get("current_reading")),
            alternatives=[
                str(item).strip()
                for item in (data.get("alternatives", []) or [])
                if str(item).strip()
            ],
        ).normalized()


@dataclass(slots=True)
class PageAnalysis:
    """
    Neue strukturierte Seitenanalyse.
    """

    raw_text: str = ""
    analysis_text: str = ""
    page_kind: PageKind = PageKind.UNKNOWN
    page_kind_confidence: ConfidenceLevel = ConfidenceLevel.OFFEN
    review_questions: list[ReviewQuestion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model_version: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def normalized(self) -> "PageAnalysis":
        return PageAnalysis(
            raw_text=_clean_multiline_text(self.raw_text) or "",
            analysis_text=_clean_inline_text(self.analysis_text) or "",
            page_kind=self.page_kind,
            page_kind_confidence=self.page_kind_confidence,
            review_questions=[item.normalized() for item in self.review_questions],
            notes=[
                cleaned
                for cleaned in (_clean_inline_text(item) for item in self.notes)
                if cleaned
            ],
            warnings=[
                cleaned
                for cleaned in (_clean_inline_text(item) for item in self.warnings)
                if cleaned
            ],
            model_version=_clean_inline_text(self.model_version),
            created_at=str(self.created_at or datetime.now(timezone.utc).isoformat()),
        )

    def to_dict(self) -> dict[str, Any]:
        item = self.normalized()
        return {
            "raw_text": item.raw_text,
            "analysis_text": item.analysis_text,
            "page_kind": item.page_kind.value,
            "page_kind_confidence": item.page_kind_confidence.value,
            "review_questions": [question.to_dict() for question in item.review_questions],
            "notes": item.notes,
            "warnings": item.warnings,
            "model_version": item.model_version,
            "created_at": item.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PageAnalysis":
        return cls(
            raw_text=str(data.get("raw_text", "") or ""),
            analysis_text=str(data.get("analysis_text", "") or ""),
            page_kind=parse_page_kind(data.get("page_kind")),
            page_kind_confidence=parse_confidence(data.get("page_kind_confidence")),
            review_questions=[
                ReviewQuestion.from_dict(item)
                for item in (data.get("review_questions", []) or [])
                if isinstance(item, dict)
            ],
            notes=[
                str(item).strip()
                for item in (data.get("notes", []) or [])
                if str(item).strip()
            ],
            warnings=[
                str(item).strip()
                for item in (data.get("warnings", []) or [])
                if str(item).strip()
            ],
            model_version=_none_if_blank(data.get("model_version")),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        ).normalized()

    @classmethod
    def empty(cls) -> "PageAnalysis":
        return cls()

    def has_open_review_points(self) -> bool:
        return any(
            question.confidence in {ConfidenceLevel.UNSICHER, ConfidenceLevel.OFFEN}
            for question in self.review_questions
        )


@dataclass(slots=True)
class PageMetadata:
    """
    Metadaten und Analyseergebnis einer einzelnen Seite.
    """

    page_number: Optional[int] = None
    source_image: Optional[str] = None
    ocr_text: str = ""
    cleaned_ocr_text: str = ""
    analysis: PageAnalysis = field(default_factory=PageAnalysis.empty)
    status: str = "ok"

    def normalized(self) -> "PageMetadata":
        return PageMetadata(
            page_number=self.page_number,
            source_image=_none_if_blank(self.source_image),
            ocr_text=_clean_multiline_text(self.ocr_text) or "",
            cleaned_ocr_text=_clean_inline_text(self.cleaned_ocr_text) or "",
            analysis=self.analysis.normalized(),
            status=_clean_inline_text(self.status) or "ok",
        )

    def to_dict(self) -> dict[str, Any]:
        item = self.normalized()
        return {
            "page_number": item.page_number,
            "source_image": item.source_image,
            "ocr_text": item.ocr_text,
            "cleaned_ocr_text": item.cleaned_ocr_text,
            "analysis": item.analysis.to_dict(),
            "status": item.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PageMetadata":
        analysis_data = data.get("analysis")
        if not isinstance(analysis_data, dict):
            analysis_data = {}

        return cls(
            page_number=data.get("page_number"),
            source_image=_none_if_blank(data.get("source_image")),
            ocr_text=str(data.get("ocr_text", "") or ""),
            cleaned_ocr_text=str(data.get("cleaned_ocr_text", "") or ""),
            analysis=PageAnalysis.from_dict(analysis_data),
            status=str(data.get("status", "ok") or "ok"),
        ).normalized()


def parse_confidence(value: Any) -> ConfidenceLevel:
    if isinstance(value, ConfidenceLevel):
        return value

    text = str(value or "").strip().lower()

    mapping = {
        "sicher": ConfidenceLevel.SICHER,
        "wahrscheinlich": ConfidenceLevel.WAHRSCHEINLICH,
        "unsicher": ConfidenceLevel.UNSICHER,
        "offen": ConfidenceLevel.OFFEN,
    }
    return mapping.get(text, ConfidenceLevel.OFFEN)


def parse_page_kind(value: Any) -> PageKind:
    if isinstance(value, PageKind):
        return value

    text = str(value or "").strip().lower()

    mapping = {
        "title_page": PageKind.TITLE_PAGE,
        "baptism": PageKind.BAPTISM,
        "marriage": PageKind.MARRIAGE,
        "burial": PageKind.BURIAL,
        "index": PageKind.INDEX,
        "register": PageKind.REGISTER,
        "mixed": PageKind.MIXED,
        "unknown": PageKind.UNKNOWN,
        "other": PageKind.OTHER,
    }
    return mapping.get(text, PageKind.UNKNOWN)


def build_basic_page_analysis(
    raw_text: str,
    analysis_text: Optional[str] = None,
    model_version: Optional[str] = None,
) -> PageAnalysis:
    raw_text = raw_text or ""
    normalized_raw = _clean_multiline_text(raw_text) or ""
    normalized_analysis = _clean_inline_text(analysis_text) or _clean_inline_text(raw_text) or ""

    page_kind, confidence, warnings = detect_page_kind(normalized_raw)

    notes: list[str] = []
    if len(normalized_raw) < MIN_OCR_CHAR_COUNT:
        warnings.append(
            f"OCR/Rohtext ist kurz ({len(normalized_raw)} Zeichen) und kann unvollständig sein."
        )

    return PageAnalysis(
        raw_text=normalized_raw,
        analysis_text=normalized_analysis,
        page_kind=page_kind,
        page_kind_confidence=confidence,
        review_questions=[],
        notes=notes,
        warnings=_unique_preserve_order(warnings),
        model_version=_none_if_blank(model_version),
    ).normalized()


def detect_page_kind(text: str) -> tuple[PageKind, ConfidenceLevel, list[str]]:
    haystack = (text or "").lower()
    warnings: list[str] = []

    if not haystack.strip():
        return PageKind.UNKNOWN, ConfidenceLevel.OFFEN, ["Kein Text für Seitentyp-Erkennung vorhanden."]

    if _contains_any(haystack, SERVICE_UNAVAILABLE_PATTERNS):
        warnings.append("Seite enthält Hinweise auf Service-Unavailable oder technische Störung.")
        return PageKind.OTHER, ConfidenceLevel.OFFEN, warnings

    if _contains_any(haystack, TITLE_PAGE_PATTERNS):
        return PageKind.TITLE_PAGE, ConfidenceLevel.WAHRSCHEINLICH, warnings

    baptism_hits = _count_hits(
        haystack,
        [
            "taufe",
            "taufen",
            "getauft",
            "bapt",
            "paten",
        ],
    )
    marriage_hits = _count_hits(
        haystack,
        [
            "trauung",
            "copul",
            "getraut",
            "ehe",
            "braut",
            "bräutigam",
        ],
    )
    burial_hits = _count_hits(
        haystack,
        [
            "begraben",
            "beerdigt",
            "gestorben",
            "verstorben",
            "tod",
            "sterbe",
        ],
    )
    index_hits = _count_hits(
        haystack,
        [
            "index",
            "register",
            "alphabet",
            "verzeichnis",
        ],
    )

    scores: list[tuple[PageKind, int]] = [
        (PageKind.BAPTISM, baptism_hits),
        (PageKind.MARRIAGE, marriage_hits),
        (PageKind.BURIAL, burial_hits),
        (PageKind.INDEX, index_hits),
    ]
    scores.sort(key=lambda item: item[1], reverse=True)

    best_kind, best_score = scores[0]
    second_score = scores[1][1]

    if best_score <= 0:
        if _contains_any(haystack, REGISTER_HINT_PATTERNS):
            return PageKind.REGISTER, ConfidenceLevel.UNSICHER, warnings
        return PageKind.UNKNOWN, ConfidenceLevel.OFFEN, warnings

    if best_score >= 3 and second_score == 0:
        return best_kind, ConfidenceLevel.SICHER, warnings

    if best_score >= 2 and second_score <= 1:
        return best_kind, ConfidenceLevel.WAHRSCHEINLICH, warnings

    if best_score >= 1 and second_score >= 1:
        warnings.append("Mehrere Seitentypen gleichzeitig wahrscheinlich; Seite könnte gemischt sein.")
        return PageKind.MIXED, ConfidenceLevel.UNSICHER, warnings

    return best_kind, ConfidenceLevel.UNSICHER, warnings


def page_json_filename_for_image(source_image: str | Path) -> str:
    """
    Kompatibilitätsfunktion für bestehenden Code.
    """
    image_path = Path(source_image)
    return f"{image_path.stem}.json"


def build_and_save_page_metadata(*args, **kwargs) -> dict[str, Any]:
    """
    Kompatibilitätsfunktion für bestehenden Code.

    Sie akzeptiert bewusst flexible Argumente, damit alter Aufrufcode
    zunächst weiterläuft, während wir den Rest schrittweise umbauen.
    """
    source_image = _extract_source_image(args, kwargs)
    output_path = _extract_output_path(args, kwargs)

    page_number = kwargs.get("page_number")
    ocr_text = kwargs.get("ocr_text", "") or ""
    cleaned_ocr_text = kwargs.get("cleaned_ocr_text", "") or ""
    status = kwargs.get("status", "ok") or "ok"
    model_version = kwargs.get("model_version")

    analysis_input_text = cleaned_ocr_text or ocr_text
    analysis = build_basic_page_analysis(
        raw_text=ocr_text,
        analysis_text=analysis_input_text,
        model_version=model_version,
    )

    metadata = PageMetadata(
        page_number=page_number if isinstance(page_number, int) else None,
        source_image=str(source_image) if source_image else None,
        ocr_text=ocr_text,
        cleaned_ocr_text=cleaned_ocr_text,
        analysis=analysis,
        status=str(status),
    ).normalized()

    data = metadata.to_dict()

    if output_path is None and source_image is not None:
        output_path = Path(source_image).with_name(page_json_filename_for_image(source_image))

    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    return data


def _extract_source_image(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Optional[Path]:
    for key in ["source_image", "image_path", "page_image", "image_file"]:
        value = kwargs.get(key)
        if value:
            return Path(value)

    if args:
        first = args[0]
        if isinstance(first, (str, Path)):
            return Path(first)

    return None


def _extract_output_path(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Optional[Path]:
    for key in ["output_path", "json_path", "target_path", "metadata_path"]:
        value = kwargs.get(key)
        if value:
            return Path(value)

    if len(args) >= 2 and isinstance(args[1], (str, Path)):
        return Path(args[1])

    return None


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _count_hits(text: str, patterns: list[str]) -> int:
    return sum(1 for pattern in patterns if pattern in text)


def _unique_preserve_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for item in items:
        cleaned = _clean_inline_text(item)
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)

    return result


def _none_if_blank(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _clean_inline_text(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in text.splitlines() if part.strip()]
    cleaned = " ".join(parts).strip()
    return cleaned or None


def _clean_multiline_text(value: Any) -> Optional[str]:
    if value is None:
        return None

    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    cleaned = "\n".join(lines).strip()
    return cleaned or None
