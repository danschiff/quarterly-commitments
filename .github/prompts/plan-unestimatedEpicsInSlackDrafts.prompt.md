# Plan: Include Unestimated Epics in Slack Drafts

Refine the draft Slack message to highlight both slipping and unestimated epics. Teams with unestimated committed epics should be told that anything committed for the quarter should have estimates.

---

## Phase 1 — Update `draft_message()` in `slack_client.py`

**Step 1:** Add `unestimated_epics=None` param to `draft_message()`.

**Step 2:** Rewrite the message body to have two optional sections:
- **Slipping section** (if `slipping_epics` is non-empty): *"The following commitment(s) are currently behind the expected burn-down rate:"* + bullet list
- **Unestimated section** (if `unestimated_epics` is non-empty): *"The following commitment(s) don't have story point estimates yet. Anything committed for the quarter should be estimated so we can track progress:"* + bullet list

The greeting, closing questions, and sign-off remain unchanged.

---

## Phase 2 — Add `any_needs_attention` field in `main.py`

**Step 3:** In `build_summaries_from_raw()`, add a new field to each team summary:
```python
"any_needs_attention": any(
    e["slipping"] or e["progress"]["unestimated"]
    for e in enriched
),
```

Keep `any_slipping` for backward compatibility (report status counts still use it).

---

## Phase 3 — Update callers in `report.py`

**Step 4:** In `print_report()`, change the draft trigger from `if team["any_slipping"]` to `if team["any_needs_attention"]`. Pass both lists:
```python
slipping_epics = [e for e in epics if e["slipping"]]
unestimated_epics = [e for e in epics if e["progress"]["unestimated"]]
msg = draft_message(..., slipping_epics=..., unestimated_epics=...)
```

**Step 5:** In `_render_team_lines()`, same change for the `include_draft` path: trigger on `any_needs_attention`, pass both lists.

**Step 6:** In `write_slack_drafts()`, change the loop filter from `any_slipping` to `any_needs_attention`, pass both lists to `draft_message()`.

**Step 7:** Update the summary footer in both `print_report()` and `write_markdown_report()` — the "N team(s) require outreach" count should use `any_needs_attention` instead of `any_slipping`.

---

## Files Changed

| File | Change |
|---|---|
| `slack_client.py` | Add `unestimated_epics` param; rewrite message with two optional sections |
| `main.py` | Add `any_needs_attention` field to team summaries |
| `report.py` | Update 3 callers of `draft_message()` to pass `unestimated_epics`; change trigger conditions from `any_slipping` to `any_needs_attention`; update summary footers |

---

## Verification

1. `pytest tests/ -v` — all tests pass
2. `python main.py` — produces updated `slack-drafts-2026-04-20.md`
3. Spot-check draft for a team with both slipping and unestimated epics (e.g. Learning Management: 3 slipping + 1 unestimated) — message should have both sections
4. Spot-check draft for a team with only unestimated epics (e.g. Performance Management) — message should only have the unestimated section
5. Teams with neither slipping nor unestimated epics should not appear in the drafts file
