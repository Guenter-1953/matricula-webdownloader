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


def normalize_name(name: str) -> str:
    if not name:
        return ""

    name = name.lower().strip()
    name = name.replace("ä", "ae")
    name = name.replace("ö", "oe")
    name = name.replace("ü", "ue")
    name = name.replace("ß", "ss")
    name = " ".join(name.split())
    return name


def build_person_id(normalized_name: str) -> str:
    return normalized_name.replace(" ", "_")


def build_persons(events):
    persons_by_name = {}

    for event in events:
        if event.get("is_header_or_meta"):
            continue

        event_id = event.get("event_id", "")
        page_id = event.get("page_id", "")
        event_type = event.get("event_type", "")
        date_text = event.get("date_text", "")
        confidence = event.get("confidence", 0.0)
        source_image = event.get("source_image", "")
        summary = event.get("summary", "")
        notes = event.get("notes", "")
        persons = event.get("persons", [])

        for raw_name in persons:
            raw_name = str(raw_name).strip()
            if not raw_name:
                continue

            normalized_name = normalize_name(raw_name)
            if not normalized_name:
                continue

            if normalized_name not in persons_by_name:
                persons_by_name[normalized_name] = {
                    "person_id": build_person_id(normalized_name),
                    "display_name": raw_name,
                    "normalized_name": normalized_name,
                    "mentions": [],
                }

            persons_by_name[normalized_name]["mentions"].append(
                {
                    "event_id": event_id,
                    "page_id": page_id,
                    "event_type": event_type,
                    "date_text": date_text,
                    "confidence": confidence,
                    "source_image": source_image,
                    "summary": summary,
                    "notes": notes,
                }
            )

    result = list(persons_by_name.values())
    result.sort(key=lambda p: p["normalized_name"])
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_persons_from_page_events.py path_to_event_index.json")
        return

    json_path = Path(sys.argv[1])
    events = load_json(json_path)

    if not isinstance(events, list):
        raise ValueError("event_index.json muss eine Liste sein.")

    persons = build_persons(events)

    output_path = json_path.parent / "persons_from_page_events.json"
    save_json(output_path, persons)

    print(f"{len(persons)} Personen gespeichert in:")
    print(output_path)


if __name__ == "__main__":
    main()
