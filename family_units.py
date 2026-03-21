import json
import os
import sys
import uuid
from typing import Any, Dict, List, Optional


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return str(value).strip() or None


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def extract_flags(person_data: Dict[str, Any], role: str, entry_details: Dict[str, Any]) -> List[str]:
    flags: List[str] = []

    status = safe_str(person_data.get("status"))
    notes_text = " ".join([str(x) for x in safe_list(person_data.get("notes")) if x is not None]).lower()

    if status:
        status_lower = status.lower()
        if role == "groom" and "witwer" in status_lower:
            flags.append("widower")
        if role == "bride" and "witwe" in status_lower:
            flags.append("widow")

    if "witwer" in notes_text and "widower" not in flags:
        flags.append("widower")
    if "witwe" in notes_text and "widow" not in flags:
        flags.append("widow")
    if "unehelich" in notes_text:
        flags.append("illegitimate")

    details_text = json.dumps(entry_details, ensure_ascii=False).lower() if entry_details else ""
    if "dispens" in details_text or "dispensation" in details_text:
        flags.append("dispensation")
    if "unehelich" in details_text and "illegitimate" not in flags:
        flags.append("illegitimate")

    unique_flags: List[str] = []
    for flag in flags:
        if flag not in unique_flags:
            unique_flags.append(flag)

    return unique_flags


def build_full_name(given_name: Optional[str], surname: Optional[str]) -> Optional[str]:
    parts = [given_name, surname]
    combined = " ".join([p for p in parts if p])
    return combined if combined else None


def make_person(
    role: str,
    person_data: Optional[Dict[str, Any]],
    unit_id: str,
    entry_details: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(person_data, dict):
        return None

    person_id = f"{unit_id}_person_{role}"

    given_name = safe_str(person_data.get("given_name"))
    surname = safe_str(person_data.get("surname"))
    full_name = safe_str(person_data.get("full_name"))
    name_original = safe_str(person_data.get("name_original"))

    if not full_name:
        full_name = build_full_name(given_name, surname)

    attributes = {
        "age": safe_str(person_data.get("age")),
        "status": safe_str(person_data.get("status")),
        "occupation": safe_str(person_data.get("occupation")),
        "residence": safe_str(person_data.get("residence")),
        "birth_place": safe_str(person_data.get("birth_place")),
    }

    clean_attributes = {}
    for key, value in attributes.items():
        if value is not None:
            clean_attributes[key] = value

    person = {
        "person_id": person_id,
        "role": role,
        "full_name": full_name,
        "given_name": given_name,
        "surname": surname,
        "name_original": name_original,
        "sex": safe_str(person_data.get("sex")),
        "attributes": clean_attributes,
        "flags": extract_flags(person_data, role, entry_details or {}),
        "raw": person_data,
    }

    return person


def extract_persons_from_marriage_entry(entry: Dict[str, Any], unit_id: str) -> List[Dict[str, Any]]:
    persons: List[Dict[str, Any]] = []
    entry_details = entry.get("details", {}) if isinstance(entry.get("details"), dict) else {}

    groom_data = entry.get("groom") if isinstance(entry.get("groom"), dict) else {}
    bride_data = entry.get("bride") if isinstance(entry.get("bride"), dict) else {}

    groom = make_person("groom", groom_data, unit_id, entry_details)
    bride = make_person("bride", bride_data, unit_id, entry_details)

    if groom:
        if not groom.get("sex"):
            groom["sex"] = "M"
        persons.append(groom)

    if bride:
        if not bride.get("sex"):
            bride["sex"] = "F"
        persons.append(bride)

    groom_father = make_person("groom_father", groom_data.get("father"), unit_id, entry_details)
    groom_mother = make_person("groom_mother", groom_data.get("mother"), unit_id, entry_details)
    bride_father = make_person("bride_father", bride_data.get("father"), unit_id, entry_details)
    bride_mother = make_person("bride_mother", bride_data.get("mother"), unit_id, entry_details)

    if groom_father:
        if not groom_father.get("sex"):
            groom_father["sex"] = "M"
        persons.append(groom_father)

    if groom_mother:
        if not groom_mother.get("sex"):
            groom_mother["sex"] = "F"
        persons.append(groom_mother)

    if bride_father:
        if not bride_father.get("sex"):
            bride_father["sex"] = "M"
        persons.append(bride_father)

    if bride_mother:
        if not bride_mother.get("sex"):
            bride_mother["sex"] = "F"
        persons.append(bride_mother)

    return persons


def extract_relationships_from_marriage_entry(entry: Dict[str, Any], unit_id: str) -> List[Dict[str, Any]]:
    relationships: List[Dict[str, Any]] = []

    groom_id = f"{unit_id}_person_groom"
    bride_id = f"{unit_id}_person_bride"
    groom_father_id = f"{unit_id}_person_groom_father"
    groom_mother_id = f"{unit_id}_person_groom_mother"
    bride_father_id = f"{unit_id}_person_bride_father"
    bride_mother_id = f"{unit_id}_person_bride_mother"

    groom_data = entry.get("groom") if isinstance(entry.get("groom"), dict) else {}
    bride_data = entry.get("bride") if isinstance(entry.get("bride"), dict) else {}

    if isinstance(entry.get("groom"), dict) and isinstance(entry.get("bride"), dict):
        relationships.append({
            "type": "spouse",
            "person1_id": groom_id,
            "person2_id": bride_id,
        })

    if isinstance(groom_data.get("father"), dict):
        relationships.append({
            "type": "child_of",
            "child_id": groom_id,
            "parent_id": groom_father_id,
        })

    if isinstance(groom_data.get("mother"), dict):
        relationships.append({
            "type": "child_of",
            "child_id": groom_id,
            "parent_id": groom_mother_id,
        })

    if isinstance(bride_data.get("father"), dict):
        relationships.append({
            "type": "child_of",
            "child_id": bride_id,
            "parent_id": bride_father_id,
        })

    if isinstance(bride_data.get("mother"), dict):
        relationships.append({
            "type": "child_of",
            "child_id": bride_id,
            "parent_id": bride_mother_id,
        })

    return relationships


def extract_event(entry: Dict[str, Any], unit_id: str) -> Dict[str, Any]:
    details = entry.get("details", {})
    if not isinstance(details, dict):
        details = {}

    place = safe_str(entry.get("place"))
    if not place:
        place = safe_str(details.get("place"))

    return {
        "event_id": f"{unit_id}_event_1",
        "type": safe_str(entry.get("type")),
        "date": entry.get("date"),
        "place": place,
        "details": details,
    }


def build_family_unit(entry: Dict[str, Any], source_path: str, entry_index: int) -> Dict[str, Any]:
    short_uuid = uuid.uuid4().hex[:8]
    unit_id = f"fu_{entry_index:04d}_{short_uuid}"

    entry_type = safe_str(entry.get("type"))

    family_unit = {
        "unit_id": unit_id,
        "source": {
            "source_file": source_path,
            "entry_index": entry_index,
        },
        "event": extract_event(entry, unit_id),
        "persons": [],
        "relationships": [],
        "notes": safe_list(entry.get("notes")),
        "raw_text": safe_str(entry.get("raw_text")),
    }

    if entry_type == "marriage":
        family_unit["persons"] = extract_persons_from_marriage_entry(entry, unit_id)
        family_unit["relationships"] = extract_relationships_from_marriage_entry(entry, unit_id)
    else:
        family_unit["notes"].append(
            f"Entry type '{entry_type}' wird in dieser Version noch nicht speziell verarbeitet."
        )

    return family_unit


def convert_page_to_family_units(data: Dict[str, Any], source_path: str) -> Dict[str, Any]:
    entries = data.get("entries", [])
    family_units: List[Dict[str, Any]] = []

    if not isinstance(entries, list):
        entries = []

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        family_unit = build_family_unit(entry, source_path, index)
        family_units.append(family_unit)

    result = {
        "source_image": data.get("source_image"),
        "source_file": source_path,
        "family_units_count": len(family_units),
        "family_units": family_units,
    }

    return result


def make_output_path(input_path: str) -> str:
    if input_path.endswith("_chatgpt_result.json"):
        return input_path.replace("_chatgpt_result.json", "_family_units.json")
    base, ext = os.path.splitext(input_path)
    return f"{base}_family_units{ext}"


def main() -> None:
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python family_units.py /app/data/books/.../page_0004_chatgpt_result.json")
        sys.exit(1)

    input_path = sys.argv[1]

    if not os.path.isfile(input_path):
        print(f"Datei nicht gefunden: {input_path}")
        sys.exit(1)

    data = load_json(input_path)
    result = convert_page_to_family_units(data, input_path)

    output_path = make_output_path(input_path)
    save_json(output_path, result)

    print("=== FAMILY UNITS ===")
    print("Quelle:")
    print(input_path)
    print("Ziel:")
    print(output_path)
    print("Family Units:")
    print(result["family_units_count"])


if __name__ == "__main__":
    main()
