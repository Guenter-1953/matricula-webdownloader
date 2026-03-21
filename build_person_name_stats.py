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


def normalize_name(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_person_name_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    persons = data.get("persons", [])
    if not isinstance(persons, list):
        persons = []

    full_name_stats: Dict[str, Dict[str, Any]] = {}
    original_name_stats: Dict[str, Dict[str, Any]] = {}
    missing_name_persons: List[Dict[str, Any]] = []

    for person in persons:
        if not isinstance(person, dict):
            continue

        full_name = normalize_name(person.get("full_name"))
        name_original = normalize_name(person.get("name_original"))
        role = person.get("role")
        unit_id = person.get("unit_id")
        person_id = person.get("person_id")
        source_file = person.get("source_file")

        short_record = {
            "person_id": person_id,
            "unit_id": unit_id,
            "role": role,
            "source_file": source_file,
            "full_name": full_name or None,
            "name_original": name_original or None,
        }

        if full_name:
            if full_name not in full_name_stats:
                full_name_stats[full_name] = {
                    "name": full_name,
                    "count": 0,
                    "roles": {},
                    "persons": [],
                }

            full_name_stats[full_name]["count"] += 1
            full_name_stats[full_name]["roles"][role] = full_name_stats[full_name]["roles"].get(role, 0) + 1
            full_name_stats[full_name]["persons"].append(short_record)

        if name_original:
            if name_original not in original_name_stats:
                original_name_stats[name_original] = {
                    "name": name_original,
                    "count": 0,
                    "roles": {},
                    "persons": [],
                }

            original_name_stats[name_original]["count"] += 1
            original_name_stats[name_original]["roles"][role] = original_name_stats[name_original]["roles"].get(role, 0) + 1
            original_name_stats[name_original]["persons"].append(short_record)

        if not full_name and not name_original:
            missing_name_persons.append(short_record)

    full_name_list = sorted(
        full_name_stats.values(),
        key=lambda x: (-x["count"], x["name"].lower())
    )

    original_name_list = sorted(
        original_name_stats.values(),
        key=lambda x: (-x["count"], x["name"].lower())
    )

    return {
        "book_dir": data.get("book_dir"),
        "pages_count": data.get("pages_count", 0),
        "persons_count": len(persons),
        "unique_full_names_count": len(full_name_list),
        "unique_original_names_count": len(original_name_list),
        "missing_name_count": len(missing_name_persons),
        "full_name_stats": full_name_list,
        "original_name_stats": original_name_list,
        "missing_name_persons": missing_name_persons,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python build_person_name_stats.py /app/data/books/BUCHNAME/persons_from_family_units.json")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.isfile(input_path):
        print(f"Datei nicht gefunden: {input_path}")
        sys.exit(1)

    data = load_json(input_path)
    result = build_person_name_stats(data)

    output_dir = os.path.dirname(input_path)
    output_path = os.path.join(output_dir, "person_name_stats.json")
    save_json(output_path, result)

    print("=== BUILD PERSON NAME STATS ===")
    print("Quelle:")
    print(input_path)
    print("Ziel:")
    print(output_path)
    print("Personen:")
    print(result["persons_count"])
    print("Eindeutige full_name:")
    print(result["unique_full_names_count"])
    print("Eindeutige name_original:")
    print(result["unique_original_names_count"])
    print("Ohne Namen:")
    print(result["missing_name_count"])


if __name__ == "__main__":
    main()
