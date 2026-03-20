import json
import sys
from pathlib import Path


QUEUE_FILE = Path("/app/data/review_queue.json")


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


def pick_item(index: int = 0) -> dict | None:
    queue = load_queue()

    pending_items = [
        item for item in queue
        if item.get("status") == "pending_review"
    ]

    if not pending_items:
        return None

    if index < 0 or index >= len(pending_items):
        return None

    selected = pending_items[index]
    selected_path = selected.get("source_image")

    for item in queue:
        if item.get("source_image") == selected_path:
            item["status"] = "selected_for_review"

    save_queue(queue)
    return selected


def main():
    index = 0

    if len(sys.argv) > 1:
        try:
            index = int(sys.argv[1])
        except Exception:
            print("Index muss eine Zahl sein.")
            return

    item = pick_item(index)

    if item is None:
        print("Kein passender Queue-Eintrag gefunden.")
        return

    print("=== AUSGEWÄHLTE REVIEW-SEITE ===")
    print(f"Quelle: {item.get('source_image', '')}")
    print(f"Status: selected_for_review")
    print("Grund:")
    print(json.dumps(item.get("reason", {}), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
