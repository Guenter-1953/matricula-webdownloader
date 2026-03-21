import os
import sys

from build_family_units_for_book import build_book_family_units
from build_merge_candidates import build_merge_candidates
from build_person_index import build_person_index
from build_person_name_stats import build_person_name_stats
from family_units import save_json


def main() -> None:
    if len(sys.argv) != 2:
        print("Verwendung:")
        print("python run_family_unit_pipeline.py /app/data/books/BUCHNAME")
        sys.exit(1)

    book_dir = sys.argv[1]

    if not os.path.isdir(book_dir):
        print(f"Buchordner nicht gefunden: {book_dir}")
        sys.exit(1)

    print("=== FAMILY UNIT PIPELINE ===")
    print("Buch:")
    print(book_dir)

    book_result = build_book_family_units(book_dir)
    family_units_book_path = os.path.join(book_dir, "family_units_book.json")
    save_json(family_units_book_path, book_result)

    print("")
    print("1) family_units_book.json geschrieben:")
    print(family_units_book_path)
    print("Seiten:")
    print(book_result["pages_count"])
    print("Family Units gesamt:")
    print(book_result["total_family_units_count"])

    person_index_result = build_person_index(book_result)
    persons_index_path = os.path.join(book_dir, "persons_from_family_units.json")
    save_json(persons_index_path, person_index_result)

    print("")
    print("2) persons_from_family_units.json geschrieben:")
    print(persons_index_path)
    print("Personen:")
    print(person_index_result["persons_count"])

    person_name_stats_result = build_person_name_stats(person_index_result)
    person_name_stats_path = os.path.join(book_dir, "person_name_stats.json")
    save_json(person_name_stats_path, person_name_stats_result)

    print("")
    print("3) person_name_stats.json geschrieben:")
    print(person_name_stats_path)
    print("Eindeutige full_name:")
    print(person_name_stats_result["unique_full_names_count"])
    print("Eindeutige name_original:")
    print(person_name_stats_result["unique_original_names_count"])
    print("Ohne Namen:")
    print(person_name_stats_result["missing_name_count"])

    merge_candidates_result = build_merge_candidates(person_index_result)
    merge_candidates_path = os.path.join(book_dir, "merge_candidates.json")
    save_json(merge_candidates_path, merge_candidates_result)

    print("")
    print("4) merge_candidates.json geschrieben:")
    print(merge_candidates_path)
    print("Kandidatengruppen:")
    print(merge_candidates_result["merge_candidate_group_count"])

    print("")
    print("=== PIPELINE FERTIG ===")


if __name__ == "__main__":
    main()
