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


def normalize_person_name(name: str) -> str:
    if not name:
        return ""

    name = " ".join(name.strip().split())
    return name


def collect_persons(entry: dict):
    persons = []

    groom = normalize_person_name(entry.get("groom", ""))
    bride = normalize_person_name(entry.get("bride", ""))
    other_persons = entry.get("other_persons", [])

    if groom:
        persons.append(groom)

    if bride:
        persons.append(bride)

    for person in other_persons:
        person = normalize_person_name(str(person))
        if person and person not in persons:
            persons.append(person)

    return persons


def build_event_id(book_id: str, page_id: str, entry_label: str, index: int) -> str:
    safe_label = (entry_label or "").strip()
    if safe_label:
        safe_label = safe_label.replace(" ", "_")
        return f"{book_id}__{page_id}__label_{safe_label}"
    return f"{book_id}__{page_id}__entry_{index:04d}"


def convert_page_entries_to_events(page_payload: dict):
    book_id = Path(page_payload.get("source_image", "")).parent.name or "unknown_book"
    page_id = page_payload.get("page_id", "")
    source_image = page_payload.get("source_image", "")
    entries = page_payload.get("entries", [])

    events = []

    for idx, entry in enumerate(entries, start=1):
        entry_label = str(entry.get("entry_label", "")).strip()
        persons = collect_persons(entry)

        event = {
            "event_id": build_event_id(book_id, page_id, entry_label, idx),
            "book_id": book_id,
            "page_id": page_id,
            "entry_index": idx,
            "entry_label": entry_label,
            "is_header_or_meta": bool(entry.get("is_header_or_meta", False)),
            "event_type": entry.get("event_type", ""),
            "date_text": entry.get("date_text", ""),
            "language": entry.get("language", ""),
            "summary": entry.get("source_text_summary_german", ""),
            "notes": entry.get("genealogical_notes_german", ""),
            "unsicherheiten": entry.get("unsicherheiten", []),
            "confidence": entry.get("confidence", 0.0),
            "snippet_path": "",
            "name_snippet_path": "",
            "source_image": source_image,
            "groom": entry.get("groom", ""),
            "groom_status": entry.get("groom_status", ""),
            "bride": entry.get("bride", ""),
            "bride_status": entry.get("bride_status", ""),
            "other_persons": entry.get("other_persons", []),
            "places": entry.get("places", []),
            "persons": persons,
            "reviewed": False,
        }

        events.append(event)

    return events


def merge_into_event_index(event_index_path: Path, new_events: list, page_id: str):
    if event_index_path.exists():
        existing_events = load_json(event_index_path)
        if not isinstance(existing_events, list):
            existing_events = []
    else:
        existing_events = []

    kept_events = [e for e in existing_events if e.get("page_id") != page_id]
    merged = kept_events + new_events

    merged.sort(
        key=lambda e: (
            e.get("page_id", ""),
            e.get("entry_index", 0),
        )
    )

    save_json(event_index_path, merged)
    return merged


def main():
    if len(sys.argv) < 2:
        print("Usage: python page_events_to_event_index.py path_to_page_events.json")
        return

    page_events_path = Path(sys.argv[1])
    page_payload = load_json(page_events_path)

    if not isinstance(page_payload, dict):
        raise ValueError("page_events.json hat nicht das erwartete Objektformat.")

    page_id = page_payload.get("page_id", "")
    if not page_id:
        raise ValueError("page_id fehlt in der page_events-Datei.")

    new_events = convert_page_entries_to_events(page_payload)

    output_dir = page_events_path.parent
    event_index_path = output_dir / "event_index.json"

    merged = merge_into_event_index(
        event_index_path=event_index_path,
        new_events=new_events,
        page_id=page_id,
    )

    print(f"Seite verarbeitet: {page_id}")
    print(f"Neue/aktualisierte Ereignisse dieser Seite: {len(new_events)}")
    print(f"Gesamte Ereignisse in event_index.json: {len(merged)}")
    print(event_index_path)


if __name__ == "__main__":
    main()
