import json
import shutil
import sys
from pathlib import Path
from datetime import datetime


QUEUE_FILE = Path("/app/data/review_queue.json")
EXPORT_DIR = Path("/app/data/chatgpt_review")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []

    try:
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_queue(queue: list) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def get_book_name_from_item(item: dict) -> str | None:
    source_image = item.get("source_image")
    if not source_image:
        return None
    try:
        return Path(source_image).parent.name
    except Exception:
        return None


def find_selected_items(queue: list, limit: int, book_name: str | None = None) -> list:
    selected = []

    for item in queue:
        if item.get("status") != "selected_for_review":
            continue

        item_book_name = get_book_name_from_item(item)
        if book_name and item_book_name != book_name:
            continue

        selected.append(item)

        if len(selected) >= limit:
            break

    return selected


def build_export_base(source_image: Path) -> str:
    book_name = source_image.parent.name
    return f"{book_name}__{source_image.stem}"


def prepare_one_item(item: dict) -> dict:
    source_image = Path(item["source_image"])

    if not source_image.exists():
        return {
            "status": "source_missing",
            "source_image": str(source_image),
        }

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    export_base = build_export_base(source_image)
    export_image = EXPORT_DIR / f"{export_base}{source_image.suffix}"
    export_json = EXPORT_DIR / f"{export_base}_chatgpt_request.json"

    shutil.copy2(source_image, export_image)

    request_payload = {
        "prepared_at": now_iso(),
        "source_image": str(source_image),
        "copied_image": str(export_image),
        "book_name": source_image.parent.name,
        "page_id": source_image.stem,
        "task": {
            "mode": "manual_chatgpt_review",
            "instructions": [
                "Seite vollständig lesen",
                "alle Einträge erkennen",
                "Namen, Daten, Orte, Berufe, Eltern, Zeugen, Randvermerke erfassen",
                "Latein nach Möglichkeit auf Deutsch wiedergeben",
                "strukturierte Ausgabe erzeugen",
            ],
        },
        "reason": item.get("reason", {}),
    }

    export_json.write_text(
        json.dumps(request_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    item["status"] = "prepared_for_chatgpt"
    item["prepared_at"] = now_iso()
    item["chatgpt_export_image"] = str(export_image)
    item["chatgpt_export_json"] = str(export_json)

    return {
        "status": "prepared",
        "source_image": str(source_image),
        "export_image": str(export_image),
        "export_json": str(export_json),
        "book_name": source_image.parent.name,
        "page_id": source_image.stem,
    }


def prepare_chatgpt_packages(limit: int = 15, book_name: str | None = None) -> dict:
    queue = load_queue()
    selected_items = find_selected_items(queue, limit=limit, book_name=book_name)

    if not selected_items:
        return {
            "status": "no_selected_items",
            "requested_limit": limit,
            "book_name": book_name,
            "prepared_count": 0,
            "results": [],
        }

    results = []

    for item in selected_items:
        result = prepare_one_item(item)
        results.append(result)

    save_queue(queue)

    prepared_count = sum(1 for r in results if r.get("status") == "prepared")
    missing_count = sum(1 for r in results if r.get("status") == "source_missing")

    return {
        "status": "prepared_batch",
        "requested_limit": limit,
        "book_name": book_name,
        "selected_count": len(selected_items),
        "prepared_count": prepared_count,
        "missing_count": missing_count,
        "results": results,
    }


def main():
    limit = 15
    book_name = None

    if len(sys.argv) >= 2:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print("Fehler: erstes Argument muss eine Zahl sein, z. B. 15")
            sys.exit(1)

    if len(sys.argv) >= 3:
        book_name = sys.argv[2]

    result = prepare_chatgpt_packages(limit=limit, book_name=book_name)

    print("=== CHATGPT-VORBEREITUNG ===")
    print("Status:")
    print(result.get("status"))
    print("Angeforderte Anzahl:")
    print(result.get("requested_limit"))

    if result.get("book_name"):
        print("Buchfilter:")
        print(result.get("book_name"))

    if "selected_count" in result:
        print("Gefundene ausgewählte Seiten:")
        print(result.get("selected_count"))

    print("Vorbereitet:")
    print(result.get("prepared_count", 0))

    if "missing_count" in result:
        print("Fehlende Quelldateien:")
        print(result.get("missing_count"))

    if result.get("results"):
        print("")
        print("Details:")
        for entry in result["results"]:
            print("---")
            print("Status:")
            print(entry.get("status"))

            if entry.get("book_name"):
                print("Buch:")
                print(entry.get("book_name"))

            if entry.get("page_id"):
                print("Seite:")
                print(entry.get("page_id"))

            if entry.get("source_image"):
                print("Quelle:")
                print(entry.get("source_image"))

            if entry.get("export_image"):
                print("Kopiertes Bild:")
                print(entry.get("export_image"))

            if entry.get("export_json"):
                print("Info-Datei:")
                print(entry.get("export_json"))


if __name__ == "__main__":
    main()
