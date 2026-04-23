# Plans: enhancements/2026-4-23.md

Four independent enhancements to the quarterly-commitments tool. Each has its own plan; they share some infrastructure (initiative fetch, extra custom fields) so a common "Foundation" step is noted where relevant. Order of implementation: Foundation → #1 → #3 → #2 → #4 (because #4 depends on #2's rolling-epic filter and on foundation fetches).

Shared answers from user:
- Rolling tag label literal = `"Rolling"` (configurable).
- Start Date = `customfield_10015`.
- Hasn't Started = **epic-level** replacement for Slipping.
- Hasn't Started → its **own section** in the Slack draft.
- Committed marker = emoji badge prefix on initiative heading.
- Committed-quarter match = use the `committed_quarter_field` value already configured (one of the committed epics is guaranteed to be in that quarter; so any initiative whose `customfield_11245` equals that configured value is "this-quarter committed").
- Health = new column in epic table + inline on initiative heading.

---

## Foundation (shared prerequisites, do first)

Introduces: initiative bulk fetch, new custom-field plumbing, cache-shape bump.

Steps:
1. In `config.yaml` add commented examples for new keys: `health_field: customfield_10883`, `initiative_committed_field: customfield_11245`, `start_date_field: customfield_10015`, `rolling_commitment_label: Rolling`, `sprint_field: customfield_10020` (needs discovery; see Verification).
2. In `jira_client.py` add `fetch_initiatives(config, keys: set[str]) -> dict[key, dict]` — JQL `key in (...)` (chunked to 50), fields = `[summary, health_field, initiative_committed_field, start_date_field]`. Returns `{key: {summary, committed_quarter, health, start_date}}`.
3. Extend `fetch_committed_epics` field list with `labels` + `health_field`.
4. Extend `fetch_epic_children` field list with `sprint_field`; compute per-child `in_sprint: bool` (sprint list non-empty).
5. In `main.fetch_raw_data`, after epics are fetched, collect unique parent keys and call `fetch_initiatives`; attach an `initiatives` dict to the cached JSON.
6. Bump the JSON cache shape: new top-level keys `initiatives`, and per-child `in_sprint`, per-epic `labels`, `health`. Reads use `.get(..., default)` for back-compat; document that `--refresh` is needed after upgrade.
7. Thread initiative metadata into `build_summaries_from_raw` so each epic carries `initiative_committed_quarter`, `initiative_health`, `initiative_start_date`.

Relevant files:
- `config.yaml` — new keys.
- `jira_client.py` — new `fetch_initiatives`, extend field lists around lines 118-124 and 137-194.
- `main.py` — `fetch_raw_data` JSON shape (lines 110-127); `build_summaries_from_raw`.
- `README.md` — under *Getting started → Configure* document each new key with short description.

Verification:
- Run `python tests/_discover_field_options.py` (or add a small script) to confirm the sprint customfield id on this Jira instance; write the id into `config.yaml`.
- `python main.py --refresh` succeeds and `data-YYYY-MM-DD.json` contains `initiatives`, `labels`, `health`, and children with `in_sprint`.
- Existing unit tests still pass: `pytest tests/test_progress.py tests/test_jira_client.py`.

---

## Plan 1: Mark & prioritize Committed-Quarter initiatives

TL;DR — Any initiative whose `customfield_11245` equals the configured `committed_quarter_field` value is "committed this quarter". Sort those first within each team and prefix the initiative heading with a 🎯 badge.

**Steps** (*depends on Foundation*)
1. In `report.py` `_group_by_initiative` (lines 33-62), change sort key: (a) initiatives with `committed_this_quarter == True` first, (b) then alphabetical by key, (c) `None` parent last.
2. In `report.py` `_render_team_lines` initiative heading renderer, when `committed_this_quarter`, render heading with `🎯 Committed this quarter · ` in line. Mirror in console renderer.
3. Compute `committed_this_quarter` at summary-build time by comparing `initiative_committed_quarter` to the configured committed-quarter value from `config.yaml` (same value already used to filter epics).
4. Update `README.md`: *What it does* notes "this-quarter-committed initiatives are surfaced first with a 🎯 marker"; *Output formats* lists the 🎯 convention.

**Relevant files**
- `main.py` — add `committed_this_quarter` on each epic's initiative record during `build_summaries_from_raw`.
- `report.py` — sort in `_group_by_initiative`; heading render in `_render_team_lines` and console section.
- `README.md` — marker convention + ordering note.

**Verification**
- Unit test in `tests/test_progress.py` (or new `test_report.py`): given two initiatives, committed first regardless of alphabetical order; 🎯 present in heading only for committed.
- Manual: regenerate report and confirm at least one team shows a 🎯 ordering change vs `report-2026-04-21.md`.

**Decisions**
- "Same quarter" = string equality with `config.committed_quarter_field`'s configured option value. No date math.
- Non-committed initiatives retain alphabetical order.

---

## Plan 2: Exclude Rolling-Commitment epics from Slack

TL;DR — If an epic carries the `Rolling` label (configurable), render its status as `↻ Rolling Commitment` instead of `⚠ SLIPPING`, exclude it from Slack drafts, and don't count it toward `any_needs_attention`.

**Steps** (*depends on Foundation step 3: epic labels fetched*)
1. In `build_summaries_from_raw`, set `epic["rolling"] = rolling_label in epic.get("labels", [])` where `rolling_label = config.get("rolling_commitment_label", "Rolling")`.
2. Adjust slipping decision in `main.py` lines 169-172: if `epic["rolling"]` and would-be-slipping, keep `slipping=False` but retain a dedicated `rolling=True` flag (already set). Unestimated still wins over rolling.
3. Update `any_needs_attention` calc at `main.py` line 197: exclude rolling epics from the attention count (rolling epics never trigger Slack).
4. In `report.py` lines 124-130 + 198-204 status cell: if `epic["rolling"]` and slipping-would-be-true → render `↻ Rolling Commitment`. Order: unestimated > rolling > slipping > on-track.
5. In `slack_client.draft_message` input construction (in `report.py` around line 136 and line 335), filter out rolling epics from the slipping list.
6. Update `README.md`: *What it does* adds Rolling Commitment bucket; *Configure* documents `rolling_commitment_label`; *Output formats* adds the ↻ convention.

**Relevant files**
- `main.py` — `build_summaries_from_raw`, slipping decision, `any_needs_attention`.
- `report.py` — status rendering (markdown + console), slack-draft feed filtering.
- `config.yaml`, `README.md`.

**Verification**
- Unit test: epic with slipping progress + `Rolling` label yields status `↻ Rolling Commitment` and is NOT in the slipping list passed to `draft_message`.
- Manual: temporarily add the label to a known epic in the cache JSON, rerun `python main.py`, confirm no Slack entry and correct status cell.

**Decisions**
- Unestimated still overrides Rolling (data quality before categorization).
- Rolling-labeled epics that are on-track render as normal `✓ on track` — the ↻ badge only replaces a Slipping render.

---

## Plan 3: Add Health status from Jira

TL;DR — Surface `customfield_10883` (Health) on both initiatives and epics — new table column on epic rows, inline tag on initiative headings.

**Steps** (*depends on Foundation steps 2-3*)
1. In `build_summaries_from_raw`, copy `health` onto each epic and `initiative_health` onto initiative record.
2. In `report.py` `_render_team_lines` epic table: add a `Health` column between Status and Progress. Empty cell (`—`) if missing.
3. Render health inline on initiative heading as a small tag: `— Health (from Jira): On Track` (or whatever the Jira value is). Use a muted emoji per common value: On Track ✅, At Risk ⚠, Off Track 🛑, default none. If there is no value, and the intiative has been tagged as `Committed this quarter`, use the tag: `— Missing Jira Health Value` with the 🛑 muted emoji.
4. Mirror changes in console renderer.
5. Update `README.md`: *What it does* lists Health visibility; *Configure* documents `health_field`; *Output formats* documents emoji mapping.

**Relevant files**
- `main.py` — summary builder.
- `report.py` — table headers/rows, initiative heading, console renderer (~lines 124-215).
- `config.yaml`, `README.md`.

**Verification**
- Unit test snippet for row renderer: given epic with `health="At Risk"`, row contains `⚠ At Risk`.
- Manual: regenerate and confirm new column in `report-YYYY-MM-DD.md` and per-team files.

**Decisions**
- Health is display-only; does not affect Slipping / attention logic.
- Emoji mapping is hardcoded (small dict); unknown values render as plain text.

---

## Plan 4: Mark epics that haven't started

TL;DR — Replace `⚠ SLIPPING` with `🕗 Hasn't Started` when an epic shows no real activity: (a) its initiative's Start Date has passed (or isn't set but other team epics are progressing), AND (b) none of the epic's child issues are assigned to a sprint. Put these in their own section in the Slack draft.

**Steps** (*depends on Foundation steps 2-4; interacts with Plan 2*)
1. In `build_summaries_from_raw`, compute per-epic `hasnt_started = (no child has in_sprint == True) AND (initiative_start_date is set and < today OR initiative_start_date is None)`. (Today = the tool's "as of" date, same one already used for quarter-pct.)
2. Remove (or conditionalize) the `done_issues == 0` drop at `main.py` line 164 — those epics must now be retained so they can be flagged `hasnt_started`. Keep drop only if epic has no children at all.
3. Status precedence in `report.py` lines 124-130 + 198-204: unestimated > rolling > hasnt_started > slipping > on-track. So `hasnt_started` replaces a would-be-Slipping label.
4. In `any_needs_attention`, include `hasnt_started` (manager attention needed).
5. In Slack draft construction (slack_client.py + report.py slack sections), add a third bucket alongside slipping/unestimated: `not_started_epics`. Update `draft_message` signature and template to render a "Haven't started yet" section.
6. Update `README.md`: *What it does* adds Hasn't Started bucket; *How it works* explains the two-signal rule; *Configure* documents `start_date_field` and `sprint_field`; *Output formats* shows the 🕗 marker and new Slack section.

**Relevant files**
- `main.py` — `build_summaries_from_raw`, attention calc, removal of `done_issues == 0` drop (line 164).
- `jira_client.py` — already extended in Foundation for sprint + start date.
- `report.py` — status rendering (both renderers), slack draft inputs (~line 136, 335).
- `slack_client.py` `draft_message` (lines 45-101) — add `not_started_epics` param + section template.
- `config.yaml`, `README.md`.

**Verification**
- Unit tests: (a) epic with no in-sprint children + initiative start-date in past → `hasnt_started` and status renders 🕗; (b) same epic also slipping → still renders 🕗 (precedence); (c) `draft_message` output contains "Haven't started" section.
- Manual: find an epic in current cache where children lack sprint assignment, regenerate report and slack draft, confirm separation.

**Decisions**
- Hasn't Started is epic-level (per user), but signal is derived from initiative's start-date + epic's own children.
- If initiative start-date is in the future, epic is NOT flagged (nothing expected yet).
- `done_issues == 0` is no longer a silent filter; those epics now surface (either as on-track, slipping, or hasn't-started depending on signals).

**Further Considerations**
1. If an initiative has no start date AND no sibling activity, should we skip flagging? Current plan flags it on the assumption "should have started by now". Alternative: require explicit start-date to avoid false positives. Recommend the current approach and revisit after first run.
