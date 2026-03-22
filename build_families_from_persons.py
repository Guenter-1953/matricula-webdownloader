import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Tuple


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_name(value: Any) -> str:
    text = safe_str(value).lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = " ".join(text.split())
    return text


def extract_key_parts(persons: List[Dict[str, Any]], event: Dict[str, Any]) -> Tuple[str, str, str]:
    father_name = ""
    mother_name = ""
    place = safe_str((event or {}).get("place"))

    for person in persons:
        if not isinstance(person, dict):
            continue
        role = safe_str(person.get("role")).lower()
        full_name = safe_str(person.get("full_name")) or safe_str(person.get("name_original"))

        if role == "father" and full_name and not father_name:
            father_name = full_name
        elif role == "mother" and full_name and not mother_name:
            mother_name = full_name

    return (
        normalize_name(father_name),
        normalize_name(mother_name),
        normalize_name(place),
    )


def extract_children(persons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    children = []

    for person in persons:
        if not isinstance(person, dict):
            continue

        role = safe_str(person.get("role")).lower()
        if role != "child":
            continue

        children.append({
            "person_id": person.get("person_id"),
            "full_name": safe_str(person.get("full_name")) or safe_str(person.get("name_original")),
            "name_original": safe_str(person.get("name_original")),
        })

    return children


def build_family_record(group_key: Tuple[str, str, str], units: List[Dict[str, Any]]) -> Dict[str, Any]:
    father_norm, mother_norm, place_norm = group_key

    father_display = ""
    mother_display = ""
    place_display = ""

    children = []
    events = []

    seen_children = set()

    for unit in units:
        event = unit.get("event", {}) or {}
        persons = unit.get("persons", []) or []

        if not place_display:
            place_display = safe_str(event.get("place"))

        for person in persons:
            if not isinstance(person, dict):
                continue

            role = safe_str(person.get("role")).lower()
            full_name = safe_str(person.get("full_name")) or safe_str(person.get("name_original"))

            if role == "father" and full_name and not father_display:
                father_display = full_name
            elif role == "mother" and full_name and not mother_display:
                mother_display = full_name

        for child in extract_children(persons):
            child_key = (
                child.get("person_id"),
                child.get("full_name"),
                safe_str(event.get("date_text")),
            )
            if child_key in seen_children:
                continue
            seen_children.add(child_key)
            children.append({
                "person_id": child.get("person_id"),
                "full_name": child.get("full_name"),
                "name_original": child.get("name_original"),
                "date_text": safe_str(event.get("date_text")),
                "event_type": safe_str(event.get("type")),
                "source_image": ((unit.get("source") or {}).get("source_image")),
                "unit_id": unit.get("unit_id"),
            })

        events.append({
            "unit_id": unit.get("unit_id"),
            "event_type": safe_str(event.get("type")),
            "date_text": safe_str(event.get("date_text")),
            "place": safe_str(event.get("place")),
            "source_image": ((unit.get("source") or {}).get("source_image")),
            "summary": safe_str(unit.get("summary")),
            "uncertainties": unit.get("uncertainties", []),
            "confidence": unit.get("confidence", 0.0),
        })

    children.sort(key=lambda x: (safe_str(x.get("date_text")), safe_str(x.get("full_name"))))
    events.sort(key=lambda x: (safe_str(x.get("date_text")), safe_str(x.get("unit_id"))))

    family_id_parts = [father_norm or "ohne_vater", mother_norm or "ohne_mutter", place_norm or "ohne_ort"]
    family_id = "fam_" + "__".join(part.replace(" ", "_") for part in family_id_parts)

    return {
        "family_id": family_id,
        "father_name": father_display or None,
        "mother_name": mother_display or None,
        "place": place_display or None,
        "children_count": len(children),
        "events_count": len(events),
        "children": children,
        "events": events,
    }


def build_families(persons_data: Dict[str, Any]) -> Dict[str, Any]:
    persons = persons_data.get("persons", [])
    if not isinstance(persons, list):
        persons = []

    units_by_id: Dict[str, Dict[str, Any]] = {}

    for person in persons:
        if not isinstance(person, dict):
            continue

        unit_id = safe_str(person.get("unit_id"))
        if not unit_id:
            continue

        if unit_id not in units_by_id:
            units_by_id[unit_id] = {
                "unit_id": unit_id,
                "event": person.get("event", {}) or {},
                "source_file": person.get("source_file"),
                "source_image": person.get("source_image"),
                "persons": [],
                "unit_notes": person.get("unit_notes", []),
                "raw_text": person.get("raw_text"),
            }

        units_by_id[unit_id]["persons"].append({
            "person_id": person.get("person_id"),
            "role": person.get("role"),
            "full_name": person.get("full_name"),
            "name_original": person.get("name_original"),
        })

    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

    for unit in units_by_id.values():
        event = unit.get("event", {}) or {}
        event_type = safe_str(event.get("type")).lower()

        if event_type not in {"taufe", "geburt", "baptism"}:
            continue

        key = extract_key_parts(unit.get("persons", []), event)

        # Nur Familien bilden, wenn wenigstens Vater oder Mutter oder Ort als Gruppierung vorhanden ist
        if not any(key):
            continue

        grouped[key].append(unit)

    families = []
    for key, units in grouped.items():
        families.append(build_family_record(key, units))

    families.sort(
        key=lambda x: (
            normalize_name(x.get("father_name")),
            normalize_name(x.get("mother_name")),
            normalize_name(x.get("place")),
        )
    )

    return {
        "book_dir": persons_data.get("book_dir"),
        "pages_count": persons_data.get("pages_count", 0),
        "families_count": len(families),
        "families": families,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python build_families_from_persons.py /app/data/books/BUCHNAME/persons_from_family_units.json")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.isfile(input_path):
        print(f"Datei nicht gefunden: {input_path}")
        sys.exit(1)

    persons_data = load_json(input_path)
    result = build_families(persons_data)

    output_dir = os.path.dirname(input_path)
    output_path = os.path.join(output_dir, "families_from_persons.json")
    save_json(output_path, result)

    print("=== BUILD FAMILIES FROM PERSONS ===")
    print("Quelle:")
    print(input_path)
    print("Ziel:")
    print(output_path)
    print("Familien:")
    print(result["families_count"])


if __name__ == "__main__":
    main()
