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


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def build_groups(persons: List[Dict[str, Any]], field_name: str) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}

    for person in persons:
        if not isinstance(person, dict):
            continue

        raw_value = person.get(field_name)
        norm_value = normalize_text(raw_value)

        if not norm_value:
            continue

        if norm_value not in grouped:
            grouped[norm_value] = {
                "match_type": field_name,
                "match_value": raw_value,
                "normalized_value": norm_value,
                "count": 0,
                "persons": [],
            }

        grouped[norm_value]["count"] += 1
        grouped[norm_value]["persons"].append({
            "person_id": person.get("person_id"),
            "unit_id": person.get("unit_id"),
            "role": person.get("role"),
            "full_name": person.get("full_name"),
            "name_original": person.get("name_original"),
            "sex": person.get("sex"),
            "source_file": person.get("source_file"),
            "event": person.get("event"),
            "attributes": person.get("attributes", {}),
            "flags": person.get("flags", []),
        })

    result = []
    for group in grouped.values():
        if group["count"] >= 2:
            result.append(group)

    result.sort(key=lambda x: (-x["count"], x["normalized_value"]))
    return result


def build_merge_candidates(data: Dict[str, Any]) -> Dict[str, Any]:
    persons = data.get("persons", [])
    if not isinstance(persons, list):
        persons = []

    full_name_groups = build_groups(persons, "full_name")
    original_name_groups = build_groups(persons, "name_original")

    return {
        "book_dir": data.get("book_dir"),
        "pages_count": data.get("pages_count", 0),
        "persons_count": len(persons),
        "merge_candidate_group_count": len(full_name_groups) + len(original_name_groups),
        "full_name_candidates": full_name_groups,
        "name_original_candidates": original_name_groups,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python build_merge_candidates.py /app/data/books/BUCHNAME/persons_from_family_units.json")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.isfile(input_path):
        print(f"Datei nicht gefunden: {input_path}")
        sys.exit(1)

    data = load_json(input_path)
    result = build_merge_candidates(data)

    output_dir = os.path.dirname(input_path)
    output_path = os.path.join(output_dir, "merge_candidates.json")
    save_json(output_path, result)

    print("=== BUILD MERGE CANDIDATES ===")
    print("Quelle:")
    print(input_path)
    print("Ziel:")
    print(output_path)
    print("Personen:")
    print(result["persons_count"])
    print("Kandidatengruppen:")
    print(result["merge_candidate_group_count"])


if __name__ == "__main__":
    main()
