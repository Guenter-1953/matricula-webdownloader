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


def clean_string(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_list(values) -> list:
    if values is None:
        return []
    if isinstance(values, list):
        return values
    return [values]


def normalize_person(person) -> dict:
    if isinstance(person, str):
        return {
            "role": "",
            "name": clean_string(person),
            "details": "",
            "confidence": None,
        }

    if not isinstance(person, dict):
        return {
            "role": "",
            "name": clean_string(person),
            "details": "",
            "confidence": None,
        }

    return {
        "role": clean_string(person.get("role")),
        "name": clean_string(person.get("name")),
        "details": clean_string(person.get("details")),
        "confidence": person.get("confidence"),
    }


def build_family_units(data: dict):
    family_units = []

    source_image = clean_string(data.get("source_image"))
    entries = clean_list(data.get("entries"))
    page_id = Path(source_image).stem if source_image else ""
    book_id = Path(source_image).parent.name if source_image else ""

    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue

        if entry.get("is_header_or_meta"):
            continue

        event_type = clean_string(entry.get("event_type"))
        if not event_type:
            event_type = "Unklar"

        persons = [
            normalize_person(p)
            for p in clean_list(entry.get("persons"))
            if clean_string(p if isinstance(p, str) else p.get("name"))
        ]

        places = [clean_string(p) for p in clean_list(entry.get("places")) if clean_string(p)]
        uncertainties = [clean_string(u) for u in clean_list(entry.get("unsicherheiten")) if clean_string(u)]
        notes = [clean_string(n) for n in clean_list(entry.get("notes")) if clean_string(n)]

        entry_index = entry.get("entry_index", idx)
        try:
            entry_index_int = int(entry_index)
        except Exception:
            entry_index_int = idx

        family_units.append(
            {
                "family_unit_id": f"{page_id}__entry_{entry_index_int:04d}",
                "book_id": book_id,
                "page_id": page_id,
                "entry_index": entry_index_int,
                "entry_label": clean_string(entry.get("entry_label")),
                "event_type": event_type,
                "date_text": clean_string(entry.get("date_text")),
                "language": clean_string(entry.get("language")),
                "persons": persons,
                "places": places,
                "summary": clean_string(entry.get("source_text_summary_german")),
                "genealogical_notes": clean_string(entry.get("genealogical_notes_german")),
                "unsicherheiten": uncertainties,
                "notes": notes,
                "confidence": entry.get("confidence", 0.0),
                "source_image": source_image,
                "review_status": "unreviewed",
            }
        )

    family_units.sort(key=lambda x: (x.get("page_id", ""), x.get("entry_index", 0)))
    return family_units


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_family_units.py /pfad/zur/page_chatgpt_result.json")
        return

    json_path = Path(sys.argv[1])
    data = load_json(json_path)

    if not isinstance(data, dict):
        raise ValueError("Eingabedatei muss ein JSON-Objekt sein.")

    family_units = build_family_units(data)

    output_path = json_path.parent / f"{json_path.stem.replace('_chatgpt_result', '')}_family_units.json"
    save_json(output_path, family_units)

    print(f"{len(family_units)} Familieneinheiten gespeichert in:")
    print(output_path)


if __name__ == "__main__":
    main()
