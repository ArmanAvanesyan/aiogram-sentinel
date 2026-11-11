"""Check preserved Git objects, source ancestry and working-document evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/monorepo-migration"


def verify(*, historical_objects: bool = False) -> None:
    for row in json.loads((REPORT / "history-map.json").read_text()):
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", row["source_head"], "HEAD"], cwd=ROOT, check=True
        )
    for row in json.loads((REPORT / "refs-map.json").read_text()) if historical_objects else []:
        # Historical refs can be absent from shallow checkouts, but source objects
        # must remain retrievable by the recorded original identity.
        subprocess.run(["git", "cat-file", "-e", row["object_id"]], cwd=ROOT, check=True)
    for row in json.loads((REPORT / "preserved-kit-working-copy.json").read_text()):
        path = ROOT / "packages/aiogram-kit" / row["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Preserved Kit working document differs: {row['path']}")
    print("Original histories, referenced objects and Kit working documents verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--historical-objects",
        action="store_true",
        help="Require every preserved branch/tag object; run after history-ref publication",
    )
    verify(historical_objects=parser.parse_args().historical_objects)
