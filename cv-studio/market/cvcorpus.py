"""Learn how CVs are built per market and position, and check a CV against it.

Standard library only, like the rest of this repo: the proxy blocks pip and this has
to run wherever the CV archive lands.

Corpus layout (one folder per market, one per position family):

    corpus/BE/accounting/*.txt|.md|.docx
    corpus/LU/accounting/...
    corpus/BE/it-dev/...
    corpus/outcomes.csv          optional: file,outcome  (outcome: sent|interview|placed|rejected)

What it measures, per (market, position):

* which words and phrases the group uses far more than a fair comparison group.
  Two comparisons, never mixed:
    - market-specific: same position, same CV language, other markets
      (Belgian accounting CVs in French vs French and Luxembourg ones)
    - role-specific:   same market, same CV language, other positions
  Comparing within one language matters: otherwise "Dutch words" swamp every result.
* how often each seed convention appears (ITAA, "comptabilite de A a Z", fiduciaire...)
* section order, CV language mix, length, and personal data habits
* when outcomes exist: which terms appear more in CVs that got an interview

Every rate is shrunk toward the parent rate (Beta prior, strength PRIOR_K) and a term
only counts as distinctive at z >= Z_MIN with enough supporting documents. Groups with
few CVs are reported as low confidence rather than left out, and the outcome analysis
refuses to answer below MIN_OUTCOMES per side: "not yet known" is a verdict.

Never commit a real corpus: CVs are personal data under GDPR.
"""

from __future__ import annotations

import csv
import json
import math
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

PRIOR_K = 10.0        # prior strength, in documents
Z_MIN = 2.0           # distinctiveness threshold
MIN_DOCS = 3          # a term must appear in at least this many CVs of the group
MIN_PREVALENCE = 0.2  # ...and in at least this share of them
MIN_OUTCOMES = 10     # per side, before saying anything about what wins
CONVENTION_SHARE = 0.5

# ---------------------------------------------------------------- text handling

def fold(text: str) -> str:
    """Lowercase and strip accents, so 'Comptabilité' and 'comptabilite' match."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        text = re.sub(r"<[^>]+>", "", xml)
        return re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", text)))
    raise ValueError(f"unsupported file type: {path.name} (convert PDFs to .txt first)")


STOP = {
    "en": set("""a an the and or of to in on at for with by from as is are was were be been being this that these those
        it its i me my we our you your he she they them their his her not no yes but if so than then there here
        also into over under about after before during while per via up out all any each more most other some such
        can could will would should may might must do does did done have has had""".split()),
    "fr": set("""le la les un une des du de d l et ou a au aux en dans sur pour par avec sans sous chez que qui quoi
        dont ce cet cette ces son sa ses leur leurs mon ma mes notre nos votre vos je tu il elle nous vous ils elles
        est sont etait ete etre avoir ai as avons avez ont ne pas plus moins tres aussi comme mais si y se s n
        tout tous toute toutes""".split()),
    "nl": set("""de het een en of van in op aan voor met bij door naar als dat die dit deze is zijn was waren
        wordt worden werd heb hebben had ik je jij u hij zij ze wij we jullie hun haar mijn ons onze niet geen
        ook maar dan om te tot uit over onder na al er nog wel zo""".split()),
    "de": set("""der die das ein eine und oder von zu im in auf an fur mit bei durch nach als dass ist sind war
        waren wird werden ich du er sie wir ihr nicht kein auch aber dann um""".split()),
}
ALL_STOP = set().union(*STOP.values())
TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-/]*[a-z0-9+#]|[a-z0-9]")


def detect_language(text: str) -> str:
    words = TOKEN.findall(fold(text))
    scores = {lang: sum(1 for w in words if w in stops) for lang, stops in STOP.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 3 else "unknown"


def terms(text: str, max_n: int = 3) -> set[str]:
    """Distinct 1- to 3-word terms in a CV, ignoring stopwords at either edge."""
    out: set[str] = set()
    for line in fold(text).splitlines():
        toks = TOKEN.findall(line)
        for n in range(1, max_n + 1):
            for i in range(len(toks) - n + 1):
                gram = toks[i:i + n]
                if gram[0] in ALL_STOP or gram[-1] in ALL_STOP:
                    continue
                if n == 1 and (len(gram[0]) < 3 or gram[0].isdigit()):
                    continue
                if any(re.search(r"\d[/.\-]\d", t) for t in gram) or all(t.isdigit() for t in gram):
                    continue  # dates and phone fragments say nothing about a market
                out.add(" ".join(gram))
    return out


# Section headings, multilingual, mapped to one canonical name.
SECTIONS = {
    "profile":        ["profile", "profil", "summary", "about me", "resume", "a propos", "profiel", "over mij", "samenvatting"],
    "experience":     ["experience", "professional experience", "work history", "work experience", "experience professionnelle",
                       "experiences professionnelles", "parcours professionnel", "ervaring", "werkervaring", "beroepservaring"],
    "education":      ["education", "formation", "formations", "etudes", "opleiding", "opleidingen", "studies"],
    "skills":         ["skills", "competences", "vaardigheden", "competenties", "technical skills", "kennis"],
    "software":       ["software", "logiciels", "it skills", "informatique", "outils", "tools"],
    "certifications": ["certifications", "certificats", "certificaten", "attestations"],
    "languages":      ["languages", "langues", "talen", "talenkennis"],
    "interests":      ["interests", "hobbies", "centres d'interet", "loisirs", "interesses", "vrije tijd"],
    "personal":       ["personal details", "personal information", "informations personnelles", "donnees personnelles",
                       "persoonlijke gegevens", "etat civil"],
    "references":     ["references", "referenties"],
}
_HEADING = {alias: canon for canon, aliases in SECTIONS.items() for alias in aliases}


def sections(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        clean = fold(line).strip().strip(":").strip()
        clean = re.sub(r"^[#*\-\s]+|[#*\s]+$", "", clean)
        if 2 < len(clean) < 40 and clean in _HEADING and _HEADING[clean] not in found:
            found.append(_HEADING[clean])
    return found


# Personal details that appear in some markets' CVs. The Zig removes all of these from
# client-facing documents; measuring them tells the anonymiser what to expect.
PERSONAL = {
    "date_of_birth":  r"\b(date de naissance|ne\(e\) le|nee? le|geboortedatum|geboren op|date of birth|born on|geburtsdatum)\b",
    "nationality":    r"\b(nationalite|nationaliteit|nationality|staatsangehorigkeit)\b",
    "marital_status": r"\b(etat civil|marie\(e\)|celibataire|burgerlijke staat|gehuwd|ongehuwd|marital status|married|single)\b",
    "driving_licence": r"\b(permis b|permis de conduire|rijbewijs b?|driving licen[cs]e|fuhrerschein)\b",
    "photo":          r"\b(photo|foto|picture)\b",
}


PERSONAL_WORDS = {"naissance", "date", "geboortedatum", "geboren", "birth", "born", "nationalite", "nationaliteit", "nationality",
                  "civil", "marie", "celibataire", "gehuwd", "permis", "rijbewijs", "licence", "license", "photo", "foto"}


# ---------------------------------------------------------------- the corpus

@dataclass
class Doc:
    path: str
    market: str
    position: str
    language: str
    terms: set[str]
    folded: str
    sections: list[str]
    words: int
    outcome: str | None = None


def load_corpus(root: Path) -> list[Doc]:
    root = Path(root)
    outcomes: dict[str, str] = {}
    oc = root / "outcomes.csv"
    if oc.exists():
        with oc.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                outcomes[row["file"].strip()] = row["outcome"].strip().lower()
    docs: list[Doc] = []
    for path in sorted(root.glob("*/*/*")):
        if path.suffix.lower() not in {".txt", ".md", ".docx"}:
            continue
        market, position = path.parent.parent.name, path.parent.name
        text = read_text(path)
        rel = str(path.relative_to(root))
        docs.append(Doc(
            path=rel, market=market.upper(), position=position.lower(),
            language=detect_language(text), terms=terms(text), folded=fold(text),
            sections=sections(text), words=len(TOKEN.findall(fold(text))),
            outcome=outcomes.get(rel) or outcomes.get(path.name),
        ))
    return docs


# ---------------------------------------------------------------- statistics

def shrunk(y: int, n: int, p0: float, k: float = PRIOR_K) -> float:
    """Beta-Binomial posterior mean with the parent rate p0 as prior."""
    return (y + k * p0) / (n + k)


def contrast(y1: int, n1: int, y2: int, n2: int, k: float = PRIOR_K) -> tuple[float, float, float]:
    """Shrunk rates in two groups and a z-score for their difference."""
    p0 = (y1 + y2 + 1) / (n1 + n2 + 2)
    a, b = shrunk(y1, n1, p0, k), shrunk(y2, n2, p0, k)
    var = a * (1 - a) / (n1 + k + 1) + b * (1 - b) / (n2 + k + 1)
    return a, b, (a - b) / math.sqrt(var) if var > 0 else 0.0


def confidence(n: int) -> str:
    return "low" if n < 15 else "medium" if n < 50 else "high"


def distinctive(group: list[Doc], baseline: list[Doc], top: int = 25) -> list[dict]:
    """Terms the group uses far more than the baseline, strongest first."""
    if len(group) < MIN_DOCS or len(baseline) < MIN_DOCS:
        return []
    g, b = Counter(), Counter()
    for d in group:
        g.update(d.terms)
    for d in baseline:
        b.update(d.terms)
    out = []
    for term, y in g.items():
        if y < MIN_DOCS or y / len(group) < MIN_PREVALENCE:
            continue
        pg, pb, z = contrast(y, len(group), b.get(term, 0), len(baseline))
        if z >= Z_MIN:
            out.append({"term": term, "share": round(y / len(group), 2), "baseline_share": round(b.get(term, 0) / len(baseline), 2),
                        "z": round(z, 1)})
    # one entry per idea: drop fragments that overlap a stronger term with about the same share
    out = [r for r in out if not any(re.search(rx, r["term"]) for rx in PERSONAL.values()) and not set(r["term"].split()) & PERSONAL_WORDS]
    out.sort(key=lambda r: (-r["z"], -len(r["term"])))
    kept: list[dict] = []
    for r in out:
        toks = set(r["term"].split()) - ALL_STOP
        if any(toks & (set(k["term"].split()) - ALL_STOP) and abs(r["share"] - k["share"]) < 0.08 for k in kept):
            continue
        kept.append(r)
        if len(kept) >= top:
            break
    return kept


def pattern_share(docs: list[Doc], pattern: str) -> tuple[int, int]:
    rx = re.compile(pattern, re.I)
    return sum(1 for d in docs if rx.search(d.folded)), len(docs)


def section_profile(docs: list[Doc]) -> dict:
    share = Counter(s for d in docs for s in d.sections)
    pos: dict[str, list[int]] = defaultdict(list)
    for d in docs:
        for i, s in enumerate(d.sections):
            pos[s].append(i)
    order = sorted(share, key=lambda s: median(pos[s]))
    return {
        "usual_order": [s for s in order if share[s] / len(docs) >= 0.3],
        "share": {s: round(share[s] / len(docs), 2) for s in order},
    }


def outcome_signals(docs: list[Doc], conventions: list[dict] | None = None) -> dict:
    won = [d for d in docs if d.outcome in {"interview", "placed"}]
    lost = [d for d in docs if d.outcome in {"rejected", "sent"}]
    if len(won) < MIN_OUTCOMES or len(lost) < MIN_OUTCOMES:
        return {"verdict": "not yet known", "reason": f"needs {MIN_OUTCOMES} CVs on each side with an outcome; has {len(won)} successful and {len(lost)} not"}
    rated = won + lost
    base = len(won) / len(rated)
    conv = []
    for c in conventions or []:
        rx = re.compile(c["pattern"], re.I)
        has = [d for d in rated if rx.search(d.folded)]
        hasnt = [d for d in rated if not rx.search(d.folded)]
        if len(has) < MIN_DOCS or len(hasnt) < MIN_DOCS:
            continue
        yw = sum(d in won for d in has)
        yn = sum(d in won for d in hasnt)
        a, b, z = contrast(yw, len(has), yn, len(hasnt))
        verdict = "helps" if z >= Z_MIN else "hurts" if z <= -Z_MIN else "not yet known"
        conv.append({"label": c["label"], "interview_rate_with": round(yw / len(has), 2), "interview_rate_without": round(yn / len(hasnt), 2),
                     "cvs_with": len(has), "cvs_without": len(hasnt), "z": round(z, 1), "verdict": verdict})
    return {"verdict": "measured", "won": len(won), "lost": len(lost), "base_rate": round(base, 2),
            "conventions": conv, "terms_that_win": distinctive(won, lost, top=15)}


# ---------------------------------------------------------------- playbooks

def load_seeds(path: Path) -> dict[tuple[str, str], dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(p["market"], p["position"]): p for p in data["playbooks"]}


def build_playbooks(docs: list[Doc], seeds: dict[tuple[str, str], dict] | None = None) -> dict[tuple[str, str], dict]:
    seeds = seeds or {}
    groups: dict[tuple[str, str], list[Doc]] = defaultdict(list)
    for d in docs:
        groups[(d.market, d.position)].append(d)
    books: dict[tuple[str, str], dict] = {}
    for key in sorted(set(groups) | set(seeds)):
        market, position = key
        group = groups.get(key, [])
        seed = seeds.get(key, {})
        book: dict = {
            "market": market, "position": position, "label": seed.get("label", f"{market} · {position}"),
            "cvs": len(group), "confidence": confidence(len(group)) if group else "none (priors only)",
            "notes": seed.get("notes", []), "vocabulary": seed.get("vocabulary", {}), "avoid": seed.get("avoid", []),
            "credentials": seed.get("credentials", []), "software": seed.get("software", []),
        }
        if group:
            langs = Counter(d.language for d in group)
            book["cv_languages"] = {l: round(c / len(group), 2) for l, c in langs.most_common()}
            book["median_words"] = int(median(d.words for d in group))
            book["sections"] = section_profile(group)
            book["personal_data"] = {k: round(pattern_share(group, rx)[0] / len(group), 2) for k, rx in PERSONAL.items()}
            # seed conventions, measured
            conv = []
            for c in seed.get("conventions", []):
                y, n = pattern_share(group, c["pattern"])
                others = [d for d in docs if d.position == position and d.market != market]
                yo, no = pattern_share(others, c["pattern"]) if others else (0, 0)
                conv.append({**{k: v for k, v in c.items() if k != "pattern"}, "share": round(y / n, 2),
                             "elsewhere": round(yo / no, 2) if no else None, "source": "MEASURED"})
            book["conventions"] = conv
            # discovered terms, per CV language, against two fair baselines
            book["market_specific"], book["role_specific"] = {}, {}
            for lang in langs:
                g = [d for d in group if d.language == lang]
                mkt = [d for d in docs if d.language == lang and d.position == position and d.market != market]
                role = [d for d in docs if d.language == lang and d.market == market and d.position != position]
                if len(g) >= MIN_DOCS:
                    book["market_specific"][lang] = distinctive(g, mkt) if len(mkt) >= MIN_DOCS else "no comparison group yet"
                    book["role_specific"][lang] = distinctive(g, role) if len(role) >= MIN_DOCS else "no comparison group yet"
            book["what_wins"] = outcome_signals(group, seed.get("conventions", []))
        else:
            book["conventions"] = [{**{k: v for k, v in c.items() if k != "pattern"}, "source": "PRIOR"} for c in seed.get("conventions", [])]
        books[key] = book
    return books


def check_cv(text: str, book: dict, seed: dict | None = None) -> list[dict]:
    """What a CV lacks or carries compared with its market's norms."""
    seed = seed or {}
    folded = fold(text)
    lang = detect_language(text)
    found = sections(text)
    issues: list[dict] = []
    for c in seed.get("conventions", []):
        measured = next((m for m in book.get("conventions", []) if m.get("key") == c.get("key")), {})
        share = measured.get("share")
        if not re.search(c["pattern"], folded, re.I):
            if share is None or share >= 0.3:
                basis = f"{int(share * 100)}% of {book['label']} CVs mention it" if share is not None else "[PRIOR] expected in this market"
                issues.append({"kind": "ask", "what": c["label"], "why": c.get("why", ""), "basis": basis})
    for s, share in book.get("sections", {}).get("share", {}).items():
        if share >= 0.7 and s not in found and s not in {"personal", "references", "interests"}:
            issues.append({"kind": "missing_section", "what": s, "basis": f"{int(share * 100)}% of {book['label']} CVs have it"})
    for k, rx in PERSONAL.items():
        if re.search(rx, folded, re.I):
            issues.append({"kind": "remove", "what": k.replace("_", " "), "basis": "personal data: removed from the client version"})
    expected = book.get("cv_languages") or {l: 1 for l in seed.get("cv_languages", [])}
    if expected and lang not in expected:
        issues.append({"kind": "language", "what": f"CV written in {lang}", "basis": f"this market's CVs are in {', '.join(expected)}"})
    return issues
