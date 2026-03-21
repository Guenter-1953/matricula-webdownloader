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


def _normalize_review_question(question: dict) -> dict:
    return {
        "field": question.get("field"),
        "confidence": question.get("confidence"),
        "reason": question.get("reason"),
        "question": question.get("question"),
        "excerpt": question.get("excerpt"),
        "current_reading": question.get("current_reading"),
        "alternatives": question.get("alternatives", []) or [],
    }


def extract_analysis_block(item: dict) -> dict:
    """
    Holt die neue Analyse-Struktur aus dem Queue-Eintrag, wenn sie dort
    bereits vorhanden ist.

    Unterstützt zwei Formen:
    1. item["analysis"] = {...}
    2. flache Felder direkt im Queue-Eintrag
    """
    analysis = item.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}

    raw_text = analysis.get("raw_text", item.get("ocr_text", ""))
    analysis_text = analysis.get("analysis_text", item.get("cleaned_ocr_text", ""))
    page_kind = analysis.get("page_kind", item.get("page_kind", "unknown"))
    page_kind_confidence = analysis.get(
        "page_kind_confidence",
        item.get("page_kind_confidence", "offen"),
    )

    review_questions_raw = analysis.get("review_questions")
    if not isinstance(review_questions_raw, list):
        review_questions_raw = item.get("review_questions", []) or []

    review_questions = [
        _normalize_review_question(question)
        for question in review_questions_raw
        if isinstance(question, dict)
    ]

    notes = analysis.get("notes")
    if not isinstance(notes, list):
        notes = item.get("notes", []) or []

    warnings = analysis.get("warnings")
    if not isinstance(warnings, list):
        warnings = item.get("warnings", []) or []

    model_version = analysis.get("model_version", item.get("model_version"))
    created_at = analysis.get("created_at", item.get("analysis_created_at"))

    return {
        "raw_text": raw_text or "",
        "analysis_text": analysis_text or "",
        "page_kind": page_kind or "unknown",
        "page_kind_confidence": page_kind_confidence or "offen",
        "review_questions": review_questions,
        "notes": [str(entry).strip() for entry in notes if str(entry).strip()],
        "warnings": [str(entry).strip() for entry in warnings if str(entry).strip()],
        "model_version": model_version,
        "created_at": created_at,
    }


def build_task_instructions() -> list[str]:
    return [
        "Seite vollständig lesen",
        "alle Einträge erkennen",
        "Rohtext und bereinigte Lesung unterscheiden",
        "Namen, Daten, Orte, Berufe, Eltern, Zeugen, Randvermerke erfassen",
        "Unsicherheiten ausdrücklich benennen",
        "mögliche Alternativen notieren",
        "konkrete review_questions formulieren, wenn Namen, Orte oder Daten unsicher sind",
        "Latein nach Möglichkeit auf Deutsch wiedergeben",
        "strukturierte Ausgabe erzeugen",
    ]


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

    analysis_block = extract_analysis_block(item)

    request_payload = {
        "prepared_at": now_iso(),
        "source_image": str(source_image),
        "copied_image": str(export_image),
        "book_name": source_image.parent.name,
        "page_id": source_image.stem,
        "task": {
            "mode": "manual_chatgpt_review",
            "instructions": build_task_instructions(),
        },
        "page_analysis_context": analysis_block,
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
        "review_question_count": len(analysis_block.get("review_questions", [])),
        "page_kind": analysis_block.get("page_kind", "unknown"),
        "page_kind_confidence": analysis_block.get("page_kind_confidence", "offen"),
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

            if entry.get("page_kind"):
                print("Seitentyp:")
                print(entry.get("page_kind"))

            if entry.get("page_kind_confidence"):
                print("Seitentyp-Sicherheit:")
                print(entry.get("page_kind_confidence"))

            if "review_question_count" in entry:
                print("Review-Fragen:")
                print(entry.get("review_question_count"))


if __name__ == "__main__":
    main()
