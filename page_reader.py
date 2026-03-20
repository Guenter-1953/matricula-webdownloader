import json
import sys
from pathlib import Path

from local_reader import LocalPageReader


MIN_CONFIDENCE = 55.0
MIN_TEXT_LENGTH = 300


def derive_output_dir(image_path: Path) -> Path:
    output_dir = image_path.parent / "entry_debug"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def derive_output_path(image_path: Path) -> Path:
    return derive_output_dir(image_path) / f"{image_path.stem}_page_events.json"


def build_local_result(image_path: Path) -> dict:
    reader = LocalPageReader()
    result = reader.read_page(str(image_path))

    text = result.get("text", "").strip()
    confidence = float(result.get("confidence", 0.0))

    use_local_result = (
        confidence >= MIN_CONFIDENCE and len(text) >= MIN_TEXT_LENGTH
    )

    if use_local_result:
        processing_status = "done_local"
        next_action = "continue_pipeline"
    else:
        processing_status = "needs_openai"
        next_action = "queue_for_openai"

    return {
        "source_image": str(image_path),
        "page_id": image_path.stem,
        "model": "tesseract-local",
        "engine": result.get("engine", "tesseract"),
        "processing_status": processing_status,
        "next_action": next_action,
        "entry_count": 0,
        "entries": [],
        "ocr_text": text,
        "confidence": confidence,
        "meta": result.get("meta", {}),
        "decision": {
            "use_local_result": use_local_result,
            "send_to_openai": not use_local_result,
            "reason": {
                "min_confidence_required": MIN_CONFIDENCE,
                "min_text_length_required": MIN_TEXT_LENGTH,
                "actual_confidence": confidence,
                "actual_text_length": len(text),
            },
        },
        "notes": [
            "Zentrale Reader-Ausgabe.",
            "Lokaler OCR-Versuch wurde zuerst ausgeführt.",
            "Wenn das Ergebnis zu schwach ist, wird die Seite vorerst nur für OpenAI markiert."
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


if __name__ == "__main__":
    main()
