import json
import sys
from pathlib import Path
from datetime import datetime


IMPORT_DIR = Path("/app/data/chatgpt_review")
OUTPUT_SUFFIX = "_chatgpt_result.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_input(json_path: Path) -> dict:
    return json.loads(json_path.read_text(encoding="utf-8"))


def build_output_path(source_image: str) -> Path:
    image_path = Path(source_image)
    return image_path.parent / "entry_debug" / f"{image_path.stem}{OUTPUT_SUFFIX}"


def as_string(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [value]


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "ja"}
    return bool(value)


def as_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def normalize_person(person) -> dict:
    if isinstance(person, str):
        return {
            "role": "",
            "name": person.strip(),
            "details": "",
            "confidence": None,
        }

    if not isinstance(person, dict):
        return {
            "role": "",
            "name": as_string(person),
            "details": "",
            "confidence": None,
        }

    return {
        "role": as_string(person.get("role")),
        "name": as_string(person.get("name")),
        "details": as_string(person.get("details")),
        "confidence": person.get("confidence"),
    }


def normalize_entry(entry: dict, entry_index: int) -> dict:
    if not isinstance(entry, dict):
        entry = {}

    persons = [normalize_person(p) for p in as_list(entry.get("persons"))]
    places = [as_string(p) for p in as_list(entry.get("places")) if as_string(p)]
    unsicherheiten = [as_string(u) for u in as_list(entry.get("unsicherheiten")) if as_string(u)]
    notes = [as_string(n) for n in as_list(entry.get("notes")) if as_string(n)]

    return {
        "entry_index": entry_index,
        "entry_label": as_string(entry.get("entry_label")),
        "is_header_or_meta": as_bool(entry.get("is_header_or_meta")),
        "event_type": as_string(entry.get("event_type")),
        "date_text": as_string(entry.get("date_text")),
        "language": as_string(entry.get("language")),
        "persons": persons,
        "places": places,
        "source_text_summary_german": as_string(entry.get("source_text_summary_german")),
        "genealogical_notes_german": as_string(entry.get("genealogical_notes_german")),
        "unsicherheiten": unsicherheiten,
        "notes": notes,
        "confidence": as_float(entry.get("confidence"), 0.0),
    }


def normalize_entries(data: dict) -> list:
    raw_entries = data.get("entries", [])
    normalized = []

    for idx, entry in enumerate(raw_entries, start=1):
        normalized.append(normalize_entry(entry, idx))

    return normalized


def import_chatgpt_result(json_path: Path) -> dict:
    data = load_input(json_path)

    source_image = as_string(data.get("source_image"))
    if not source_image:
        raise ValueError("source_image fehlt im JSON")

    entries = normalize_entries(data)

    output = {
        "source_image": source_image,
        "imported_at": now_iso(),
        "engine": "chatgpt_manual",
        "page_type": as_string(data.get("page_type")),
        "event_types_on_page": [as_string(v) for v in as_list(data.get("event_types_on_page")) if as_string(v)],
        "entry_count": len(entries),
        "entries": entries,
        "notes": as_string(data.get("notes")),
        "review_status": "unreviewed",
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
