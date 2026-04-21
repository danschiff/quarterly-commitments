# Quarterly Commitments Tracker

A weekly check-in tool that pulls committed epics for the current quarter from Jira, compares each epic's burn-down against the linear time-elapsed target, and generates ready-to-paste Slack draft messages for teams that need a nudge.

## What it does

Every week the team delivery manager needs to answer: *which teams are falling behind on what they committed to this quarter, and which epics haven't been sized yet?* This tool automates that check.

For each configured team it:

1. Finds every Epic marked as committed for the current quarter (via a Jira custom-field filter).
2. Walks each Epic's child issues and sums up done vs. total story points.
3. Compares the epic's `% complete` against `% of quarter elapsed`:
   - **Unestimated** — the epic has no story-point estimates at all.
   - **Slipping** — the epic is more than `slippage_threshold` (default 10 pp) behind the linear target.
   - **On track** — everything else, including 100% complete.
4. Filters out epics where no child work has started yet (noise).
5. Renders four artifacts so you can skim quickly and act:
   - Console report
   - Combined Markdown report: `report-YYYY-MM-DD.md`
   - One Markdown file per team in `reports/YYYY-MM-DD/`
   - A separate Slack-drafts file (`slack-drafts-YYYY-MM-DD.md`) that contains a paste-ready DM for every team with slipping or unestimated epics, @-mentioning each team's EM(s) and SEM.

Raw Jira data is cached to `data-YYYY-MM-DD.json` so subsequent runs the same day are instant and don't hit the API. Use `--refresh` to force a re-fetch.

## How it works (brief)

| File | Role |
|------|------|
| `main.py` | Orchestration: CLI args, config loading, cache read/write, wiring everything together. |
| `jira_client.py` | Thin Jira REST wrapper — fetches committed epics and their children via JQL. |
| `progress.py` | Pure functions: `quarter_pct_elapsed()`, `epic_progress()`, `is_slipping()`. No I/O. |
| `slack_client.py` | Builds the Slack draft message text (with @-mentions). No bot token required. |
| `report.py` | All rendering — console, combined Markdown, per-team Markdown, Slack-drafts file. |
| `config.yaml` | Jira connection, quarter window, slippage threshold, team roster, managers. |
| `tests/` | `pytest` suite covering progress math, slippage thresholds, and the Jira client (with mocked HTTP). |

The core "is this slipping?" rule lives in `progress.is_slipping()`:

```
is_slipping  ⇔  (quarter_pct - epic_pct)  >  threshold
```

Unestimated epics (`total_pts == 0`) are flagged separately so they're surfaced for sizing rather than mis-labeled as slipping.

## Getting started

### Prerequisites

- Python 3.11+
- A Jira Cloud account with an API token ([generate one here](https://id.atlassian.com/manage-profile/security/api-tokens))
- PowerShell (examples below), bash, or zsh

### 1. Clone and install

```powershell
git clone <repo-url> quarterly-commitments
cd quarterly-commitments
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure

Edit `config.yaml`:

- `jira.base_url` / `jira.email` — your Jira Cloud instance and account.
- `jira.current_quarter` — the exact dropdown value used for the "Committed Quarter" custom field (e.g. `"FY26 Quarter 4"`).
- `jira.committed_quarter_field` / `jira.team_field` / `jira.story_points_field` — custom field IDs for your Jira instance.
- `quarter.start` / `quarter.end` — ISO dates bounding the current quarter.
- `slippage_threshold` — fraction behind linear target before an epic is flagged (0.10 = 10 pp).
- `teams` — one entry per team. Each team needs:
  - `name` — display name used in reports.
  - `team_field_value` — exact value in the Jira team custom field.
  - Either:
    - **Single manager** (legacy): `em_slack_id` + `sem_slack_id`.
    - **Multiple managers**: a `managers:` list of `{em_slack_id, sem_slack_id}` entries (EMs are listed first in the @-mention greeting, SEMs are deduped after).

To find a Slack user ID: open the person's profile → **…** menu → **Copy member ID**.

### 3. Set your Jira API token

```powershell
$env:JIRA_API_TOKEN = "your-token-here"
```

(Persist it via **System Properties → Environment Variables** or a shell profile.)

### 4. Run

```powershell
python main.py
```

First run of the day hits Jira and writes `data-YYYY-MM-DD.json`. Subsequent runs reuse the cache.

Useful flags:

- `python main.py --refresh` — re-fetch from Jira even if today's cache exists.
- `python main.py --data path/to/data.json` — load an explicit cache file (handy for reruns across midnight).

Outputs land in the repo root and `reports/YYYY-MM-DD/`.

### 5. Run the tests

```powershell
python -m pytest tests/ -q
```

## Weekly workflow

1. `python main.py`
2. Skim the console "ACTION NEEDED" footer.
3. Open `slack-drafts-YYYY-MM-DD.md`, copy the block for each team that needs outreach, and paste into Slack.
4. Share `report-YYYY-MM-DD.md` (or a specific per-team file under `reports/YYYY-MM-DD/`) with stakeholders as needed.

## Output formats

- **Console** — color-free progress bars, slipping/unestimated flags, summary footer.
- **`report-YYYY-MM-DD.md`** — one big Markdown report covering all teams.
- **`reports/YYYY-MM-DD/<team>.md`** — per-team Markdown for sharing individually.
- **`slack-drafts-YYYY-MM-DD.md`** — only the draft messages, grouped by team, each in a fenced code block ready to copy.
- **`data-YYYY-MM-DD.json`** — raw Jira cache (safe to delete; will be re-fetched).

## Keeping this README current

Whenever you ship an enhancement, update the relevant section above:

- New behavior or new flag? → update **What it does**, **Getting started → Run**, or **Output formats**.
- New module or significant refactor? → update the **How it works** table.
- New config key? → document it in **Getting started → Configure** and add a commented example in `config.yaml`.
- Breaking change to config or output paths? → call it out near the top of **What it does** so first-time readers see it.

A good heuristic: if someone cloning the repo a year from now would be confused without the change, the README needs an edit.
