#!/usr/bin/env python3
"""Copy src/esendex_client.py into every skill's scripts/ folder.

Each skill ships its own copy so it works when installed on its own, but there is
one source. Edit src/esendex_client.py, never a copy, then:

    python3 sync_client.py            # rewrite the copies
    python3 sync_client.py --check    # exit 1 if any copy differs
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "src" / "esendex_client.py"
SKILLS = ROOT / "esendex-developer-kit" / "skills"


def copies():
    return [skill.parent / "scripts" / "esendex_client.py" for skill in sorted(SKILLS.glob("*/SKILL.md"))]


def main(check):
    source = SOURCE.read_bytes()
    stale = [c for c in copies() if not c.exists() or c.read_bytes() != source]
    if check:
        for c in stale:
            print(f"out of date: {c.relative_to(ROOT)}")
        if stale:
            print("Edit src/esendex_client.py, then run python3 sync_client.py")
        return 1 if stale else 0
    for c in stale:
        c.parent.mkdir(exist_ok=True)
        c.write_bytes(source)
        print(f"updated: {c.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv[1:]))
