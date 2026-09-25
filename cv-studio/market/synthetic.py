"""A synthetic CV corpus for tests and demos. Every CV here is invented.

It plants market conventions at known rates so the analyser can be checked: if
measure_markets.py cannot find "ITAA" in Belgian accounting CVs that were written with
it 70% of the time, the analyser is wrong, not the market.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

GENERIC_FR = [
    "Rigueur, sens de l'organisation et esprit d'équipe.",
    "Encodage des factures d'achat et de vente.",
    "Suivi des paiements et relances clients.",
    "Préparation des documents pour la clôture.",
    "Maîtrise d'Excel, tableaux croisés dynamiques.",
]
GENERIC_NL = [
    "Nauwkeurig, georganiseerd en teamgericht.",
    "Inboeken van aankoop- en verkoopfacturen.",
    "Opvolging van betalingen en herinneringen.",
    "Voorbereiding van de afsluiting.",
    "Goede kennis van Excel en draaitabellen.",
]
GENERIC_EN = [
    "Accurate, organised and a team player.",
    "Processing purchase and sales invoices.",
    "Following up payments and reminders.",
    "Preparing month-end closing files.",
    "Advanced Excel, pivot tables.",
]

PLANTS = {
    ("BE", "accounting", "fr"): [(0.7, "Stagiaire ITAA, examen en cours."), (0.6, "Comptabilité de A à Z pour un portefeuille de PME."),
                                 (0.55, "Cinq ans en fiduciaire à Namur."), (0.8, "Déclarations TVA mensuelles et listing clients via Intervat."),
                                 (0.5, "Logiciels : Winbooks, BOB 50."), (0.6, "Date de naissance : 12/03/1990"), (0.5, "Permis B")],
    ("BE", "accounting", "nl"): [(0.7, "ITAA-stagiair, examen lopende."), (0.6, "Boekhouding van A tot Z voor kmo-klanten."),
                                 (0.55, "Vijf jaar ervaring in een boekhoudkantoor in Gent."), (0.8, "Maandelijkse btw-aangiftes en klantenlisting via Intervat."),
                                 (0.5, "Software: Winbooks, Exact Online."), (0.5, "Rijbewijs B")],
    ("FR", "accounting", "fr"): [(0.7, "Cinq ans en cabinet d'expertise comptable à Lille."), (0.6, "DCG obtenu, DSCG en cours."),
                                 (0.6, "Établissement de la liasse fiscale et du bilan."), (0.5, "Logiciels : Sage, Cegid."), (0.4, "Permis B")],
    ("LU", "accounting", "fr"): [(0.7, "Fund accounting : calcul de NAV pour des OPCVM."), (0.5, "Reporting CSSF trimestriel."),
                                 (0.5, "Clôtures en Lux GAAP et IFRS."), (0.4, "Dépôt des comptes via eCDF au RCS.")],
    ("LU", "accounting", "en"): [(0.8, "Fund accounting: NAV calculation for UCITS and AIF."), (0.6, "Quarterly CSSF reporting."),
                                 (0.5, "Closings under Lux GAAP and IFRS.")],
    ("BE", "it-dev", "en"): [(0.6, "Freelance through my own SRL since 2020."), (0.7, "Client: a Belgian bank, mission of 18 months."),
                             (0.6, "Languages: French C2, Dutch B2, English C1.")],
    ("BE", "it-dev", "fr"): [(0.6, "Freelance via ma SRL depuis 2020."), (0.7, "Mission : banque belge, 18 mois."),
                             (0.6, "Langues : français C2, néerlandais B2, anglais C1.")],
}
HEADINGS = {
    "fr": ["PROFIL", "EXPÉRIENCE PROFESSIONNELLE", "FORMATION", "LOGICIELS", "LANGUES"],
    "nl": ["PROFIEL", "WERKERVARING", "OPLEIDING", "SOFTWARE", "TALEN"],
    "en": ["PROFILE", "EXPERIENCE", "EDUCATION", "SKILLS", "LANGUAGES"],
}
GENERIC = {"fr": GENERIC_FR, "nl": GENERIC_NL, "en": GENERIC_EN}

MIX = {  # (market, position): [(language, count)]
    ("BE", "accounting"): [("fr", 24), ("nl", 16)],
    ("FR", "accounting"): [("fr", 30)],
    ("LU", "accounting"): [("fr", 10), ("en", 14)],
    ("BE", "it-dev"): [("en", 16), ("fr", 10)],
}


def write_corpus(root: Path, seed: int = 7, with_outcomes: bool = True) -> Path:
    rng = random.Random(seed)
    root = Path(root)
    rows = []
    for (market, position), mix in MIX.items():
        for lang, count in mix:
            for i in range(count):
                h = HEADINGS[lang]
                planted = [line for p, line in PLANTS.get((market, position, lang), []) if rng.random() < p]
                body = rng.sample(GENERIC[lang], 3)
                text = "\n".join([f"Candidate {market}-{position}-{lang}-{i}", h[0], body[0], h[1], *planted[:4], body[1], h[2], body[2], h[3], *planted[4:], h[4], "English, French"])
                path = root / market / position / f"{lang}_{i:02d}.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                if with_outcomes:
                    got = any("ITAA" in l or "A à Z" in l or "A tot Z" in l for l in planted)
                    won = rng.random() < (0.6 if got else 0.25)
                    rows.append({"file": str(path.relative_to(root)), "outcome": "interview" if won else "rejected"})
    if with_outcomes:
        with (root / "outcomes.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file", "outcome"])
            w.writeheader()
            w.writerows(rows)
    return root
