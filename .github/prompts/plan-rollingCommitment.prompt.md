# Plan: Rolling Commitment Feature

The "Rolling" label lives on the **Initiative** in Jira. Every epic whose parent initiative carries that label inherits `rolling=True`, which overrides Slipping, Not Started, and Unestimated — those epics are shown with a distinct status in reports but fully excluded from Slack outreach.

## Steps

### 1. `jira_client.py` — `fetch_initiatives()`
- Add `"labels"` to `fetch_fields`.
- In the results loop: `rolling = "Rolling" in (f.get("labels") or [])` → store `"rolling": rolling` on each initiative dict.

### 2. `main.py` — `build_summaries_from_raw()`
- Read `rolling = init_data.get("rolling", False)` after resolving `init_data`.
- If `rolling`: force `slipping = False`, `not_started = False`.
- Add `"rolling": rolling` to the enriched epic dict.
- Update `any_needs_attention` and `any_slipping` predicates to gate on `not e["rolling"]`.

### 3. `report.py` — rendering
- **Status label:** add `elif epic.get("rolling"): status = "↺ ROLLING"` in both `_render_team_lines()` and `print_report()`.
- **Counts:** compute `n_rolling`, subtract from `n_on_track`, add to the summary line (`N rolling`).
- **Slack exclusion:** filter `not e.get("rolling")` from `slipping_epics`, `unestimated_epics`, and `not_started_epics` before calling `draft_message()` — in both render paths.

## Relevant files
- `jira_client.py` — `fetch_initiatives()`: add `labels` field, set `rolling` bool
- `main.py` — `build_summaries_from_raw()`: propagate `rolling`, update attention predicates
- `report.py` — status label, counts, Slack list filtering

## Verification
1. Find a real initiative in Jira with label "Rolling" — confirm all its child epics show "↺ ROLLING" in console and Markdown.
2. Confirm no Rolling epics appear in any section (slipping / unestimated / not started) of the Slack draft.
3. Confirm the team summary line shows a separate `N rolling` bucket.
4. An epic under a non-Rolling initiative that is behind target still shows "⚠ SLIPPING" (regression check).
5. Add a unit test covering `rolling=True` suppressing all three flags in the enriched epic dict.

## Decisions
- Tag is checked on the Initiative only; epics inherit it from their parent.
- Rolling suppresses Slipping, Not Started, **and** Unestimated in Slack.
- Rolling epics remain visible in the report table with "↺ ROLLING" status.
- No config key needed — "Rolling" is a hardcoded label name (convention-based).
