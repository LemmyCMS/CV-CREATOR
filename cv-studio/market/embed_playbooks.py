"""Copy market playbooks into CV Studio so the generator follows them.

    python3 embed_playbooks.py                      # seed playbooks ([PRIOR] only)
    python3 embed_playbooks.py playbooks.json       # measured playbooks from measure_markets.py build

Only rules and aggregate shares are embedded, never CV text, so the page carries no
personal data.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cvcorpus import build_playbooks, load_seeds  # noqa: E402

STUDIO = HERE.parent / "zig_cv_studio.html"
KEEP = ("market", "position", "label", "cvs", "confidence", "notes", "vocabulary", "avoid", "credentials", "software", "conventions", "cv_languages")


def main(argv: list[str]) -> int:
    if argv:
        books = json.loads(Path(argv[0]).read_text(encoding="utf-8"))["playbooks"]
    else:
        books = list(build_playbooks([], load_seeds(HERE / "seed_playbooks.json")).values())
    slim = [{k: b[k] for k in KEEP if k in b} for b in books]
    for b in slim:  # aggregate shares only: drop anything that is not a rule or a number
        b["conventions"] = [{k: c[k] for k in ("key", "label", "why", "share", "elsewhere", "source") if k in c} for c in b.get("conventions", [])]
    payload = json.dumps({"playbooks": slim}, ensure_ascii=False).replace("</", "<\\/")
    html = STUDIO.read_text(encoding="utf-8")
    new, n = re.subn(r'(<script type="application/json" id="playbooks">).*?(</script>)', lambda m: m.group(1) + payload + m.group(2), html, flags=re.S)
    if n != 1:
        print("playbooks block not found in zig_cv_studio.html")
        return 1
    STUDIO.write_text(new, encoding="utf-8")
    print(f"embedded {len(slim)} playbooks into {STUDIO.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
