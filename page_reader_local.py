import json
import sys
from pathlib import Path

from local_reader import LocalPageReader


def derive_output_dir(image_path: Path) -> Path:
    output_dir = image_path.parent / "entry_debug"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def derive_output_path(image_path: Path) -> Path:
    return derive_output_dir(image_path) / f"{image_path.stem}_page_events_local.json"


def build_payload(image_path: Path) -> dict:
    reader = LocalPageReader()
    result = reader.read_page(str(image_path))

    text = result.get("text", "").strip()

    return {
        "source_image": str(image_path),
        "page_id": image_path.stem,
        "model": "tesseract-local",
        "engine": result.get("engine", "tesseract"),
        "entry_count": 0,
        "entries": [],
        "ocr_text": text,
        "confidence": result.get("confidence", 0.0),
        "meta": result.get("meta", {}),
        "notes": [
            "Dies ist die lokale OCR-Ausgabe mit Tesseract.",
            "Die eigentliche Zerlegung in Einträge folgt später.",
            "Das Ausgabeformat bleibt mit dem restlichen Workflow kompatibel."
        ],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python page_reader_local.py /pfad/zur/seite.png")
        return

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        raise FileNotFoundError(f"Bilddatei nicht gefunden: {image_path}")

    payload = build_payload(image_path)
    output_path = derive_output_path(image_path)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("Lokaler OCR-Reader ausgeführt.")
    print("Gespeichert in:")
    print(output_path)
    print("OCR-Zeichen:")
    print(len(payload.get("ocr_text", "")))
    print("Confidence:")
    print(payload.get("confidence", 0.0))


if __name__ == "__main__":
    main()
