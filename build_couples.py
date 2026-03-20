import json
import sys
import os


def load_events(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name):
    return name.strip().lower()


def build_couples(events):
    couples = []

    for event in events:
        persons = event.get("persons", [])

        if len(persons) < 2:
            continue  # keine Trauung oder unvollständig

        # einfache Logik: erstes Paar nehmen
        p1 = persons[0]
        p2 = persons[1]

        couple = {
            "event_id": event.get("event_id"),
            "page_id": event.get("page_id"),
            "event_type": event.get("event_type"),
            "date_text": event.get("date_text"),
            "partner_1": p1,
            "partner_2": p2,
            "confidence": event.get("confidence", 0.0),
        }

        couples.append(couple)

    return couples


def save_couples(couples, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(couples, f, indent=2, ensure_ascii=False)


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_couples.py <event_index.json>")
        return

    input_file = sys.argv[1]

    events = load_events(input_file)
    couples = build_couples(events)

    output_file = os.path.join(os.path.dirname(input_file), "couples.json")
    save_couples(couples, output_file)

    print(f"{len(couples)} Paare gespeichert in:")
    print(output_file)


if __name__ == "__main__":
    main()
