# Plan: Multi-EM Support Per Team

Allow a team to have multiple engineering managers, each paired with their own senior EM, while still producing a single report per team and a single Slack draft that @-mentions every relevant manager (deduped). Backward compatible with the existing single-EM config.

## Approach

Introduce an optional `managers: [{em_slack_id, sem_slack_id}, ...]` list on team config entries. When present it wins; when absent, synthesize a one-entry list from the existing `em_slack_id`/`sem_slack_id` fields. Normalize to this list shape everywhere internally so downstream code (cache, report, draft) handles one or many uniformly.

## Phase 1 — Config normalization

- **`main.py`** (new helper near top-level, e.g. `_team_managers(team_cfg)`):
  - If `team_cfg` has a truthy `managers` list, return it as-is.
  - Else wrap the legacy `em_slack_id`/`sem_slack_id` into a single-element list.
- Use this helper inside `fetch_raw_data()` to replace the two fields with a single `managers` field in the raw JSON schema.
- Update the schema docstring in `fetch_raw_data()` accordingly.

## Phase 2 — Cache schema + summaries

- **`main.py` `build_summaries_from_raw()`**:
  - Read `managers` from `team_data`; if missing (older cache file), synthesize from legacy fields for backward compat.
  - Replace the two fields on the appended summary dict with `"managers": [...]`.

## Phase 3 — `draft_message()` rewrite

- **`slack_client.py`**: change signature to `draft_message(team_name, managers, slipping_epics, quarter_pct, unestimated_epics=None)`.
  - Build a deduped, order-preserving list of Slack IDs: all `em_slack_id`s first (in config order), then each unique `sem_slack_id` not already present.
  - Render greeting with natural English joining: 1 → `<@A>`; 2 → `<@A> and <@B>`; 3+ → `<@A>, <@B>, and <@C>`.
  - Rest of body unchanged.

## Phase 4 — Report call sites

Three call sites in **`report.py`** currently pass `em_slack_id=` + `sem_slack_id=`. Replace each with `managers=team["managers"]`:
- `_render_team_lines()` (~line 124)
- `print_report()` draft block (~line 218)
- `write_slack_drafts()` (~line 365)

Three display lines print `DM <@EM> and <@SEM>`:
- `_render_team_lines()` (~line 139) — markdown
- `print_report()` (~line 236) — console
- `write_slack_drafts()` (~line 386) — markdown

Add a module-level helper `_format_dm_ids(managers)` in `report.py` that returns `` `<@A>` `` / `` `<@A>` and `<@B>` `` / `` `<@A>`, `<@B>`, and `<@C>` `` (deduped, EMs first). Use it at all three sites.

## Phase 5 — Config update

- **`config.yaml`**: convert Recruiting to the new schema with a TODO placeholder for Cory:
  ```yaml
  - name: "Recruiting"
    team_field_value: "Recruiting"
    managers:
      - em_slack_id:  "U0EG2DG5U"
        sem_slack_id: "U0ADRG6EZ37"
      - em_slack_id:  "TODO_CORY_SLACK_ID"
        sem_slack_id: "U0ADRG6EZ37"
  ```
  Remove the old `em_slack_id`/`sem_slack_id`/`# missing Cory here` lines for Recruiting only.
- Update the header comment to document both forms.
- Leave the other 7 teams on the legacy single-EM form (still supported).

## Phase 6 — Verification

1. `pytest tests/ -q` — all 49 tests must still pass.
2. `python main.py` against cached data — confirm:
   - Recruiting per-team report DM line shows all three Slack IDs.
   - `slack-drafts-2026-04-20.md` Recruiting greeting reads `Hi <@U0EG2DG5U>, <@TODO_CORY_SLACK_ID>, and <@U0ADRG6EZ37>,`.
   - Other 7 teams render identically to today.
3. `python main.py --refresh` — confirm fresh fetch writes `managers` into the cache JSON.
4. Simulate older cache (remove `managers` from a copy) — confirm legacy fallback works.

## Relevant files

- `config.yaml` — add `managers` list for Recruiting; comment both forms.
- `main.py` — add `_team_managers()` helper; update `fetch_raw_data()` schema + docstring; update `build_summaries_from_raw()` to read `managers` with legacy fallback.
- `slack_client.py` — rewrite `draft_message()` signature + greeting rendering.
- `report.py` — replace 3 call-site pairs with `managers=`; add `_format_dm_ids()` helper and use at 3 display sites.
- `tests/` — no changes expected; spot-check after.

## Decisions

- **Greeting format**: Single "Hi" line, EMs in config order first, then unique SEMs; joined with commas and "and".
- **Schema**: Additive/optional `managers` list. Legacy `em_slack_id`/`sem_slack_id` still supported.
- **Cache**: Store normalized `managers` list; tolerate older caches via fallback.
- **Recruiting second EM**: Placeholder `TODO_CORY_SLACK_ID` — user will replace later.
- **Out of scope**: Per-team report filenames/structure unchanged. Summary footer still keyed by team. No extra schema validation beyond Python's natural errors.
