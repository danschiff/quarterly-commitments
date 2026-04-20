# Plan: Jira Cache + Initiative Field + Work Filter

Two coordinated changes to `main.py` only. `jira_client.py`, `config.yaml`, `report.py`, `progress.py`, and `slack_client.py` are untouched.

> **Diagnostic finding (Phase 0 complete):** `customfield_10018` returns `None` for all epics in this Jira instance. The `parent` field is the correct and already-working source of initiative data. Phase 1 (field swap) is skipped.

---

## Phase 0 — Diagnostic ✅ COMPLETE

**Result:** `customfield_10018` returns `None` for all epics. The `parent` field is already used and working correctly in `fetch_committed_epics()`. No changes needed to `jira_client.py` or `config.yaml`.

`tests/_diag_cf10018.py` is retained in the repo as a permanent debugging aid.

---

## Phase 1 — Swap initiative field ⏭ SKIPPED

`parent` field confirmed as the correct initiative source. No changes needed.

---

## Phase 2 — JSON data cache (`main.py`)  ← START HERE

**Step 2a:** Add imports: `import json`, `import argparse`, `from datetime import datetime`

**Step 2b:** Add `fetch_raw_data(config)` — fetches all epics + children, returns:
```json
{
  "fetched_at": "2026-04-20T14:30:00",
  "teams": [
    {
      "name": "Recruiting",
      "team_field_value": "Recruiting",
      "em_slack_id": "...",
      "sem_slack_id": "...",
      "epics": [
        {
          "key": "RC-1955",
          "summary": "...",
          "initiative_key": "PCS-3271",
          "initiative_summary": "AI Ignite...",
          "children": [
            {"key": "RC-2001", "summary": "...", "status_category": "done", "story_points": 3.0}
          ]
        }
      ]
    }
  ]
}
```

This function contains the team-grouping + unmatched-warning logic currently in `build_team_summaries`.

**Step 2c:** Add `save_raw_data(data, path)` and `load_raw_data(path)` using `json.dumps/loads` with `encoding="utf-8"`.

**Step 2d:** Add `argparse` to `main()`:
- `--refresh` flag: force re-fetch even if today's file exists
- `--data FILE`: optional override of the data file path (defaults to `data-YYYY-MM-DD.json`)

**Step 2e:** `main()` decision logic:
```
if --refresh OR data file does not exist:
    raw_data = fetch_raw_data(config)
    save_raw_data(raw_data, data_path)
    print(f"Data saved to {data_path}")
else:
    raw_data = load_raw_data(data_path)
    print(f"Using cached data from {data_path}")
```

**Step 2f:** Add `build_summaries_from_raw(raw_data, config, quarter_pct)` — receives pre-fetched data, calls `epic_progress()` + `is_slipping()`, applies filter (Phase 3), returns the same summary structure `print_report()` expects.

**Step 2g:** Remove old `build_team_summaries()`.

---

## Phase 3 — Filter epics with no completed work

Applied inside `build_summaries_from_raw()` after computing `epic_progress(children)`:

```python
prog = epic_progress(epic_data["children"])

# Exclude epics where no work has been completed yet
if prog["done_issues"] == 0:
    continue
```

**Key decisions:**
- Filter is at **report-build time** — the raw JSON retains all epics for auditing
- Threshold is `done_issues == 0` (not `done_pts == 0`), so unestimated-but-in-progress work is preserved when at least one issue is Done
- Epics that are 100% done **remain** in the report — "celebrate progress"

---

## Phase 4 — Test updates (`tests/test_jira_client.py`)

**Step 4a:** Add `initiative_field: "customfield_10018"` to `BASE_CONFIG` in the test file.

**Step 4b:** Update `_make_raw_epic` helper to emit `customfield_10018` instead of `parent`.

**Step 4c:** Update `test_returns_mapped_epics` expected dict to include `initiative_key` and `initiative_summary` keys.

**Step 4d:** Add `TestInitiativeFieldValue` test class with 4 cases: `None`, bare string, dict with summary, dict without summary.

**Step 4e:** Add test asserting `customfield_10018` appears in the Jira fields list (not `parent`).

---

## Files Changed

| File | Change |
|---|---|
| `main.py` | Add argparse, `fetch_raw_data`, JSON save/load, `build_summaries_from_raw` with filter; remove `build_team_summaries` |
| `tests/test_jira_client.py` | Update `BASE_CONFIG` and mapped-epics test to match current 5-key return shape |
| `tests/_diag_cf10018.py` | Already created — diagnostic script, no further changes |
| `config.yaml` | **No changes** |
| `jira_client.py` | **No changes** |
| `report.py` | **No changes** |
| `progress.py` | **No changes** |

---

## Verification

1. ~~Run `python tests/_diag_cf10018.py`~~ ✅ Done — `parent` field confirmed correct
2. `pytest tests/test_jira_client.py tests/test_progress.py -v` — all pass
3. `python main.py --refresh` → fetches Jira, writes `data-2026-04-20.json`, prints report + markdown
4. `python main.py` (no flag, same day) → prints "Using cached data…", no Jira HTTP calls
5. Confirm epics with 0 done issues absent from output (cross-check a few against previous report)
6. Initiative grouping unchanged from current output (still parent-based)

---

## Risks

| Risk | Mitigation |
|---|---|
| Filtering removes too many epics early in quarter | By design — run with `--refresh` at start of week; add `--no-filter` flag later if needed |
| Stale cache masks Jira changes mid-week | `--refresh` re-fetches; date-based naming means each new day starts with no cache |
