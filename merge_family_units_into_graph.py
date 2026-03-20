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

    name = str(name).lower().strip()
    name = name.replace("ä", "ae")
    name = name.replace("ö", "oe")
    name = name.replace("ü", "ue")
    name = name.replace("ß", "ss")
    name = " ".join(name.split())
    return name


def build_person_id(name: str) -> str:
    return normalize_name(name).replace(" ", "_")


def get_or_create_person(persons_by_id: dict, name: str):
    person_id = build_person_id(name)

    if person_id not in persons_by_id:
        persons_by_id[person_id] = {
            "person_id": person_id,
            "display_name": name.strip(),
            "normalized_name": normalize_name(name),
            "mentions": [],
        }

    return persons_by_id[person_id]


def append_unique_mention(person: dict, mention: dict):
    if mention not in person["mentions"]:
        person["mentions"].append(mention)


def build_graph(family_units: list):
    persons_by_id = {}
    families = []

    for family in family_units:
        groom_name = (family.get("groom", {}) or {}).get("name", "").strip()
        bride_name = (family.get("bride", {}) or {}).get("name", "").strip()

        if not groom_name or not bride_name:
            continue

        groom = get_or_create_person(persons_by_id, groom_name)
        bride = get_or_create_person(persons_by_id, bride_name)

        family_id = family.get("family_unit_id", "")
        event_id = family.get("event_id", "")
        page_id = family.get("page_id", "")
        date_text = family.get("date_text", "")
        event_type = family.get("event_type", "")
        confidence = family.get("confidence", 0.0)
        source_image = family.get("source_image", "")
        summary = family.get("summary", "")
        notes = family.get("notes", "")
        places = family.get("places", [])
        related_persons = family.get("related_persons", [])

        family_node = {
            "family_id": family_id,
            "event_id": event_id,
            "page_id": page_id,
            "event_type": event_type,
            "date_text": date_text,
            "groom_person_id": groom["person_id"],
            "bride_person_id": bride["person_id"],
            "groom_name": groom_name,
            "bride_name": bride_name,
            "related_persons": related_persons,
            "places": places,
            "summary": summary,
            "notes": notes,
            "confidence": confidence,
            "source_image": source_image,
        }

        families.append(family_node)

        mention = {
            "family_id": family_id,
            "event_id": event_id,
            "page_id": page_id,
            "role": "groom",
            "date_text": date_text,
            "event_type": event_type,
            "confidence": confidence,
        }
        append_unique_mention(groom, mention)

        mention = {
            "family_id": family_id,
            "event_id": event_id,
            "page_id": page_id,
            "role": "bride",
            "date_text": date_text,
            "event_type": event_type,
            "confidence": confidence,
        }
        append_unique_mention(bride, mention)

    persons = list(persons_by_id.values())
    persons.sort(key=lambda p: p["normalized_name"])
    families.sort(key=lambda f: (f.get("page_id", ""), f.get("family_id", "")))

    return {
        "persons": persons,
        "families": families,
        "person_count": len(persons),
        "family_count": len(families),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python merge_family_units_into_graph.py path_to_family_units.json")
        return

    json_path = Path(sys.argv[1])
    family_units = load_json(json_path)

    if not isinstance(family_units, list):
        raise ValueError("family_units.json muss eine Liste sein.")

    graph = build_graph(family_units)

    output_path = json_path.parent / "family_graph.json"
    save_json(output_path, graph)

    print(f"Personen: {graph['person_count']}")
    print(f"Familien: {graph['family_count']}")
    print(output_path)


if __name__ == "__main__":
    main()
