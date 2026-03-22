import json
import sys
from pathlib import Path
from datetime import datetime


QUEUE_FILE = Path("/app/data/review_queue.json")


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


def derive_page_id(image_path: str) -> str:
    return Path(image_path).stem


def derive_book_id(image_path: str) -> str:
    path = Path(image_path)
    if path.parent.name:
        return path.parent.name
    return ""


def normalize_questions(questions) -> list:
    if questions is None:
        return []
    if isinstance(questions, list):
        return questions
    return [questions]


def add_page(
    image_path: str,
    reason: dict | None = None,
    review_type: str = "page_review",
    priority: str = "normal",
    source_json: str = "",
    questions: list | None = None,
    decision: dict | None = None,
) -> dict:
    queue = load_queue()

    image_path = str(Path(image_path))
    page_id = derive_page_id(image_path)
    book_id = derive_book_id(image_path)
    questions = normalize_questions(questions)

    existing = next((item for item in queue if item.get("source_image") == image_path), None)

    if existing:
        existing["last_seen_at"] = now_iso()
        existing["page_id"] = page_id
        existing["book_id"] = book_id
        existing["review_type"] = review_type
        existing["priority"] = priority

        if reason is not None:
            existing["reason"] = reason

        if source_json:
            existing["source_json"] = source_json

        if questions:
            existing["questions"] = questions

        if decision is not None:
            existing["decision"] = decision

        result = {
            "status": "already_present",
            "item": existing,
        }
        save_queue(queue)
        return result

    item = {
        "source_image": image_path,
        "page_id": page_id,
        "book_id": book_id,
        "status": "pending_review",
        "review_type": review_type,
        "priority": priority,
        "created_at": now_iso(),
        "last_seen_at": now_iso(),
        "resolved_at": None,
        "reason": reason or {},
        "source_json": source_json,
        "questions": questions,
        "decision": decision or {},
    }

    queue.append(item)
    save_queue(queue)

    return {
        "status": "added",
        "item": item,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python review_queue.py /pfad/zur/seite.png")
        return

    image_path = sys.argv[1]

    result = add_page(image_path)

    print("Review-Queue aktualisiert.")
    print("Status:")
    print(result["status"])
    print("Datei:")
    print(result["item"]["source_image"])


if __name__ == "__main__":
    main()
