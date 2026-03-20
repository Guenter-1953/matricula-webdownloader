import json
import sys
from pathlib import Path


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def gedcom_escape(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("\n", " ").replace("\r", " ").strip()


def split_display_name(display_name: str):
    parts = gedcom_escape(display_name).split()
    if not parts:
        return "", ""

    if len(parts) == 1:
        return parts[0], ""

    given = " ".join(parts[:-1])
    surname = parts[-1]
    return given, surname


def build_gedcom(graph: dict) -> str:
    persons = graph.get("persons", [])
    families = graph.get("families", [])

    lines = []
    lines.append("0 HEAD")
    lines.append("1 SOUR ChatGPT-Ahnenprojekt")
    lines.append("1 GEDC")
    lines.append("2 VERS 5.5.1")
    lines.append("1 CHAR UTF-8")

    person_xref_map = {}
    family_xref_map = {}

    for idx, person in enumerate(persons, start=1):
        person_xref = f"@I{idx}@"
        person_xref_map[person.get("person_id", "")] = person_xref

    for idx, family in enumerate(families, start=1):
        family_xref = f"@F{idx}@"
        family_xref_map[family.get("family_id", "")] = family_xref

    for person in persons:
        person_id = person.get("person_id", "")
        xref = person_xref_map[person_id]
        display_name = person.get("display_name", "")
        given, surname = split_display_name(display_name)

        lines.append(f"0 {xref} INDI")
        if surname:
            lines.append(f"1 NAME {gedcom_escape(given)} /{gedcom_escape(surname)}/")
            lines.append(f"2 GIVN {gedcom_escape(given)}")
            lines.append(f"2 SURN {gedcom_escape(surname)}")
        else:
            lines.append(f"1 NAME {gedcom_escape(display_name)}")

        mentions = person.get("mentions", [])
        if mentions:
            first = mentions[0]
            date_text = gedcom_escape(first.get("date_text", ""))
            event_type = gedcom_escape(first.get("event_type", ""))
            page_id = gedcom_escape(first.get("page_id", ""))

            if event_type:
                lines.append("1 EVEN")
                lines.append(f"2 TYPE {event_type}")
                if date_text:
                    lines.append(f"2 DATE {date_text}")
                if page_id:
                    lines.append(f"2 NOTE Erste Erwähnung auf {page_id}")

    for family in families:
        family_id = family.get("family_id", "")
        xref = family_xref_map[family_id]

        groom_person_id = family.get("groom_person_id", "")
        bride_person_id = family.get("bride_person_id", "")

        groom_xref = person_xref_map.get(groom_person_id, "")
        bride_xref = person_xref_map.get(bride_person_id, "")

        lines.append(f"0 {xref} FAM")

        if groom_xref:
            lines.append(f"1 HUSB {groom_xref}")
        if bride_xref:
            lines.append(f"1 WIFE {bride_xref}")

        lines.append("1 MARR")

        date_text = gedcom_escape(family.get("date_text", ""))
        if date_text:
            lines.append(f"2 DATE {date_text}")

        places = family.get("places", [])
        if places:
            lines.append(f"2 PLAC {gedcom_escape(', '.join(places))}")

        summary = gedcom_escape(family.get("summary", ""))
        notes = gedcom_escape(family.get("notes", ""))
        source_image = gedcom_escape(family.get("source_image", ""))

        if summary:
            lines.append(f"1 NOTE {summary}")
        if notes:
            lines.append(f"1 NOTE {notes}")
        if source_image:
            lines.append(f"1 NOTE Quelle: {source_image}")

    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: python export_gedcom.py path_to_family_graph.json")
        return

    json_path = Path(sys.argv[1])
    graph = load_json(json_path)

    if not isinstance(graph, dict):
        raise ValueError("family_graph.json muss ein Objekt sein.")

    gedcom_text = build_gedcom(graph)

    output_path = json_path.parent / "family_graph.ged"
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(gedcom_text)

    print("GEDCOM exportiert:")
    print(output_path)


if __name__ == "__main__":
    main()
