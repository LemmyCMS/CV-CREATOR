"""Turn Slice & Dice pages pasted from Cube19 into CSV.

A pasted page is one value per line with blank cells dropped, so fields cannot be
read by position alone. Each parser anchors on the values that are always present
(dates, numeric IDs, fixed vocabularies) and assigns the optional ones around them.

Writes two files per page:
  data/raw/<name>_full.csv     every column, including candidate and contact
                               personal data. Git-ignored - never commit it.
  data/gentis/<name>.csv       the same rows with personal columns removed.
                               Safe to commit and to publish.

Standard library only.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "gentis"

DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
ID = re.compile(r"^\d{4,7}$")
PRIORITIES = {"A+", "A", "B", "C", "D", "SPEC"}
JOB_TYPES = {"Contract", "Opportunity", "Permanent", "Retainer", "Temp-to-Perm", "Contract Payroll"}

PERSONAL = {"candidate", "candidate_email", "candidate_id", "client_contact", "client_contact_email"}


def lines(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def money(s: str) -> tuple[float | None, str]:
    """'€23,100' -> (23100.0, 'EUR'); 'AED 50,000' -> (50000.0, 'AED')."""
    cur = "EUR" if "€" in s else "CAD" if "C$" in s else "AED" if "AED" in s else ""
    n = re.sub(r"[^\d.]", "", s)
    return (float(n) if n else None), cur


def pct(s: str) -> float | None:
    n = re.sub(r"[^\d.]", "", s)
    return float(n) if n else None


def split_terms(tail: list[str]) -> dict:
    """Organisation terms that trail a row: freelance flag, payment terms, fee bands."""
    out = {"org_freelance": "", "org_payment_terms": "", "org_rate_max": "", "org_rate_min": "", "org_terms_other": ""}
    rest = []
    for v in tail:
        if v in ("YES", "NO") and not out["org_freelance"]:
            out["org_freelance"] = v
        else:
            rest.append(v)
    rates = [v for v in rest if v.endswith("%") or re.fullmatch(r"\d{4,6}", v)]
    other = [v for v in rest if v not in rates]
    if other and re.match(r"^(EOM )?\d{1,3}\b", other[0]):
        out["org_payment_terms"] = other.pop(0)
    if rates:
        out["org_rate_max"] = rates[0]
    if len(rates) > 1:
        out["org_rate_min"] = rates[1]
    out["org_terms_other"] = " | ".join(other)
    return out


def perm(path: Path) -> list[dict]:
    L, rows, i = lines(path), [], 0
    while i < len(L):
        c = L[i:i + 22]
        assert ID.match(c[0]) and DATE.match(c[1]), f"perm row misaligned at line {i + 1}: {c[:3]}"
        local, cur = money(c[16])
        rows.append({
            "placement_id": c[0], "date_approved": c[1], "date_added": c[2], "start_date": c[3],
            "owner": c[4], "market": c[5], "client": c[6], "client_contact": c[7], "job_title": c[8],
            "job_created": c[9], "priority": c[10], "candidate": c[11], "candidate_email": c[12],
            "split": c[13], "fee_pct_raw": c[14], "fee_pct": pct(c[14]),
            "billing_local": local, "currency": cur, "billing_eur": money(c[17])[0],
            "time_to_fill": c[18], "source": c[19], "job_owner": c[20], "job_id": c[21],
            "is_retainer": str(c[11] == "Candidate Retainer").lower(),
            "candidate_deleted": str(c[11] == "[deleted]").lower(),
        })
        i += 22
    return rows


def contract(path: Path) -> list[dict]:
    L, rows, i = lines(path), [], 0
    while i < len(L):
        assert ID.match(L[i]) and DATE.match(L[i + 1]), f"contract row misaligned at line {i + 1}"
        c = L[i:i + 12]
        j = i + 12
        pri = ""
        if L[j] in PRIORITIES:
            pri, j = L[j], j + 1
        t = L[j:j + 16]
        rows.append({
            "placement_id": c[0], "date_approved": c[1], "date_added": c[2], "start_date": c[3], "end_date": c[4],
            "owner": c[5], "employment_type": c[6], "market": c[7], "candidate_id": c[8], "candidate": c[9],
            "candidate_email": c[10], "job_title": c[11], "priority": pri, "client": t[0],
            "billing_eur": money(t[1])[0], "split": t[4], "fee_pct": pct(t[5]), "weekly_gp": money(t[6])[0],
            "contract_type": t[9], "job_type": t[10], "source": t[11], "time_to_fill": t[12],
            "job_owner": t[13], "job_id": t[14], "status": t[15],
        })
        i = j + 16
    return rows


def _starts(L: list[str]) -> list[int]:
    """Row starts in pages that open each row with two dates."""
    s = [k for k in range(len(L) - 2) if DATE.match(L[k]) and DATE.match(L[k + 1]) and not DATE.match(L[k + 2])]
    return s


def interviews(path: Path) -> list[dict]:
    L = lines(path)
    st = _starts(L) + [len(L)]
    rows = []
    for a, b in zip(st, st[1:]):
        r = L[a:b]
        head = r[:9]  # created, interview date, owner, group, org, contact email, position, job title, job created
        k = 9
        pri = ""
        if r[k] in PRIORITIES:
            pri, k = r[k], k + 1
        # candidate id / candidate / client contact run up to the job type
        jt = next(x for x in range(k, len(r)) if r[x] in JOB_TYPES)
        mid = r[k:jt]
        cand_id = mid.pop(0) if mid and ID.match(mid[0]) else ""
        contact = mid.pop() if mid else ""
        cand = mid[0] if mid else ""
        job_type, int_type, crm_type = r[jt], r[jt + 1], r[jt + 2]
        jid = next(x for x in range(jt + 3, len(r)) if ID.match(r[x]))
        between = r[jt + 3:jid]
        source, job_owner = (between + [""])[:2] if len(between) == 2 else ("", between[0] if between else "")
        rows.append({
            "created": head[0], "interview_date": head[1], "owner": head[2], "market": head[3], "client": head[4],
            "client_contact_email": head[5], "client_contact_position": head[6], "job_title": head[7],
            "job_created": head[8], "priority": pri, "candidate_id": cand_id, "candidate": cand,
            "client_contact": contact, "job_type": job_type, "interview_type": int_type, "crm_interview_type": crm_type,
            "source": source, "job_owner": job_owner, "job_id": r[jid], **split_terms(r[jid + 1:]),
        })
    return rows


def meetings(path: Path) -> list[dict]:
    L = lines(path)
    st = _starts(L) + [len(L)]
    rows = []
    for a, b in zip(st, st[1:]):
        r = L[a:b]
        rows.append({
            "created": r[0], "meeting_date": r[1], "owner": r[2], "market": r[3], "client": r[4],
            "client_contact": r[5], "meeting_type": r[6], "client_contact_position": r[7], "meeting_id": r[8],
            **split_terms(r[9:]),
        })
    return rows


def write(rows: list[dict], name: str) -> None:
    cols = list(rows[0].keys())
    with (RAW / f"{name}_full.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)
    safe = [c for c in cols if c not in PERSONAL]
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, safe, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows -> raw/{name}_full.csv ({len(cols)} cols), gentis/{name}.csv ({len(safe)} cols)")


PAGES = {
    "perm_page_2026-09-27.txt": (perm, "perm_placements_page2"),
    "contract_page_2026-09-27.txt": (contract, "contract_placements_page2"),
    "interviews_page_2026-09-27.txt": (interviews, "interviews_feb2023"),
    "meetings_page_2026-09-27.txt": (meetings, "client_meetings_apr2023"),
}

if __name__ == "__main__":
    for src, (fn, name) in PAGES.items():
        p = RAW / src
        if not p.exists():
            print(f"skip {src}: not in data/raw/", file=sys.stderr)
            continue
        write(fn(p), name)
