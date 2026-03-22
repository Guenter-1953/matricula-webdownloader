import json
import sys
from pathlib import Path

from local_reader import LocalPageReader
from review_queue import add_page


MIN_CONFIDENCE = 55.0
MIN_TEXT_LENGTH = 300


def derive_output_dir(image_path: Path) -> Path:
    output_dir = image_path.parent / "entry_debug"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def derive_output_path(image_path: Path) -> Path:
    return derive_output_dir(image_path) / f"{image_path.stem}_page_events.json"


def build_questions(confidence: float, text_length: int) -> list:
    questions = []

    if confidence < MIN_CONFIDENCE:
        questions.append({
            "field": "ocr_confidence",
            "question": f"OCR-Confidence ist mit {confidence:.1f} zu niedrig. Soll die Seite per KI weiterverarbeitet werden?",
            "status": "open",
        })

    if text_length < MIN_TEXT_LENGTH:
        questions.append({
            "field": "ocr_text_length",
            "question": f"OCR-Text ist mit {text_length} Zeichen zu kurz. Ist die Seite handschriftlich/schwer lesbar und soll zur KI-Prüfung?",
            "status": "open",
        })

    return questions


def build_local_result(image_path: Path) -> dict:
    reader = LocalPageReader()
    result = reader.read_page(str(image_path))

    text = result.get("text", "").strip()
    confidence = float(result.get("confidence", 0.0))
    text_length = len(text)

    use_local_result = (
        confidence >= MIN_CONFIDENCE and text_length >= MIN_TEXT_LENGTH
    )

    queue_result = None
    questions = build_questions(confidence, text_length)

    if use_local_result:
        processing_status = "done_local"
        next_action = "continue_pipeline"
    else:
        processing_status = "needs_review"
        next_action = "queue_for_manual_or_ai_review"

        queue_result = add_page(
            str(image_path),
            reason={
                "min_confidence_required": MIN_CONFIDENCE,
                "min_text_length_required": MIN_TEXT_LENGTH,
                "actual_confidence": confidence,
                "actual_text_length": text_length,
            },
            review_type="page_review",
            priority="normal",
            source_json=str(derive_output_path(image_path)),
            questions=questions,
            decision={
                "use_local_result": use_local_result,
                "send_to_openai": False,
                "recommended_next_step": "review_or_ai_page_reading",
            },
        )

    return {
        "source_image": str(image_path),
        "page_id": image_path.stem,
        "processing_status": processing_status,
        "next_action": next_action,
        "engine": result.get("engine", "tesseract"),
        "model": "tesseract-local",
        "page_type": "",
        "event_types_on_page": [],
        "entry_count": 0,
        "entries": [],
        "ocr_text": text,
        "confidence": confidence,
        "meta": result.get("meta", {}),
        "decision": {
            "use_local_result": use_local_result,
            "send_to_openai": False,
            "reason": {
                "min_confidence_required": MIN_CONFIDENCE,
                "min_text_length_required": MIN_TEXT_LENGTH,
                "actual_confidence": confidence,
                "actual_text_length": text_length,
            },
        },
        "review_queue": queue_result,
        "questions": questions,
        "notes": [
            "Zentrale Reader-Ausgabe.",
            "Lokaler OCR-Versuch wurde zuerst ausgeführt.",
            "Schwache Seiten werden automatisch in die Review-Queue eingetragen.",
            "Gemischte Bücher werden unterstützt; Ereignistypen werden später ergänzt."
        ],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python page_reader.py /pfad/zur/seite.png")
        return

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        raise FileNotFoundError(f"Bilddatei nicht gefunden: {image_path}")

    payload = build_local_result(image_path)
    output_path = derive_output_path(image_path)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("Zentraler Reader ausgeführt.")
    print("Gespeichert in:")
    print(output_path)
    print("Processing status:")
    print(payload.get("processing_status"))
    print("Next action:")
    print(payload.get("next_action"))
    print("Confidence:")
    print(payload.get("confidence", 0.0))
    print("Review queue status:")
    print((payload.get("review_queue") or {}).get("status"))


if __name__ == "__main__":
    main()
