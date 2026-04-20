# Plan: Separate Slack Drafts from Reports

Remove draft Slack message blocks from all markdown report files and consolidate them into a single `slack-drafts-YYYY-MM-DD.md` at the project root.

---

## Phase 1 — Gate drafts in `_render_team_lines()` (`report.py`)

**Step 1:** Add `include_draft=False` keyword-only param to `_render_team_lines()`.

**Step 2:** Gate the draft block on the new param:
```python
# before
if team["any_slipping"]:
# after
if include_draft and team["any_slipping"]:
```

All existing callers (`write_markdown_report` inner loop, `write_team_markdown_report`) pass no argument, so drafts are automatically suppressed everywhere.

---

## Phase 2 — Add `write_slack_drafts()` to `report.py`

**Step 3:** Add `write_slack_drafts(team_summaries, quarter_pct, config, path=None)`:

- Default path: `slack-drafts-YYYY-MM-DD.md` in cwd
- Structure:
  ```
  # Draft Slack Messages
  **Date:** … | **Quarter:** …
  **Quarter elapsed:** 21.1%

  4 team(s) require outreach.

  ---

  ## Recruiting
  DM `<@U0EG2DG5U>` and `<@U0ADRG6EZ37>`
  ```<draft message>```

  ---

  ## Learning Management
  …
  ```
- If no slipping teams: single line `"All teams on track — no outreach needed this week. ✓"`
- Returns `Path`

---

## Phase 3 — Wire into `main.py`

**Step 4:** Add `write_slack_drafts` to the import from `report`.

**Step 5:** Call after `write_per_team_reports()`:
```python
drafts_path = write_slack_drafts(summaries, quarter_pct, config)
print(f"Slack drafts written to: {drafts_path.resolve()}")
```

---

## Files Changed

| File | Change |
|---|---|
| `report.py` | Add `include_draft` param to `_render_team_lines()`; add `write_slack_drafts()` |
| `main.py` | Add `write_slack_drafts` to import; call + print after `write_per_team_reports()` |

---

## Verification

1. `pytest tests/ -v` — all 49 tests pass
2. `python main.py` — produces:
   - `report-2026-04-20.md` — combined report, no draft sections
   - `reports/2026-04-20/*.md` — 8 per-team files, no draft sections
   - `slack-drafts-2026-04-20.md` — drafts for the 4 slipping teams only
3. Spot-check `reports/2026-04-20/recruiting.md` — ends after last initiative table, no `Draft Slack message` block
4. Spot-check `slack-drafts-2026-04-20.md` — has H2 per slipping team, fenced draft message

---

## Decisions

- `slack-drafts-YYYY-MM-DD.md` goes in the project root (not in `reports/`), since it's the action item for the week rather than a reference report
- Combined report (`report-*.md`) also loses its draft sections for consistency
- `include_draft` defaults to `False` — callers must opt in explicitly; currently no caller does
