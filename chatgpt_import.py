import json
import sys
from pathlib import Path
from datetime import datetime


IMPORT_DIR = Path("/app/data/chatgpt_review")
OUTPUT_SUFFIX = "_chatgpt_result.json"


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def load_input(json_path: Path) -> dict:
    return json.loads(json_path.read_text(encoding="utf-8"))


def build_output_path(source_image: str) -> Path:
    image_path = Path(source_image)
    return image_path.parent / "entry_debug" / f"{image_path.stem}{OUTPUT_SUFFIX}"


def normalize_entries(data: dict) -> list:
    entries = data.get("entries", [])
    normalized = []

    for e in entries:
        normalized.append({
            "type": e.get("type", ""),
            "date": e.get("date", ""),
            "groom": e.get("groom", {}),
            "bride": e.get("bride", {}),
            "details": e.get("details", ""),
            "raw_text": e.get("raw_text", ""),
            "notes": e.get("notes", []),
        })

    return normalized


def import_chatgpt_result(json_path: Path) -> dict:
    data = load_input(json_path)

    source_image = data.get("source_image")
    if not source_image:
        raise ValueError("source_image fehlt im JSON")

    entries = normalize_entries(data)

    output = {
        "source_image": source_image,
        "imported_at": now_iso(),
        "engine": "chatgpt_manual",
        "entry_count": len(entries),
        "entries": entries,
        "notes": data.get("notes", ""),
    }

    output_path = build_output_path(source_image)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "status": "imported",
        "output_path": str(output_path),
        "entry_count": len(entries),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python chatgpt_import.py /pfad/zur/json_datei.json")
        return

    json_path = Path(sys.argv[1])

    if not json_path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {json_path}")

    result = import_chatgpt_result(json_path)

    print("=== CHATGPT IMPORT ===")
    print("Status:")
    print(result["status"])
    print("Ziel:")
    print(result["output_path"])
    print("Einträge:")
    print(result["entry_count"])


if __name__ == "__main__":
    main()
