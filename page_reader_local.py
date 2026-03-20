import json
import sys
from pathlib import Path


def derive_output_dir(image_path: Path) -> Path:
    output_dir = image_path.parent / "entry_debug"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def derive_output_path(image_path: Path) -> Path:
    return derive_output_dir(image_path) / f"{image_path.stem}_page_events_local.json"


def build_placeholder_payload(image_path: Path) -> dict:
    return {
        "source_image": str(image_path),
        "page_id": image_path.stem,
        "model": "local-placeholder",
        "entry_count": 0,
        "entries": [],
        "notes": [
            "Dies ist ein Platzhalter für den lokalen Reader.",
            "Hier soll später ein Open-Source- oder lokales Modell die komplette Seite analysieren.",
            "Das Ausgabeformat ist bereits kompatibel zum restlichen Workflow."
        ]
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python page_reader_local.py /pfad/zur/seite.png")
        return

    image_path = Path(sys.argv[1])

    if not image_path.exists():
        raise FileNotFoundError(f"Bilddatei nicht gefunden: {image_path}")

    payload = build_placeholder_payload(image_path)
    output_path = derive_output_path(image_path)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("Lokaler Platzhalter-Reader ausgeführt.")
    print("Gespeichert in:")
    print(output_path)


if __name__ == "__main__":
    main()
