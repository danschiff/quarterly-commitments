Good — no workspace is open, so session memory isn't available. Here's the comprehensive plan:

---

## Plan: Weekly Commitment Tracker (Jira → Slack)

**What & Why:** A Python script you run manually each week that pulls committed epics from Jira, computes progress per team, flags slippage using a linear burn-down model, and for any slipping team opens a pre-drafted Slack group DM (EM + Senior EM) with one click.

---

### Project Structure
```
commitment-tracker/
├── config.yaml        # credentials (via env vars), quarter dates, team→EM/SEM map
├── jira_client.py     # Jira REST API calls
├── progress.py        # burn-down math + slippage detection
├── slack_client.py    # Slack conversations.open + deep link generation
├── report.py          # terminal report formatter
├── requirements.txt   # requests, pyyaml
└── main.py            # orchestration
```

---

### Steps

**Phase 1 — Config & Scaffolding**
1. Create `requirements.txt` (`requests`, `pyyaml`)
2. Create `config.yaml` with full schema and inline comments:
    - Jira: base URL, email, API token env var name, `committed_quarter_field` (`cf[11245]`), team field `cf[10817]`, story points field, current quarter label, epic-link mode (`parent` for next-gen boards, `epic_link` for classic)
   - Slack: bot token env var name, workspace ID
   - Quarter: `start` / `end` dates
   - `slippage_threshold: 0.10`
   - 7 team entries, each with `name`, `team_field_value`, `em_slack_id`, `sem_slack_id`

**Phase 2 — Jira Client** (`jira_client.py`)

3. `fetch_committed_epics(config)` — JQL: `issuetype = Epic AND cf[11245] = "{current_quarter}"`, paginated via `nextPageToken`, returns list of `{key, summary, team_field_value}`
4. `fetch_epic_children(config, epic_key)` — JQL: `parent = EPIC_KEY` (next-gen) or `"Epic Link" = EPIC_KEY` (classic), fetches `status.statusCategory.key` + `customfield_10016` (story points) for each child ticket. Handles pagination.

**Phase 3 — Progress Math** (`progress.py`) *(no dependencies)*

5. `quarter_pct_elapsed(config)` → `(today − quarter_start) / (quarter_end − quarter_start)`
6. `epic_progress(children)` → `{done_pts, total_pts, pct_complete}` — "done" = `status.statusCategory.key == "done"`
7. `is_slipping(epic_pct, quarter_pct, threshold)` → bool; epics with 0 total points tagged "unestimated" (not auto-flagged)

**Phase 4 — Slack Client** (`slack_client.py`) *(depends on Phase 1)*

8. `open_group_dm(bot_token, em_id, sem_id)` — POST to `conversations.open` with `users="EM_ID,SEM_ID"`, returns `channel_id`
9. `make_deep_link(workspace_id, channel_id)` → `slack://channel?team={T...}&id={C...}` (opens native Slack); also produce `https://slack.com/app_redirect?channel={channel_id}&team={workspace_id}` as browser fallback
10. `draft_message(team_name, slipping_epics, quarter_pct)` → fills in a templated message asking the three questions (on track?, blockers?, need help?)

**Phase 5 — Report** (`report.py`) *(depends on Phases 2–4)*

11. `print_report(team_summaries)` — terminal output:
    - Header: today's date + `N% through Q2 2026`
    - One section per team: list of epics with `[████░░░░] 42% (21/50 pts)` style progress, `⚠ SLIPPING` flag where applicable
    - For each slipping team: print draft message text + deep link

**Phase 6 — Orchestration** (`main.py`)

12. Load config; resolve env vars for API tokens (never log them)
13. Compute `quarter_pct`
14. Fetch all committed epics → group by `cf[10817]` value matched to config teams
15. For each team: fetch children per epic → compute progress → detect slippage
16. For slipping teams: call `open_group_dm` → generate deep link
17. Call `print_report`

---

### Relevant Technical Notes
- **Jira auth**: HTTP Basic with `email:api_token`, base64-encoded; use `JIRA_API_TOKEN` env var
- **Jira API**: `POST /rest/api/3/search/jql` (current, non-deprecated endpoint)
- **Committed Quarter field ID**: Set to `cf[11245]`
- **Slack bot scopes needed**: `conversations:write`, `im:write`, `mpim:write` (for `conversations.open`)
- **Deep link format**: `slack://channel?team={TEAM_ID}&id={CHANNEL_ID}` — clicking opens native Slack directly in that group DM

---

### Verification
1. Run against a Jira project with known test epics; verify story point totals match Jira UI
2. Confirm slippage logic: at 50% through quarter, an epic at 35% complete → flags (15% gap > 10% threshold); at 42% complete → does not flag (8% gap ≤ 10%)
3. Confirm env vars are never printed in output
4. Click a generated deep link and verify it opens the correct Slack group DM

---

### Decisions & Scope
- Secrets via environment variables only — never stored in `config.yaml`
- No scheduler built in; run manually or add to Windows Task Scheduler if desired
- Story points field defaults to `customfield_10016`; one config value to override
- Epics with 0 total story points are reported as "unestimated," not slipping
- The draft message is printed to terminal; you copy-paste after clicking the deep link to open the DM

---

The committed quarter field ID is `cf[11245]`. Everything else is ready for refinement or implementation.