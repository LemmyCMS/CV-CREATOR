# Market playbooks

How CVs are built differs by market and by role. A Belgian accountant's CV says ITAA,
*comptabilité de A à Z* and *fiduciaire*; a French one says DCG and *cabinet*; a
Luxembourg one says fund accounting and CSSF. This folder learns those differences from
past CVs and feeds them into CV Studio, so each Zig CV speaks its client's market.

| File | What it does |
|---|---|
| `seed_playbooks.json` | Recruiter knowledge per market and position, labelled `[PRIOR]`. Used until real CVs are measured. |
| `cvcorpus.py` | The analyser. Standard library only. |
| `measure_markets.py` | `build` a playbook from a CV archive, `check` one CV, or run a `demo` on invented CVs. |
| `embed_playbooks.py` | Copies playbooks (rules and shares only, no CV text) into `zig_cv_studio.html`. |
| `synthetic.py` | Invented corpus for tests and the demo. |

## Run it on the real archive

1. Export CVs as text (Bullhorn's parsed resume text, or `.docx`; PDFs need converting to `.txt`).
2. Put them in `corpus/<MARKET>/<position>/`, e.g. `corpus/BE/accounting/`. Optional
   `corpus/outcomes.csv` with `file,outcome` (`sent`, `interview`, `placed`, `rejected`).
3. `python3 measure_markets.py build corpus --out playbooks.json`
4. `python3 embed_playbooks.py playbooks.json`, then republish CV Studio.

`corpus/` and `playbooks.json` are git-ignored: CVs are personal data.

## How to read the output

* **Market-specific terms** compare a group with the *same position and same CV language*
  in other markets, so French-language Belgian CVs are compared with French and
  Luxembourg ones, never with Dutch ones.
* Every rate is shrunk toward the parent rate; a term needs z ≥ 2 and at least 3 CVs.
  Groups under 15 CVs are marked low confidence.
* **What wins** compares interview rates for CVs with and without each convention. Under
  10 outcomes on either side it answers "not yet known", which is a verdict, not a gap.
* `check` lists conventions a CV does not mention as **ask**: things to confirm with the
  candidate, never things to add.

Tests: `python3 -m unittest discover -s tests -v`
