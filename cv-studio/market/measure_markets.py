"""Build market playbooks from a CV archive, or check one CV against them.

    python3 measure_markets.py build  <corpus_dir> [--out playbooks.json]
    python3 measure_markets.py check  <cv.txt> --market BE --position accounting [--playbooks playbooks.json]
    python3 measure_markets.py demo                 # runs on an invented corpus

Corpus layout: <corpus_dir>/<MARKET>/<position>/*.txt|.md|.docx, optional outcomes.csv.
PDFs must be converted to text first (Bullhorn's parsed resume text works too).
Never commit a real corpus or its playbooks' examples: CVs are personal data.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cvcorpus import build_playbooks, check_cv, load_corpus, load_seeds, read_text  # noqa: E402
from synthetic import write_corpus  # noqa: E402

SEEDS = HERE / "seed_playbooks.json"


def dump(books: dict, out: Path) -> None:
    out.write_text(json.dumps({"playbooks": list(books.values())}, ensure_ascii=False, indent=1), encoding="utf-8")


def summary(book: dict) -> str:
    lines = [f"\n== {book['label']}  ({book['cvs']} CVs, confidence {book['confidence']})"]
    if book.get("cv_languages"):
        lines.append("   CV language: " + ", ".join(f"{l} {int(s * 100)}%" for l, s in book["cv_languages"].items()))
    for c in book.get("conventions", []):
        if "share" in c:
            else_ = f"  (other markets {int(c['elsewhere'] * 100)}%)" if c.get("elsewhere") is not None else ""
            lines.append(f"   {int(c['share'] * 100):3d}%  {c['label']}{else_}")
    for lang, rows in book.get("market_specific", {}).items():
        if isinstance(rows, list) and rows:
            lines.append(f"   distinctive vs other markets [{lang}]: " + ", ".join(r["term"] for r in rows[:8]))
    pd = book.get("personal_data")
    if pd:
        lines.append("   personal data in CVs: " + ", ".join(f"{k.replace('_', ' ')} {int(v * 100)}%" for k, v in pd.items() if v))
    ww = book.get("what_wins", {})
    if ww.get("verdict") == "measured":
        lines.append(f"   interviews: {int(ww['base_rate'] * 100)}% of {ww['won'] + ww['lost']} CVs with an outcome")
        for c in ww.get("conventions", []):
            lines.append(f"     {c['label']}: {int(c['interview_rate_with'] * 100)}% with vs {int(c['interview_rate_without'] * 100)}% without  -> {c['verdict']}")
        terms_ = ", ".join(r["term"] for r in ww["terms_that_win"][:6])
        lines.append("   words more common in CVs that got an interview: " + (terms_ or "none clear yet"))
    elif ww:
        lines.append(f"   what wins: {ww['verdict']} ({ww['reason']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("corpus"); b.add_argument("--out", default="playbooks.json")
    c = sub.add_parser("check"); c.add_argument("cv"); c.add_argument("--market", required=True); c.add_argument("--position", required=True)
    c.add_argument("--playbooks", default=None)
    sub.add_parser("demo")
    a = ap.parse_args(argv)
    seeds = load_seeds(SEEDS)

    if a.cmd in {"build", "demo"}:
        corpus = Path(a.corpus) if a.cmd == "build" else write_corpus(Path(tempfile.mkdtemp()) / "corpus")
        books = build_playbooks(load_corpus(corpus), seeds)
        for book in books.values():
            print(summary(book))
        if a.cmd == "build":
            dump(books, Path(a.out))
            print(f"\nwrote {a.out}")
        else:
            print("\n(demo corpus is invented; the numbers show the method, not the market)")
        return 0

    key = (a.market.upper(), a.position.lower())
    if a.playbooks:
        books = {(p["market"], p["position"]): p for p in json.loads(Path(a.playbooks).read_text(encoding="utf-8"))["playbooks"]}
    else:
        books = build_playbooks([], seeds)
    if key not in books:
        print(f"no playbook for {key[0]} {key[1]}")
        return 1
    for issue in check_cv(read_text(Path(a.cv)), books[key], seeds.get(key)) or [{"kind": "ok", "what": "nothing to flag", "basis": ""}]:
        print(f"- [{issue['kind']}] {issue['what']}: {issue['basis']}" + (f"  ({issue['why']})" if issue.get("why") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
