import json
import os
import sys
from typing import Any, Dict, List


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_person_index(book_data: Dict[str, Any]) -> Dict[str, Any]:
    persons: List[Dict[str, Any]] = []

    pages = book_data.get("pages", [])
    if not isinstance(pages, list):
        pages = []

    for page in pages:
        source_file = page.get("source_file")
        source_image = page.get("source_image")
        family_units = page.get("family_units", [])

        if not isinstance(family_units, list):
            continue

        for family_unit in family_units:
            unit_id = family_unit.get("unit_id")
            event = family_unit.get("event", {})
            relationships = family_unit.get("relationships", [])
            notes = family_unit.get("notes", [])
            raw_text = family_unit.get("raw_text")
            unit_persons = family_unit.get("persons", [])

            if not isinstance(unit_persons, list):
                continue

            for person in unit_persons:
                if not isinstance(person, dict):
                    continue

                person_record = {
                    "person_id": person.get("person_id"),
                    "unit_id": unit_id,
                    "source_file": source_file,
                    "source_image": source_image,
                    "event": event,
                    "role": person.get("role"),
                    "full_name": person.get("full_name"),
                    "given_name": person.get("given_name"),
                    "surname": person.get("surname"),
                    "name_original": person.get("name_original"),
                    "sex": person.get("sex"),
                    "attributes": person.get("attributes", {}),
                    "flags": person.get("flags", []),
                    "relationships": relationships,
                    "unit_notes": notes,
                    "raw_text": raw_text,
                    "raw_person": person.get("raw", {}),
                }

                persons.append(person_record)

    return {
        "book_dir": book_data.get("book_dir"),
        "pages_count": book_data.get("pages_count", 0),
        "persons_count": len(persons),
        "persons": persons,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python build_person_index.py /app/data/books/BUCHNAME/family_units_book.json")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.isfile(input_path):
        print(f"Datei nicht gefunden: {input_path}")
        sys.exit(1)

    book_data = load_json(input_path)
    result = build_person_index(book_data)

    output_dir = os.path.dirname(input_path)
    output_path = os.path.join(output_dir, "persons_from_family_units.json")
    save_json(output_path, result)

    print("=== BUILD PERSON INDEX ===")
    print("Quelle:")
    print(input_path)
    print("Ziel:")
    print(output_path)
    print("Seiten:")
    print(result["pages_count"])
    print("Personen:")
    print(result["persons_count"])


if __name__ == "__main__":
    main()
