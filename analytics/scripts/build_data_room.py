"""Build the Gentis Belgium Data Room page from the committed Cube19 samples.

Reads only files in data/gentis/ (personal columns already removed by
ingest_pages.py), so the page never carries candidate names, candidate emails or
client contact names. Writes dashboard/data_room.html.

Standard library only.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G = ROOT / "data" / "gentis"
DASH = ROOT / "dashboard"

BE = re.compile(r"Brussels|Antwerp|Belgium|Bxl", re.I)


def is_be(m: str) -> bool:
    return bool(BE.search(m or ""))


def rows(name: str) -> list[dict]:
    p = G / name
    return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []


def f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def day(s: str):
    try:
        return dt.datetime.strptime(s, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def city(m: str) -> str:
    return "Antwerp" if "Antwerp" in m else "Brussels" if "Brussels" in m else "Belgium (no city)"


# ---------------------------------------------------------------- placements
def perm_rows() -> list[dict]:
    out = []
    for r in rows("perm_placements_sample.csv"):
        out.append({
            "placement_id": r["placement_id"], "date_approved": r["date_approved"], "start_date": r["start_date"],
            "client": r["client"], "job_title": r["job_title"], "market": r["market"], "owner": r["owner"],
            "priority": r["priority"], "salary_eur": r["salary_eur"], "fee_pct": r["fee_pct"], "split": r["split"],
            "billing_eur": r["billing_eur"], "time_to_fill": r["time_to_fill"], "source": r["source"],
            "period": "Earlier sample" if r["period"] == "prior" else "Recent sample",
            "is_retainer": r["is_retainer"], "flag": "",
        })
    for r in rows("perm_placements_page2.csv"):
        flag = []
        if (f(r["fee_pct"]) or 0) > 100:
            flag.append(f"fee recorded as {r['fee_pct_raw']}")
        a, s = day(r["date_approved"]), day(r["start_date"])
        if a and s and (a - s).days > 60:
            flag.append("start date months before approval")
        if r.get("candidate_deleted") == "true":
            flag.append("candidate record deleted")
        out.append({
            "placement_id": r["placement_id"], "date_approved": r["date_approved"], "start_date": r["start_date"],
            "client": r["client"], "job_title": r["job_title"], "market": r["market"], "owner": r["owner"],
            "priority": r["priority"], "salary_eur": "", "fee_pct": "" if (f(r["fee_pct"]) or 0) > 100 else r["fee_pct"],
            "split": r["split"], "billing_eur": r["billing_eur"], "time_to_fill": r["time_to_fill"], "source": r["source"],
            "period": "Nov 2025 – Mar 2026", "is_retainer": r["is_retainer"], "flag": "; ".join(flag),
        })
    return [r for r in out if is_be(r["market"])]


def contract_rows() -> list[dict]:
    out = []
    for r in rows("contract_placements_sample.csv"):
        out.append({
            "placement_id": r["placement_id"], "client": r["client"], "job_title": "", "market": r["market"],
            "owner": r["owner"], "job_owner": r["job_owner"], "priority": r["priority"], "fee_pct": r["fee_pct"],
            "weekly_gp": r["weekly_gp"], "billing_eur": r["invoice_gp"], "start_date": "", "end_date": "", "weeks": "",
            "contract_type": r["contract_type"], "job_type": r["job_type"], "source": r["source"], "time_to_fill": r["ttf"],
            "period": "Earlier sample" if r["period"] == "prior" else "Recent sample",
        })
    for r in rows("contract_placements_page2.csv"):
        s, e = day(r["start_date"]), day(r["end_date"])
        out.append({
            "placement_id": r["placement_id"], "client": r["client"], "job_title": r["job_title"], "market": r["market"],
            "owner": r["owner"], "job_owner": r["job_owner"], "priority": r["priority"], "fee_pct": r["fee_pct"],
            "weekly_gp": r["weekly_gp"], "billing_eur": r["billing_eur"], "start_date": r["start_date"],
            "end_date": r["end_date"], "weeks": round((e - s).days / 7, 1) if s and e else "",
            "contract_type": r["contract_type"], "job_type": r["job_type"], "source": r["source"],
            "time_to_fill": r["time_to_fill"], "period": "Mar – Jul 2025 (new, excl. extensions)",
        })
    return [r for r in out if is_be(r["market"])]


# ---------------------------------------------------------------- activity
def activity_rows():
    iv = [r for r in rows("interviews_feb2023.csv") if is_be(r["market"])]
    mt = [r for r in rows("client_meetings_apr2023.csv") if is_be(r["market"])]
    return iv, mt


def terms_by_client(iv, mt) -> dict:
    t = {}
    for r in iv + mt:
        if any(r.get(k) for k in ("org_freelance", "org_payment_terms", "org_rate_max", "org_terms_other")):
            t[r["client"]] = {k: r.get(k, "") for k in ("org_freelance", "org_payment_terms", "org_rate_max", "org_rate_min", "org_terms_other")}
    return t


# ---------------------------------------------------------------- aggregates
def build() -> dict:
    perm, con = perm_rows(), contract_rows()
    iv, mt = activity_rows()
    terms = terms_by_client(iv, mt)

    # perm: unique placements, billing summed across split rows
    bill = defaultdict(float)
    uniq = {}
    for r in perm:
        bill[r["placement_id"]] += f(r["billing_eur"], 0)
        uniq.setdefault(r["placement_id"], r)
    pv = list(uniq.values())
    pri = Counter(v["priority"] or "(blank)" for v in pv)
    real = [bill[v["placement_id"]] for v in pv if v["is_retainer"] != "true" and bill[v["placement_id"]] > 0]
    permst = {
        "placements": len(pv), "rows": len(perm), "billing": sum(bill.values()),
        "a_share": sum(n for k, n in pri.items() if k in ("A", "A+")) / len(pv),
        "blank": pri.get("(blank)", 0) / len(pv),
        "retainer": sum(v["is_retainer"] == "true" for v in pv) / len(pv),
        "fee_median": med(f(v["fee_pct"]) for v in pv if 0 < (f(v["fee_pct"]) or 0) <= 100),
        "ttf_median": med(f(v["time_to_fill"]) for v in pv), "median_bill": med(real),
        "flagged": sum(bool(v["flag"]) for v in pv),
    }

    cur = [r for r in con if r["period"] == "Recent sample"]
    pr = [r for r in con if r["period"] == "Earlier sample"]
    new = [r for r in con if r["period"].startswith("Mar")]
    gp = lambda r: f(r["billing_eur"], 0)
    ghost = lambda r: r["owner"].startswith("Ghost")
    cst = {
        "rows": len(con), "prior": len(pr), "current": len(cur), "new": len(new),
        "m_prior": med(f(r["fee_pct"]) for r in pr), "m_cur": med(f(r["fee_pct"]) for r in cur),
        "m_new": med(f(r["fee_pct"]) for r in new),
        "thin": sum((f(r["fee_pct"]) or 0) < 12 for r in cur + new) / max(1, len(cur + new)),
        "ghost_prior": sum(map(ghost, pr)) / max(1, len(pr)), "ghost_cur": sum(map(ghost, cur)) / max(1, len(cur)),
        "ghost_new": sum(map(ghost, new)) / max(1, len(new)),
        "ghost_gp": sum(gp(r) for r in con if ghost(r)) / max(1, sum(gp(r) for r in con)),
        "gp": sum(gp(r) for r in con),
        "weeks_median": med(f(r["weeks"]) for r in new), "weekly_median": med(f(r["weekly_gp"]) for r in con),
        "ttf_median": med(f(r["time_to_fill"]) for r in con if r["time_to_fill"]),
        "ttf_n": sum(1 for r in con if r["time_to_fill"]),
    }

    # desks
    desks = defaultdict(lambda: {"perm_n": 0, "perm_bill": 0.0, "con_n": 0, "con_gp": 0.0, "fees": [], "weekly": [], "weeks": [], "iv": 0, "mt": 0})
    for v in pv:
        d = desks[v["market"]]; d["perm_n"] += 1; d["perm_bill"] += bill[v["placement_id"]]
    for r in con:
        d = desks[r["market"]]; d["con_n"] += 1; d["con_gp"] += gp(r)
        d["fees"].append(f(r["fee_pct"])); d["weekly"].append(f(r["weekly_gp"])); d["weeks"].append(f(r["weeks"]))
    for r in iv:
        desks[r["market"]]["iv"] += 1
    for r in mt:
        desks[r["market"]]["mt"] += 1
    deskrows = [{"desk": m, "city": city(m), "perm_n": d["perm_n"], "perm_bill": d["perm_bill"], "con_n": d["con_n"],
                 "con_gp": d["con_gp"], "margin": med(d["fees"]), "weekly": med(d["weekly"]), "weeks": med(d["weeks"]),
                 "iv": d["iv"], "mt": d["mt"]} for m, d in desks.items()]

    # clients
    cl = defaultdict(lambda: {"perm_n": 0, "perm_bill": 0.0, "con_n": 0, "con_gp": 0.0, "fees": [], "desks": set(),
                              "periods": set(), "roles": set(), "iv": 0, "mt": 0, "owners": set()})
    for v in pv:
        c = cl[v["client"]]; c["perm_n"] += 1; c["perm_bill"] += bill[v["placement_id"]]
        c["desks"].add(v["market"]); c["periods"].add(v["period"]); c["roles"].add(v["job_title"]); c["owners"].add(v["owner"])
    for r in con:
        c = cl[r["client"]]; c["con_n"] += 1; c["con_gp"] += gp(r); c["fees"].append(f(r["fee_pct"]))
        c["desks"].add(r["market"]); c["periods"].add(r["period"]); c["owners"].add(r["owner"])
        if r["job_title"]:
            c["roles"].add(r["job_title"])
    for r in iv:
        c = cl[r["client"]]; c["iv"] += 1; c["desks"].add(r["market"]); c["roles"].add(r["job_title"])
    for r in mt:
        c = cl[r["client"]]; c["mt"] += 1; c["desks"].add(r["market"])
    clients = []
    for k, c in cl.items():
        t = terms.get(k, {})
        clients.append({
            "client": k, "perm_n": c["perm_n"], "perm_bill": c["perm_bill"], "con_n": c["con_n"], "con_gp": c["con_gp"],
            "margin": med(c["fees"]), "desks": sorted(c["desks"]), "periods": sorted(c["periods"]),
            "roles": sorted(x for x in c["roles"] if x), "owners": sorted(x for x in c["owners"] if x),
            "iv": c["iv"], "mt": c["mt"], "value": c["perm_bill"] + c["con_gp"],
            "fee_band": (t.get("org_rate_max", "") + (" – " + t["org_rate_min"] if t.get("org_rate_min") else "")) or t.get("org_terms_other", ""),
            "pay_days": t.get("org_payment_terms", ""), "freelance": t.get("org_freelance", ""),
        })
    clients.sort(key=lambda x: (-x["value"], -(x["iv"] + x["mt"])))

    # recruiters
    rc = defaultdict(lambda: {"perm_n": 0, "perm_bill": 0.0, "con_n": 0, "con_gp": 0.0, "iv": 0, "mt": 0, "desks": set(), "clients": set()})
    for r in perm:
        o = rc[r["owner"]]; o["perm_n"] += f(r["split"], 1); o["perm_bill"] += f(r["billing_eur"], 0)
        o["desks"].add(r["market"]); o["clients"].add(r["client"])
    for r in con:
        o = rc[r["owner"]]; o["con_n"] += 1; o["con_gp"] += gp(r); o["desks"].add(r["market"]); o["clients"].add(r["client"])
    for r in iv:
        o = rc[r["owner"]]; o["iv"] += 1; o["desks"].add(r["market"])
    for r in mt:
        o = rc[r["owner"]]; o["mt"] += 1; o["desks"].add(r["market"])
    recruiters = sorted(({"owner": k, "perm_n": round(o["perm_n"], 1), "perm_bill": o["perm_bill"], "con_n": o["con_n"],
                          "con_gp": o["con_gp"], "iv": o["iv"], "mt": o["mt"], "desks": sorted(o["desks"]),
                          "clients": len(o["clients"]), "value": o["perm_bill"] + o["con_gp"], "ghost": k.startswith("Ghost")}
                         for k, o in rc.items()), key=lambda x: -x["value"])

    rate_max = [f(t["org_rate_max"].rstrip("%")) for t in terms.values() if t["org_rate_max"].endswith("%")]
    pay = Counter(t["org_payment_terms"] for t in terms.values() if t["org_payment_terms"])
    termst = {"clients": len(terms), "rate_median": med(rate_max), "rate_min": min(rate_max) if rate_max else None,
              "rate_max": max(rate_max) if rate_max else None, "pay": pay.most_common(),
              "freelance_yes": sum(t["org_freelance"] == "YES" for t in terms.values()),
              "freelance_known": sum(bool(t["org_freelance"]) for t in terms.values())}

    ivrows = [{k: r[k] for k in ("created", "interview_date", "owner", "market", "client", "client_contact_position",
                                 "job_title", "priority", "job_type", "interview_type", "source")} for r in iv]
    mtrows = [{k: r[k] for k in ("meeting_date", "owner", "market", "client", "client_contact_position", "meeting_type")} for r in mt]

    z = json.loads((DASH / "zig_year1.json").read_text())
    z["perm"] = [d for d in z["perm"] if is_be(d["desk"])]
    z["freelance"] = [d for d in z["freelance"] if is_be(d["desk"])]

    allp = rows("perm_placements_sample.csv") + rows("perm_placements_page2.csv")
    allc = rows("contract_placements_sample.csv") + rows("contract_placements_page2.csv")
    return {
        "perm": perm, "contract": con, "interviews": ivrows, "meetings": mtrows,
        "permst": permst, "cst": cst, "termst": termst, "desks": deskrows, "clients": clients, "recruiters": recruiters,
        "zig": z, "excluded": {"perm": len(allp) - len(perm), "contract": len(allc) - len(con),
                               "markets": sorted({r["market"] for r in allp + allc if not is_be(r["market"])})},
    }


if __name__ == "__main__":
    data = build()
    tpl = (DASH / "data_room_template.html").read_text(encoding="utf-8")
    out = DASH / "data_room.html"
    out.write_text(tpl.replace("__DATA__", json.dumps(data, separators=(",", ":"), default=list)), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}: {data['permst']['placements']} perm, {data['cst']['rows']} contract, "
          f"{len(data['interviews'])} interviews, {len(data['meetings'])} meetings, {len(data['clients'])} clients, "
          f"{len(data['recruiters'])} recruiters")
