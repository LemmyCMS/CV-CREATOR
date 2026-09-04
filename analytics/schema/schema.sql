-- Canonical warehouse schema for the Cube19 replacement.
--
-- The Python engine holds all of this in memory (a decade of a 100-head agency is a
-- few hundred thousand rows), so this file is for when the data outgrows that or has
-- to live somewhere the rest of the business can query. Runs on DuckDB and Postgres.
--
-- The design decision that matters: stage_event is one row per *stage entry*, not one
-- row per submission. A submission that reaches Placed also passed CV Sent and
-- Interview, and each of those is its own row with its own timestamp. Storing current
-- status instead collapses the funnel and inflates every ratio downstream.

CREATE TABLE IF NOT EXISTS dim_consultant (
    consultant_id   TEXT PRIMARY KEY,
    name            TEXT,
    market          TEXT,
    start_date      DATE NOT NULL,     -- required: no start date means no ramp curve
    end_date        DATE,              -- leavers MUST be retained; they hold most of the history
    team            TEXT
);

CREATE TABLE IF NOT EXISTS dim_client (
    client_id       TEXT PRIMARY KEY,
    name            TEXT,
    market          TEXT,
    geo             TEXT,              -- BE-VLG / BE-BRU / BE-WAL / NL / FR / LU
    industry        TEXT,
    date_added      DATE
);

CREATE TABLE IF NOT EXISTS dim_market (
    market          TEXT PRIMARY KEY,
    parent          TEXT,
    -- Team structures get reorganised. Map historical desks onto current markets here
    -- rather than letting the time series break at the reorg.
    active_from     DATE,
    active_to       DATE
);

CREATE TABLE IF NOT EXISTS fact_job (
    job_id          TEXT PRIMARY KEY,
    client_id       TEXT REFERENCES dim_client(client_id),
    consultant_id   TEXT REFERENCES dim_consultant(consultant_id),
    market          TEXT,
    date_opened     DATE NOT NULL,
    date_closed     DATE,
    exclusive       BOOLEAN DEFAULT FALSE,   -- exclusive fill rates run 3-5x contingent
    seniority       TEXT,
    placement_type  TEXT CHECK (placement_type IN ('perm','contract'))
);

CREATE TABLE IF NOT EXISTS fact_stage_event (
    stage_event_id  BIGINT,
    submission_id   TEXT NOT NULL,
    job_id          TEXT REFERENCES fact_job(job_id),
    candidate_id    TEXT,
    client_id       TEXT REFERENCES dim_client(client_id),
    consultant_id   TEXT REFERENCES dim_consultant(consultant_id),
    market          TEXT,
    stage           TEXT NOT NULL CHECK (stage IN (
                      'internal_submission','cv_sent','first_interview',
                      'further_interview','offer','placed','rejected')),
    event_date      DATE NOT NULL,
    placement_type  TEXT,
    source_status   TEXT   -- the tenant's raw status string, kept so a bad map is recoverable
);

CREATE TABLE IF NOT EXISTS fact_placement (
    placement_id    TEXT PRIMARY KEY,
    submission_id   TEXT,               -- links a placement back to the CV that produced it
    job_id          TEXT REFERENCES fact_job(job_id),
    client_id       TEXT REFERENCES dim_client(client_id),
    consultant_id   TEXT REFERENCES dim_consultant(consultant_id),
    market          TEXT,
    start_date      DATE NOT NULL,
    gp              NUMERIC(14,2) NOT NULL,
    placement_type  TEXT CHECK (placement_type IN ('perm','contract')),
    fell_off        BOOLEAN DEFAULT FALSE,
    split_pct       NUMERIC(5,2) DEFAULT 100.0   -- split desks change every per-head number
);

CREATE TABLE IF NOT EXISTS fact_activity (
    activity_date   DATE NOT NULL,
    consultant_id   TEXT REFERENCES dim_consultant(consultant_id),
    client_id       TEXT,
    market          TEXT,
    action          TEXT CHECK (action IN ('call','connect','email','client_meeting','linkedin')),
    cnt             INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS ix_stage_date    ON fact_stage_event (event_date);
CREATE INDEX IF NOT EXISTS ix_stage_sub     ON fact_stage_event (submission_id);
CREATE INDEX IF NOT EXISTS ix_stage_market  ON fact_stage_event (market, stage, event_date);
CREATE INDEX IF NOT EXISTS ix_place_date    ON fact_placement (start_date);
CREATE INDEX IF NOT EXISTS ix_place_market  ON fact_placement (market, start_date);
CREATE INDEX IF NOT EXISTS ix_act_date      ON fact_activity (activity_date, consultant_id);

-- Headcount by month. Everyone forgets this table and then cannot tell "the market grew"
-- apart from "we put more people on it" (docs/06 item 2.5).
CREATE OR REPLACE VIEW v_headcount_month AS
SELECT m.month, c.market, COUNT(*) AS active_consultants
FROM   dim_consultant c
CROSS  JOIN (SELECT DISTINCT DATE_TRUNC('month', event_date) AS month FROM fact_stage_event) m
WHERE  c.start_date <= m.month
  AND (c.end_date IS NULL OR c.end_date >= m.month)
GROUP  BY m.month, c.market;

-- The funnel, at monthly grain. Every ratio in docs/03 divides two columns of this view.
CREATE OR REPLACE VIEW v_funnel_month AS
SELECT DATE_TRUNC('month', event_date) AS month,
       market, consultant_id, client_id, placement_type,
       COUNT(*) FILTER (WHERE stage = 'cv_sent')           AS cvs_sent,
       COUNT(*) FILTER (WHERE stage = 'first_interview')   AS first_interviews,
       COUNT(*) FILTER (WHERE stage = 'further_interview') AS further_interviews,
       COUNT(*) FILTER (WHERE stage = 'offer')             AS offers
FROM   fact_stage_event
GROUP  BY 1,2,3,4,5;

-- Cohort view: attribute the outcome to the period of the CV, not of the placement.
-- Within-period ratios are only valid in a steady state (docs/03 section 4.2).
CREATE OR REPLACE VIEW v_cv_cohort AS
SELECT e.submission_id,
       DATE_TRUNC('month', e.event_date) AS cv_month,
       e.market, e.consultant_id, e.client_id,
       p.placement_id IS NOT NULL AND NOT COALESCE(p.fell_off, FALSE) AS placed,
       p.gp,
       CASE WHEN p.start_date IS NOT NULL
            THEN p.start_date - e.event_date END AS days_to_placement
FROM   fact_stage_event e
LEFT   JOIN fact_placement p ON p.submission_id = e.submission_id
WHERE  e.stage = 'cv_sent';
