import json
import os
import sys
from typing import Any, Dict, List

from family_units import convert_page_to_family_units


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_chatgpt_result_files(entry_debug_dir: str) -> List[str]:
    result_files: List[str] = []

    if not os.path.isdir(entry_debug_dir):
        return result_files

    for name in sorted(os.listdir(entry_debug_dir)):
        if not name.endswith("_chatgpt_result.json"):
            continue
        result_files.append(os.path.join(entry_debug_dir, name))

    return result_files


def build_book_family_units(book_dir: str) -> Dict[str, Any]:
    entry_debug_dir = os.path.join(book_dir, "entry_debug")
    result_files = find_chatgpt_result_files(entry_debug_dir)

    pages: List[Dict[str, Any]] = []
    total_family_units = 0

    for result_file in result_files:
        data = load_json(result_file)
        converted = convert_page_to_family_units(data, result_file)

        page_record = {
            "source_file": result_file,
            "source_image": converted.get("source_image"),
            "family_units_count": converted.get("family_units_count", 0),
            "family_units": converted.get("family_units", []),
        }

        pages.append(page_record)
        total_family_units += page_record["family_units_count"]

    return {
        "book_dir": book_dir,
        "entry_debug_dir": entry_debug_dir,
        "pages_count": len(pages),
        "total_family_units_count": total_family_units,
        "pages": pages,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python build_family_units_for_book.py /app/data/books/BUCHNAME")
        sys.exit(1)

    book_dir = sys.argv[1]

    if not os.path.isdir(book_dir):
        print(f"Buchordner nicht gefunden: {book_dir}")
        sys.exit(1)

    result = build_book_family_units(book_dir)

    output_path = os.path.join(book_dir, "family_units_book.json")
    save_json(output_path, result)

    print("=== BUILD FAMILY UNITS FOR BOOK ===")
    print("Buch:")
    print(book_dir)
    print("Ziel:")
    print(output_path)
    print("Seiten:")
    print(result["pages_count"])
    print("Family Units gesamt:")
    print(result["total_family_units_count"])


if __name__ == "__main__":
    main()
