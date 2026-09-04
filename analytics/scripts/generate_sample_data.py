#!/usr/bin/env python3
"""Generate a realistic synthetic recruitment history.

Two jobs at once:

1. It makes the engine and dashboard runnable *today*, before any Cube19 export exists.
2. The CSVs it writes ARE the canonical format spec - hand data/sample/ to whoever runs
   the extraction and say "make it look like this".

The generator deliberately bakes in the things that break naive analytics, so the engine
gets tested against them: markets that differ in fee size rather than conversion, a
market that is declining, a market with almost no volume, a client that has consumed 40
CVs and never placed, consultants on a ramp curve, seasonality, and split desks.

Nothing here is Gentis data. Every number is invented.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
RNG = random.Random(1904)

START_YEAR, END_YEAR = 2019, 2025

# (market, cv->int, int->offer, offer->place, avg fee, fee sd, yearly trend, share of volume)
MARKETS = [
    ("Life Sciences",   0.38, 0.30, 0.85, 24000, 7000,  0.14, 0.20),
    ("IT & Data",       0.31, 0.26, 0.78, 19000, 5500,  0.08, 0.30),
    ("Engineering",     0.34, 0.24, 0.82, 16000, 4200,  0.02, 0.18),
    ("Finance",         0.28, 0.22, 0.76, 21000, 6500, -0.06, 0.15),
    ("Public Sector",   0.22, 0.18, 0.70,  9500, 2400, -0.18, 0.12),
    ("Renewables",      0.40, 0.32, 0.88, 27000, 8000,  0.35, 0.05),  # small, unproven, hot
]

GEOS = ["BE-VLG", "BE-BRU", "BE-WAL", "NL", "LU", "FR"]
SENIORITY = ["junior", "mid", "senior", "lead"]

FIRST = ["Anke", "Bram", "Chloé", "Dries", "Elena", "Femke", "Gilles", "Hanne", "Ilias",
         "Jonas", "Karel", "Lore", "Matthias", "Nele", "Olivier", "Pieter", "Ruben",
         "Sofie", "Thomas", "Wout"]
LAST = ["Peeters", "Janssens", "Maes", "Jacobs", "Willems", "Claes", "Goossens", "Wouters",
        "De Smet", "Dubois", "Lambert", "Martin", "Simon", "Leroy", "Mertens"]


def working_day(year: int) -> date:
    """A random weekday, with real recruitment seasonality baked in."""
    # August dead, September and January spikes, December slow.
    weights = [1.15, 1.0, 1.05, 0.95, 1.0, 0.9, 0.75, 0.45, 1.25, 1.1, 1.05, 0.7]
    month = RNG.choices(range(1, 13), weights=weights)[0]
    day = RNG.randint(1, 28)
    d = date(year, month, day)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def ramp_factor(months: float) -> float:
    """Productivity by tenure. Nothing for a quarter, then a slow climb to steady state
    around 12-18 months - the shape every recruitment manager knows and few plan for."""
    if months < 3:
        return 0.05
    if months < 6:
        return 0.35
    if months < 9:
        return 0.6
    if months < 12:
        return 0.8
    if months < 18:
        return 0.95
    return 1.0


def build():
    OUT.mkdir(parents=True, exist_ok=True)

    # -- consultants: staggered starts, some leavers ------------------------
    consultants = []
    used_names = set()
    for i in range(22):
        market = RNG.choices([m[0] for m in MARKETS], weights=[m[7] for m in MARKETS])[0]
        while True:
            name = f"{RNG.choice(FIRST)} {RNG.choice(LAST)}"
            if name not in used_names:
                used_names.add(name)
                break
        start = date(RNG.randint(START_YEAR - 2, END_YEAR - 1), RNG.randint(1, 12), 1)
        # ~25% attrition, which is normal and matters: a history containing only current
        # staff is missing most of its placements.
        end = None
        if RNG.random() < 0.25:
            end = start + timedelta(days=RNG.randint(400, 1600))
            if end > date(END_YEAR, 12, 31):
                end = None
        consultants.append({
            "consultant_id": f"U{i+1:03d}", "name": name, "market": market,
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else "",
            "_start": start, "_end": end,
        })

    # -- clients ------------------------------------------------------------
    clients = []
    for i in range(70):
        market = RNG.choices([m[0] for m in MARKETS], weights=[m[7] for m in MARKETS])[0]
        clients.append({
            "client_id": f"C{i+1:03d}",
            "name": f"{RNG.choice(['Nova','Atlas','Meridian','Kestrel','Orbit','Vantage','Delta','Helix','Aurora','Beacon','Pivot','Quanta','Lumen','Verge','Cobalt'])} "
                    f"{RNG.choice(['Group','Systems','Labs','Industries','Partners','Technologies','Solutions','NV','BV'])}",
            "market": market,
            "geo": RNG.choices(GEOS, weights=[45, 20, 12, 12, 5, 6])[0],
            "date_added": date(RNG.randint(START_YEAR - 3, END_YEAR - 1), RNG.randint(1, 12), 15).isoformat(),
            "industry": market,
            "_quality": RNG.betavariate(2.2, 2.2),  # how good this account really is
        })

    # One account that eats effort and never converts - the Deprioritise case the whole
    # client-scoring section exists to surface.
    clients[3]["_quality"] = 0.02
    clients[3]["name"] = "Ironclad Holdings"
    # One account that went quiet after being excellent - the dormant/reactivation case.
    clients[7]["_quality"] = 0.9
    clients[7]["name"] = "Meridian Pharma"

    jobs, stage_events, placements, activities = [], [], [], []
    job_n = sub_n = pl_n = 0

    market_cfg = {m[0]: m for m in MARKETS}

    for year in range(START_YEAR, END_YEAR + 1):
        years_in = year - START_YEAR
        for c in consultants:
            if c["_start"].year > year or (c["_end"] and c["_end"].year < year):
                continue
            cfg = market_cfg[c["market"]]
            _, p_int, p_off, p_pl, fee_mu, fee_sd, trend, _ = cfg

            tenure = (date(year, 6, 30) - c["_start"]).days / 30.44
            ramp = ramp_factor(tenure)
            trend_mult = (1 + trend) ** years_in
            # 2020 covid dip, which also gives the YoY decomposition something real to find
            covid = 0.72 if year == 2020 else 1.0

            n_jobs = max(1, int(RNG.gauss(26, 6) * ramp * trend_mult * covid))
            market_clients = [cl for cl in clients if cl["market"] == c["market"]] or clients

            for _ in range(n_jobs):
                job_n += 1
                job_id = f"J{job_n:05d}"
                client = RNG.choices(market_clients,
                                     weights=[0.2 + cl["_quality"] for cl in market_clients])[0]
                opened = working_day(year)
                exclusive = RNG.random() < 0.22
                ptype = "contract" if RNG.random() < 0.28 else "perm"
                jobs.append({
                    "job_id": job_id, "client_id": client["client_id"],
                    "consultant_id": c["consultant_id"], "market": c["market"],
                    "date_opened": opened.isoformat(), "date_closed": "",
                    "exclusive": "true" if exclusive else "false",
                    "seniority": RNG.choices(SENIORITY, weights=[20, 45, 28, 7])[0],
                    "placement_type": ptype,
                })

                # CVs per job: quality accounts and exclusive briefs get fewer, better CVs
                base_cvs = 2.4 if exclusive else 3.6
                n_cvs = max(0, int(RNG.gauss(base_cvs, 1.3)))
                placed_this_job = False

                for _ in range(n_cvs):
                    sub_n += 1
                    sub_id = f"S{sub_n:06d}"
                    cand_id = f"K{RNG.randint(1, 40000):06d}"
                    cv_date = opened + timedelta(days=RNG.randint(2, 45))
                    if cv_date.year != year:
                        cv_date = date(year, 12, 20)

                    def ev(stage, when):
                        stage_events.append({
                            "submission_id": sub_id, "job_id": job_id,
                            "candidate_id": cand_id, "client_id": client["client_id"],
                            "consultant_id": c["consultant_id"], "market": c["market"],
                            "stage": stage, "event_date": when.isoformat(),
                            "placement_type": ptype,
                        })

                    ev("Internally Submitted", cv_date - timedelta(days=RNG.randint(1, 5)))
                    ev("Client Submission", cv_date)

                    # Conversion is the market's rate, tilted by account quality,
                    # consultant ramp and exclusivity.
                    quality_mult = 0.55 + client["_quality"] * 0.9
                    p1 = min(p_int * quality_mult * (0.65 + 0.35 * ramp)
                             * (1.35 if exclusive else 1.0), 0.95)
                    if RNG.random() >= p1:
                        continue
                    i1 = cv_date + timedelta(days=RNG.randint(5, 28))
                    ev("1st Interview", i1)

                    if RNG.random() < 0.62:
                        ev("2nd Interview", i1 + timedelta(days=RNG.randint(5, 20)))

                    if RNG.random() >= min(p_off * quality_mult, 0.9):
                        continue
                    off = i1 + timedelta(days=RNG.randint(10, 40))
                    ev("Offer", off)

                    if placed_this_job or RNG.random() >= p_pl:
                        continue
                    start = off + timedelta(days=RNG.randint(14, 75))
                    ev("Placed", start)
                    placed_this_job = True

                    pl_n += 1
                    fee = max(3000, RNG.gauss(fee_mu, fee_sd)) * (1 + 0.03 * years_in)
                    if ptype == "contract":
                        fee *= 0.75  # contract GP accrues; smaller at recognition
                    placements.append({
                        "placement_id": f"P{pl_n:05d}", "job_id": job_id,
                        "submission_id": sub_id, "client_id": client["client_id"],
                        "consultant_id": c["consultant_id"], "market": c["market"],
                        "start_date": start.isoformat(), "gp": f"{fee:.2f}",
                        "placement_type": ptype,
                        "fell_off": "true" if RNG.random() < 0.06 else "false",
                    })

            # -- activity: logged imperfectly, exactly like the real thing ----
            # Some consultants barely log calls. That is not noise to be smoothed away,
            # it is the reason docs/04 says anchor targets at CVs sent.
            logging_quality = 0.25 if random.Random(c["consultant_id"]).random() < 0.3 else 1.0
            for month in range(1, 13):
                if c["_start"] > date(year, month, 28):
                    continue
                if c["_end"] and c["_end"] < date(year, month, 1):
                    continue
                seasonal = 0.4 if month == 8 else (0.65 if month == 12 else 1.0)
                calls = int(RNG.gauss(140, 35) * ramp * seasonal * logging_quality * covid)
                connects = int(calls * RNG.uniform(0.18, 0.32))
                meetings = int(connects * RNG.uniform(0.12, 0.26))
                for action, n in (("call", calls), ("connect", connects),
                                  ("email", int(calls * 1.4)), ("client_meeting", meetings)):
                    if n <= 0:
                        continue
                    activities.append({
                        "activity_date": date(year, month, 15).isoformat(),
                        "consultant_id": c["consultant_id"], "market": c["market"],
                        "action": action, "client_id": "", "count": n,
                    })

    # Make Meridian Pharma genuinely dormant: nothing after 2023.
    dormant_id = clients[7]["client_id"]
    jobs = [j for j in jobs if not (j["client_id"] == dormant_id and j["date_opened"] >= "2024")]
    stage_events = [e for e in stage_events
                    if not (e["client_id"] == dormant_id and e["event_date"] >= "2024")]
    placements = [p for p in placements
                  if not (p["client_id"] == dormant_id and p["start_date"] >= "2024")]

    for cl in clients:
        cl.pop("_quality", None)
    for c in consultants:
        c.pop("_start", None)
        c.pop("_end", None)

    _write("stage_events.csv", stage_events)
    _write("placements.csv", placements)
    _write("jobs.csv", jobs)
    _write("activities.csv", activities)
    _write("consultants.csv", consultants)
    _write("clients.csv", clients)

    print(f"Wrote synthetic history to {OUT}")
    print(f"  {len(stage_events):>7,} stage events")
    print(f"  {len(placements):>7,} placements")
    print(f"  {len(jobs):>7,} jobs")
    print(f"  {len(activities):>7,} activity rows")
    print(f"  {len(consultants):>7,} consultants, {len(clients):,} clients")
    print(f"  total GP: EUR {sum(float(p['gp']) for p in placements):,.0f}")


def _write(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    path = OUT / name
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    build()
