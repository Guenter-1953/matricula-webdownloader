import json
import sys
from pathlib import Path


INVALID_NAMES = {
    "",
    "unbekannt",
    "unknown",
    "?",
    "n/a",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_valid_name(name: str) -> bool:
    if not name:
        return False

    n = name.lower().strip()

    if n in INVALID_NAMES:
        return False

    if len(n) < 3:
        return False

    return True


def merge_mentions(target, source):
    existing = target["mentions"]
    for m in source["mentions"]:
        if m not in existing:
            existing.append(m)


def clean_persons(persons):
    cleaned = {}

    for person in persons:
        name = person.get("display_name", "").strip()

        if not is_valid_name(name):
            continue

        key = name.lower()

        if key not in cleaned:
            cleaned[key] = person
        else:
            merge_mentions(cleaned[key], person)

    result = list(cleaned.values())
    result.sort(key=lambda p: p.get("normalized_name", ""))

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python clean_persons_from_page_events.py path_to_persons.json")
        return

    input_path = Path(sys.argv[1])
    persons = load_json(input_path)

    cleaned = clean_persons(persons)

    output_path = input_path.parent / "persons_cleaned.json"
    save_json(output_path, cleaned)

    print(f"Vorher: {len(persons)} Personen")
    print(f"Nachher: {len(cleaned)} Personen")
    print(output_path)


if __name__ == "__main__":
    main()
