import json
import sys
from pathlib import Path
from datetime import datetime


EXPORT_DIR = Path("/app/data/chatgpt_review")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_template(source_image: str) -> dict:
    image_path = Path(source_image)

    return {
        "created_at": now_iso(),
        "source_image": str(image_path),
        "notes": "Hier das zusammenfassende Ergebnis der manuellen ChatGPT-Auswertung eintragen.",
        "entries": [
            {
                "type": "marriage",
                "date": "",
                "groom": {
                    "name": "",
                    "details": ""
                },
                "bride": {
                    "name": "",
                    "details": ""
                },
                "details": "",
                "raw_text": "",
                "notes": [
                    ""
                ]
            }
        ]
    }


def build_output_path(source_image: str) -> Path:
    image_path = Path(source_image)
    return EXPORT_DIR / f"{image_path.stem}_chatgpt_result_template.json"


def main():
    if len(sys.argv) < 2:
        print("Usage: python chatgpt_result_template.py /pfad/zur/seite.png")
        return

    source_image = sys.argv[1]
    image_path = Path(source_image)

    if not image_path.exists():
        raise FileNotFoundError(f"Bilddatei nicht gefunden: {image_path}")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    payload = build_template(str(image_path))
    output_path = build_output_path(str(image_path))

    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=== CHATGPT RESULT TEMPLATE ===")
    print("Vorlage erzeugt:")
    print(output_path)


if __name__ == "__main__":
    main()
