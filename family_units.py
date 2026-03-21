import json
import os
import re
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple


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


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_name(raw_name: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    raw_name = safe_str(raw_name)
    if not raw_name:
        return None, None, None

    cleaned = normalize_whitespace(raw_name)

    cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
    cleaned = normalize_whitespace(cleaned)

    if not cleaned:
        return raw_name, None, None

    parts = cleaned.split(" ")

    if len(parts) == 1:
        return cleaned, cleaned, None

    surname = parts[0]
    given_name = " ".join(parts[1:])

    full_name = f"{given_name} {surname}".strip()

    return full_name, given_name, surname


def infer_status_from_text(text: str, role: str) -> Optional[str]:
    t = text.lower()

    if "viduus" in t or "witwer" in t:
        return "witwer"
    if "vidua" in t or "witwe" in t:
        return "witwe"
    if "virgo" in t or "ledig" in t:
        return "ledig"
    if "adolescens" in t:
        if role == "groom":
            return "ledig"
    return None


def infer_residence_from_text(text: str) -> Optional[str]:
    patterns = [
        r"wohnhaft in ([A-ZÄÖÜa-zäöüß\-\s]+)",
        r"aus ([A-ZÄÖÜa-zäöüß\-\s]+)",
        r"herkunft ([A-ZÄÖÜa-zäöüß\-\s]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = normalize_whitespace(match.group(1))
            value = re.split(r"[;,\.]", value)[0].strip()
            return value or None

    return None


def infer_flags_from_text(text: str, role: str) -> List[str]:
    flags: List[str] = []
    t = text.lower()

    if "viduus" in t or "witwer" in t:
        flags.append("widower")
    if "vidua" in t or "witwe" in t:
        flags.append("widow")
    if "unehelich" in t:
        flags.append("illegitimate")
    if "dispens" in t or "dispensation" in t:
        flags.append("dispensation")

    unique_flags: List[str] = []
    for flag in flags:
        if flag not in unique_flags:
            unique_flags.append(flag)

    return unique_flags


def extract_flags(person_data: Dict[str, Any], role: str, entry_details: Dict[str, Any], entry_notes: List[Any]) -> List[str]:
    flags: List[str] = []

    status = safe_str(person_data.get("status"))
    person_notes_text = " ".join([str(x) for x in safe_list(person_data.get("notes")) if x is not None]).lower()
    person_details_text = safe_str(person_data.get("details")) or ""
    entry_details_text = json.dumps(entry_details, ensure_ascii=False).lower() if entry_details else ""
    entry_notes_text = " ".join([str(x) for x in entry_notes if x is not None]).lower()

    if status:
        status_lower = status.lower()
        if role == "groom" and "witwer" in status_lower:
            flags.append("widower")
        if role == "bride" and "witwe" in status_lower:
            flags.append("widow")
        if "ledig" in status_lower and role == "bride":
            pass

    for source_text in [person_notes_text, person_details_text.lower(), entry_details_text, entry_notes_text]:
        for flag in infer_flags_from_text(source_text, role):
            if flag not in flags:
                flags.append(flag)

    return flags


def build_full_name(given_name: Optional[str], surname: Optional[str]) -> Optional[str]:
    parts = [given_name, surname]
    combined = " ".join([p for p in parts if p])
    return combined if combined else None


def build_person_name_fields(person_data: Dict[str, Any]) -> Dict[str, Optional[str]]:
    given_name = safe_str(person_data.get("given_name"))
    surname = safe_str(person_data.get("surname"))
    full_name = safe_str(person_data.get("full_name"))
    name_original = safe_str(person_data.get("name_original"))

    raw_name = safe_str(person_data.get("name"))

    if not full_name and (given_name or surname):
        full_name = build_full_name(given_name, surname)

    if not full_name and raw_name:
        guessed_full_name, guessed_given_name, guessed_surname = split_name(raw_name)
        full_name = guessed_full_name
        if not given_name:
            given_name = guessed_given_name
        if not surname:
            surname = guessed_surname

    if not name_original and raw_name:
        name_original = raw_name

    return {
        "full_name": full_name,
        "given_name": given_name,
        "surname": surname,
        "name_original": name_original,
    }


def make_person(
    role: str,
    person_data: Optional[Dict[str, Any]],
    unit_id: str,
    entry_details: Optional[Dict[str, Any]] = None,
    entry_notes: Optional[List[Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(person_data, dict):
        return None

    person_id = f"{unit_id}_person_{role}"
    entry_details = entry_details or {}
    entry_notes = entry_notes or []

    name_fields = build_person_name_fields(person_data)

    person_details_text = safe_str(person_data.get("details")) or ""
    inferred_status = infer_status_from_text(person_details_text, role)
    inferred_residence = infer_residence_from_text(person_details_text)

    attributes = {
        "age": safe_str(person_data.get("age")),
        "status": safe_str(person_data.get("status")) or inferred_status,
        "occupation": safe_str(person_data.get("occupation")),
        "residence": safe_str(person_data.get("residence")) or inferred_residence,
        "birth_place": safe_str(person_data.get("birth_place")),
        "details_text": person_details_text or None,
    }

    clean_attributes = {}
    for key, value in attributes.items():
        if value is not None:
            clean_attributes[key] = value

    person = {
        "person_id": person_id,
        "role": role,
        "full_name": name_fields["full_name"],
        "given_name": name_fields["given_name"],
        "surname": name_fields["surname"],
        "name_original": name_fields["name_original"],
        "sex": safe_str(person_data.get("sex")),
        "attributes": clean_attributes,
        "flags": extract_flags(person_data, role, entry_details, entry_notes),
        "raw": person_data,
    }

    return person


def extract_persons_from_marriage_entry(entry: Dict[str, Any], unit_id: str) -> List[Dict[str, Any]]:
    persons: List[Dict[str, Any]] = []
    entry_details = entry.get("details", {}) if isinstance(entry.get("details"), dict) else {}
    entry_notes = safe_list(entry.get("notes"))

    groom_data = entry.get("groom") if isinstance(entry.get("groom"), dict) else {}
    bride_data = entry.get("bride") if isinstance(entry.get("bride"), dict) else {}

    groom = make_person("groom", groom_data, unit_id, entry_details, entry_notes)
    bride = make_person("bride", bride_data, unit_id, entry_details, entry_notes)

    if groom:
        if not groom.get("sex"):
            groom["sex"] = "M"
        persons.append(groom)

    if bride:
        if not bride.get("sex"):
            bride["sex"] = "F"
        persons.append(bride)

    groom_father = make_person("groom_father", groom_data.get("father"), unit_id, entry_details, entry_notes)
    groom_mother = make_person("groom_mother", groom_data.get("mother"), unit_id, entry_details, entry_notes)
    bride_father = make_person("bride_father", bride_data.get("father"), unit_id, entry_details, entry_notes)
    bride_mother = make_person("bride_mother", bride_data.get("mother"), unit_id, entry_details, entry_notes)

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
