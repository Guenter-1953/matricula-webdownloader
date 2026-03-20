import json
import sys
from pathlib import Path

from local_reader import LocalPageReader
from openai_reader import OpenAIPageReader


MIN_CONFIDENCE = 55.0
MIN_TEXT_LENGTH = 300


def derive_output_dir(image_path: Path) -> Path:
    output_dir = image_path.parent / "entry_debug"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def derive_output_path(image_path: Path) -> Path:
    return derive_output_dir(image_path) / f"{image_path.stem}_page_events.json"


def run_local_reader(image_path: Path) -> dict:
    reader = LocalPageReader()
    result = reader.read_page(str(image_path))

    text = result.get("text", "").strip()
    confidence = float(result.get("confidence", 0.0))

    use_local_result = (
        confidence >= MIN_CONFIDENCE and len(text) >= MIN_TEXT_LENGTH
    )

    return {
        "source_image": str(image_path),
        "page_id": image_path.stem,
        "engine": result.get("engine", "tesseract"),
        "model": "tesseract-local",
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
    }


def run_openai_reader(image_path: Path) -> dict:
    reader = OpenAIPageReader()
    result = reader.read_page(str(image_path))

    raw_response = result.get("raw_response", "").strip()

    parsed_json = None
    parse_error = None

    try:
        parsed_json = json.loads(raw_response)
    except Exception as e:
        parse_error = str(e)

    return {
        "engine": result.get("engine", "openai"),
        "model": result.get("model", ""),
        "raw_response": raw_response,
        "parsed_json": parsed_json,
        "parse_error": parse_error,
    }


def build_payload(image_path: Path) -> dict:
    local_result = run_local_reader(image_path)

    if local_result["decision"]["use_local_result"]:
        return {
            "source_image": local_result["source_image"],
            "page_id": local_result["page_id"],
            "processing_status": "done_local",
            "next_action": "continue_pipeline",
            "engine": local_result["engine"],
            "model": local_result["model"],
            "entry_count": 0,
            "entries": [],
            "ocr_text": local_result["ocr_text"],
            "confidence": local_result["confidence"],
            "meta": local_result["meta"],
            "decision": local_result["decision"],
            "notes": [
                "Lokaler Reader war ausreichend.",
                "OpenAI wurde nicht verwendet."
            ],
        }

    openai_result = run_openai_reader(image_path)

    parsed = openai_result.get("parsed_json") or {}
    entries = parsed.get("entries", []) if isinstance(parsed, dict) else []
    notes = parsed.get("notes", "") if isinstance(parsed, dict) else ""

    return {
        "source_image": local_result["source_image"],
        "page_id": local_result["page_id"],
        "processing_status": "done_openai",
        "next_action": "continue_pipeline",
        "engine": openai_result.get("engine", "openai"),
        "model": openai_result.get("model", ""),
        "entry_count": len(entries),
        "entries": entries,
        "ocr_text": local_result["ocr_text"],
        "confidence": local_result["confidence"],
        "meta": {
            "local": local_result["meta"],
            "openai_parse_error": openai_result.get("parse_error"),
        },
        "decision": local_result["decision"],
        "openai": {
            "raw_response": openai_result.get("raw_response", ""),
            "parsed_json_available": openai_result.get("parsed_json") is not None,
        },
        "notes": [
            "Lokaler Reader war zu schwach.",
            "Seite wurde deshalb an OpenAI gesendet.",
            notes,
        ],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python page_reader.py /pfad/zur/seite.png")
        return

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        raise FileNotFoundError(f"Bilddatei nicht gefunden: {image_path}")

    payload = build_payload(image_path)
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
    print("Engine:")
    print(payload.get("engine"))
    print("Entry count:")
    print(payload.get("entry_count", 0))


if __name__ == "__main__":
    main()
