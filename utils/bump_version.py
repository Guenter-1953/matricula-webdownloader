import json
import re
from pathlib import Path
from datetime import datetime


VERSION_FILE = Path("version.json")


def load_version_data() -> dict:
    if VERSION_FILE.exists():
        try:
            return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    return {
        "version": "v1.1.0",
        "date": datetime.now().date().isoformat(),
    }


def bump_patch(version: str) -> str:
    version = str(version or "").strip()

    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return "v1.1.0"

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) + 1

    return f"v{major}.{minor}.{patch}"


def main():
    data = load_version_data()

    old_version = data.get("version", "v1.1.0")
    new_version = bump_patch(old_version)
    today = datetime.now().date().isoformat()

    new_data = {
        "version": new_version,
        "date": today,
    }

    VERSION_FILE.write_text(
        json.dumps(new_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Version erhöht: {old_version} -> {new_version}")
    print(f"Datum gesetzt: {today}")


if __name__ == "__main__":
    main()
