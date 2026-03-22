import json
import os
import re
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


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_name_text(raw_name: Optional[str]) -> Optional[str]:
    raw_name = safe_str(raw_name)
    if not raw_name:
        return None

    cleaned = normalize_whitespace(raw_name)
    cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
    cleaned = normalize_whitespace(cleaned)

    return cleaned or None


def infer_status_from_text(text: str, role: str) -> Optional[str]:
    t = (text or "").lower()

    if "viduus" in t or "witwer" in t:
        return "witwer"
    if "vidua" in t or "witwe" in t:
        return "witwe"
    if "virgo" in t or "ledig" in t:
        return "ledig"
    if "adolescens" in t and role in {"groom", "bridegroom", "braeutigam"}:
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


def infer_flags_from_text(text: str) -> List[str]:
    flags: List[str] = []
    t = (text or "").lower()

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


def build_full_name_from_name(name: Optional[str]) -> Optional[str]:
    cleaned = clean_name_text(name)
    return cleaned or None


def normalize_role(role: Optional[str]) -> str:
    role_text = (safe_str(role) or "").lower()

    role_map = {
        "kind": "child",
        "kindesvater": "father",
        "vater": "father",
        "mutter": "mother",
        "pate": "godparent",
        "patin": "godparent",
        "taufpate": "godparent",
        "taufpatin": "godparent",
        "braeutigam": "groom",
        "bräutigam": "groom",
        "groom": "groom",
        "braut": "bride",
        "bride": "bride",
        "zeugen": "witness",
        "zeuge": "witness",
        "zeugin": "witness",
        "pfarrer": "priest",
        "priester": "priest",
        "verstorbener": "deceased",
        "verstorbene": "deceased",
        "toter": "deceased",
        "tote": "deceased",
    }

    return role_map.get(role_text, role_text or "related_person")


def make_person(
    role: str,
    person_data: Optional[Dict[str, Any]],
    unit_id: str,
    event_type: str,
    notes_texts: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(person_data, dict):
        return None

    name = safe_str(person_data.get("name"))
    if not name:
        return None

    person_id = f"{unit_id}_person_{role}"
    notes_texts = notes_texts or []

    details_text = safe_str(person_data.get("details")) or ""
    inferred_status = infer_status_from_text(details_text, role)
    inferred_residence = infer_residence_from_text(details_text)

    flags: List[str] = []
    for source_text in [details_text] + notes_texts:
        for flag in infer_flags_from_text(source_text):
            if flag not in flags:
                flags.append(flag)

    attributes = {
        "status": safe_str(person_data.get("status")) or inferred_status,
        "occupation": safe_str(person_data.get("occupation")),
        "residence": safe_str(person_data.get("residence")) or inferred_residence,
        "birth_place": safe_str(person_data.get("birth_place")),
        "details_text": details_text or None,
        "confidence": person_data.get("confidence"),
        "event_type_context": event_type,
    }

    clean_attributes = {}
    for key, value in attributes.items():
        if value is not None:
            clean_attributes[key] = value

    person = {
        "person_id": person_id,
        "role": normalize_role(role),
        "full_name": build_full_name_from_name(name),
        "given_name": safe_str(person_data.get("given_name")),
        "surname": safe_str(person_data.get("surname")),
        "name_original": name,
        "sex": safe_str(person_data.get("sex")),
        "attributes": clean_attributes,
        "flags": flags,
        "raw": person_data,
    }

    return person


def normalize_persons_list(entry: Dict[str, Any], unit_id: str, event_type: str) -> List[Dict[str, Any]]:
    persons: List[Dict[str, Any]] = []
    raw_persons = safe_list(entry.get("persons"))
    notes_texts = [str(x) for x in safe_list(entry.get("notes")) if x is not None]
    seen_ids = set()

    for index, person_data in enumerate(raw_persons, start=1):
        if isinstance(person_data, str):
            person_data = {
                "role": f"related_person_{index}",
                "name": person_data,
            }

        if not isinstance(person_data, dict):
            continue

        role = safe_str(person_data.get("role")) or f"related_person_{index}"
        person = make_person(role, person_data, unit_id, event_type, notes_texts)
        if not person:
            continue

        person_id = person.get("person_id")
        if person_id in seen_ids:
            continue

        seen_ids.add(person_id)
        persons.append(person)

    return persons


def extract_relationships(entry: Dict[str, Any], unit_id: str, persons: List[Dict[str, Any]], event_type: str) -> List[Dict[str, Any]]:
    relationships: List[Dict[str, Any]] = []

    role_to_ids: Dict[str, List[str]] = {}
    for person in persons:
        role = person.get("role") or ""
        role_to_ids.setdefault(role, []).append(person["person_id"])

    event_type_lower = (event_type or "").lower()

    if event_type_lower in {"trauung", "marriage"}:
        groom_ids = role_to_ids.get("groom", [])
        bride_ids = role_to_ids.get("bride", [])
        if groom_ids and bride_ids:
            relationships.append({
                "type": "spouse",
                "person1_id": groom_ids[0],
                "person2_id": bride_ids[0],
            })

    if event_type_lower in {"taufe", "baptism", "geburt"}:
        child_ids = role_to_ids.get("child", [])
        father_ids = role_to_ids.get("father", [])
        mother_ids = role_to_ids.get("mother", [])

        if child_ids:
            child_id = child_ids[0]
            if father_ids:
                relationships.append({
                    "type": "child_of",
                    "child_id": child_id,
                    "parent_id": father_ids[0],
                })
            if mother_ids:
                relationships.append({
                    "type": "child_of",
                    "child_id": child_id,
                    "parent_id": mother_ids[0],
                })

    return relationships


def extract_event(entry: Dict[str, Any], unit_id: str) -> Dict[str, Any]:
    places = safe_list(entry.get("places"))
    place = None

    for value in places:
        value_str = safe_str(value)
        if value_str:
            place = value_str
            break

    return {
        "event_id": f"{unit_id}_event_1",
        "type": safe_str(entry.get("event_type")) or "Unklar",
        "date_text": safe_str(entry.get("date_text")),
        "language": safe_str(entry.get("language")),
        "place": place,
        "page_type": safe_str(entry.get("page_type")),
        "is_header_or_meta": bool(entry.get("is_header_or_meta", False)),
    }


def build_family_unit(entry: Dict[str, Any], source_path: str, entry_index: int, source_image: Optional[str]) -> Optional[Dict[str, Any]]:
    if bool(entry.get("is_header_or_meta", False)):
        return None

    short_uuid = uuid.uuid4().hex[:8]
    unit_id = f"fu_{entry_index:04d}_{short_uuid}"

    event_type = safe_str(entry.get("event_type")) or "Unklar"
    persons = normalize_persons_list(entry, unit_id, event_type)
    relationships = extract_relationships(entry, unit_id, persons, event_type)

    family_unit = {
        "unit_id": unit_id,
        "source": {
            "source_file": source_path,
            "source_image": source_image,
            "entry_index": entry_index,
            "entry_label": safe_str(entry.get("entry_label")),
        },
        "event": extract_event(entry, unit_id),
        "persons": persons,
        "relationships": relationships,
        "summary": safe_str(entry.get("source_text_summary_german")),
        "genealogical_notes": safe_str(entry.get("genealogical_notes_german")),
        "uncertainties": [safe_str(x) for x in safe_list(entry.get("unsicherheiten")) if safe_str(x)],
        "notes": [safe_str(x) for x in safe_list(entry.get("notes")) if safe_str(x)],
        "raw_text": safe_str(entry.get("raw_text")),
        "confidence": entry.get("confidence", 0.0),
        "review_status": "unreviewed",
        "raw_entry": entry,
    }

    return family_unit


def convert_page_to_family_units(data: Dict[str, Any], source_path: str) -> Dict[str, Any]:
    entries = data.get("entries", [])
    family_units: List[Dict[str, Any]] = []
    source_image = safe_str(data.get("source_image"))

    if not isinstance(entries, list):
        entries = []

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue

        family_unit = build_family_unit(entry, source_path, index, source_image)
        if family_unit is not None:
            family_units.append(family_unit)

    result = {
        "source_image": source_image,
        "source_file": source_path,
        "page_type": safe_str(data.get("page_type")),
        "event_types_on_page": safe_list(data.get("event_types_on_page")),
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
