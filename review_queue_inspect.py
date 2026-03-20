import json
from pathlib import Path
from collections import defaultdict


QUEUE_FILE = Path("/app/data/review_queue.json")


def main():
    if not QUEUE_FILE.exists():
        print("Keine Review-Queue vorhanden.")
        return

    data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))

    print("=== REVIEW QUEUE ÜBERSICHT ===")
    print(f"Gesamt: {len(data)} Seiten\n")

    books = defaultdict(int)

    for item in data:
        path = item.get("source_image", "")
        parts = path.split("/books/")
        if len(parts) > 1:
            book_name = parts[1].split("/")[0]
        else:
            book_name = "unbekannt"

        books[book_name] += 1

    print("Nach Büchern:\n")

    for book, count in sorted(books.items()):
        print(f"{book}: {count} Seiten")


if __name__ == "__main__":
    main()
