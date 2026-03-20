import json
import shutil
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


def find_selected_item(queue: list) -> dict | None:
    for item in queue:
        if item.get("status") == "selected_for_review":
            return item
    return None


def build_export_name(source_image: Path) -> str:
    book_name = source_image.parent.name
    return f"{book_name}__{source_image.name}"


def prepare_chatgpt_package() -> dict:
    queue = load_queue()
    selected = find_selected_item(queue)

    if selected is None:
        return {"status": "no_selected_item"}

    source_image = Path(selected["source_image"])
    if not source_image.exists():
        return {
            "status": "source_missing",
            "source_image": str(source_image),
        }

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    export_base = build_export_name(source_image)
    export_image = EXPORT_DIR / export_base
    export_json = EXPORT_DIR / f"{source_image.stem}_chatgpt_request.json"

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
                "strukturierte Ausgabe erzeugen"
            ],
        },
        "reason": selected.get("reason", {}),
    }

    export_json.write_text(
        json.dumps(request_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    for item in queue:
        if item.get("source_image") == str(source_image):
            item["status"] = "prepared_for_chatgpt"
            item["prepared_at"] = now_iso()

    save_queue(queue)

    return {
        "status": "prepared",
        "source_image": str(source_image),
        "export_image": str(export_image),
        "export_json": str(export_json),
    }


def main():
    result = prepare_chatgpt_package()

    print("=== CHATGPT-VORBEREITUNG ===")
    print("Status:")
    print(result.get("status"))

    if result.get("source_image"):
        print("Quelle:")
        print(result["source_image"])

    if result.get("export_image"):
        print("Kopiertes Bild:")
        print(result["export_image"])

    if result.get("export_json"):
        print("Info-Datei:")
        print(result["export_json"])


if __name__ == "__main__":
    main()
