import json
import sys
from pathlib import Path


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clean_name(value: str) -> str:
    return str(value).strip() if value else ""


def build_family_units(events):
    family_units = []

    for event in events:
        if event.get("is_header_or_meta"):
            continue

        event_type = clean_name(event.get("event_type", ""))
        if event_type.lower() != "trauung":
            continue

        groom = clean_name(event.get("groom", ""))
        bride = clean_name(event.get("bride", ""))
        groom_status = clean_name(event.get("groom_status", ""))
        bride_status = clean_name(event.get("bride_status", ""))
        other_persons = event.get("other_persons", [])
        places = event.get("places", [])

        if not groom or not bride:
            continue

        family_units.append(
            {
                "family_unit_id": f"{event.get('page_id', '')}__entry_{int(event.get('entry_index', 0)):04d}",
                "event_id": event.get("event_id", ""),
                "book_id": event.get("book_id", ""),
                "page_id": event.get("page_id", ""),
                "entry_index": event.get("entry_index", 0),
                "event_type": event_type,
                "date_text": clean_name(event.get("date_text", "")),
                "groom": {
                    "name": groom,
                    "status": groom_status,
                },
                "bride": {
                    "name": bride,
                    "status": bride_status,
                },
                "related_persons": [clean_name(p) for p in other_persons if clean_name(p)],
                "places": [clean_name(p) for p in places if clean_name(p)],
                "summary": clean_name(event.get("summary", "")),
                "notes": clean_name(event.get("notes", "")),
                "confidence": event.get("confidence", 0.0),
                "source_image": clean_name(event.get("source_image", "")),
            }
        )

    family_units.sort(key=lambda x: (x.get("page_id", ""), x.get("entry_index", 0)))
    return family_units


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_family_units.py path_to_event_index.json")
        return

    json_path = Path(sys.argv[1])
    events = load_json(json_path)

    if not isinstance(events, list):
        raise ValueError("event_index.json muss eine Liste sein.")

    family_units = build_family_units(events)

    output_path = json_path.parent / "family_units.json"
    save_json(output_path, family_units)

    print(f"{len(family_units)} Familieneinheiten gespeichert in:")
    print(output_path)


if __name__ == "__main__":
    main()
