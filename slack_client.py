"""Slack integration helpers.

Currently only draft_message() is implemented — no bot token required.
When a SLACK_BOT_TOKEN becomes available, uncomment and complete
open_group_dm() and make_deep_link() to enable one-click DM opening.
"""


def _dedupe_manager_ids(managers):
    """Return a deduped, order-preserving list of Slack IDs: EMs first, then SEMs.

    Each entry in `managers` is a {em_slack_id, sem_slack_id} dict.
    """
    ordered = []
    seen    = set()
    # First pass: EMs in config order
    for m in managers:
        sid = m["em_slack_id"]
        if sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    # Second pass: SEMs not already listed
    for m in managers:
        sid = m["sem_slack_id"]
        if sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered


def _join_mentions(slack_ids):
    """Render a list of Slack IDs as an English-joined <@...> string.

    1 id  -> "<@A>"
    2 ids -> "<@A> and <@B>"
    3+    -> "<@A>, <@B>, and <@C>"
    """
    mentions = [f"<@{sid}>" for sid in slack_ids]
    if len(mentions) == 1:
        return mentions[0]
    if len(mentions) == 2:
        return f"{mentions[0]} and {mentions[1]}"
    return ", ".join(mentions[:-1]) + f", and {mentions[-1]}"


def draft_message(team_name, managers, slipping_epics, quarter_pct,
                  unestimated_epics=None, not_started_epics=None):
    """Return a ready-to-paste Slack message for a team needing attention.

    The <@USER_ID> syntax renders as a clickable @mention when pasted
    into any Slack message box.

    Args:
        team_name:          str   — display name of the team
        managers:           list  — [{em_slack_id, sem_slack_id}, ...] (1 or more)
        slipping_epics:     list  — epic dicts with keys "key" and "summary"
        quarter_pct:        float — fraction of quarter elapsed (e.g. 0.211)
        unestimated_epics:  list  — epic dicts with keys "key" and "summary" (optional)
        not_started_epics:  list  — epic dicts with keys "key" and "summary" (optional)

    Returns:
        str
    """
    if unestimated_epics is None:
        unestimated_epics = []
    if not_started_epics is None:
        not_started_epics = []

    pct_str = f"{quarter_pct * 100:.0f}%"
    greeting_ids = _dedupe_manager_ids(managers)
    greeting = _join_mentions(greeting_ids)
    parts = []

    parts.append(
        f"Hi {greeting},\n\n"
        f"Doing my weekly check-in on quarterly commitments for the *{team_name}* team "
        f"({pct_str} through the quarter)."
    )

    if slipping_epics:
        epic_lines = "\n".join(f"  • {e['key']}: {e['summary']}" for e in slipping_epics)
        parts.append(
            f"The following commitment(s) are currently behind the expected burn-down rate:\n\n"
            f"{epic_lines}"
        )

    if unestimated_epics:
        epic_lines = "\n".join(f"  • {e['key']}: {e['summary']}" for e in unestimated_epics)
        parts.append(
            f"The following commitment(s) don't have story point estimates yet. "
            f"Anything committed for the quarter should be estimated so we can track progress:\n\n"
            f"{epic_lines}"
        )

    if not_started_epics:
        epic_lines = "\n".join(f"  • {e['key']}: {e['summary']}" for e in not_started_epics)
        parts.append(
            f"The following commitment(s) have not been started yet:\n\n"
            f"{epic_lines}"
        )

    parts.append(
        f"A few questions:\n"
        f"  1. Are you still on track to deliver these by end of quarter?\n"
        f"  2. Are there any blockers I should know about?\n"
        f"  3. Is there anything you need help with?\n\n"
        f"Thanks!"
    )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Future: uncomment when SLACK_BOT_TOKEN is available
# ---------------------------------------------------------------------------

# import os
# import requests
#
# def open_group_dm(bot_token, em_id, sem_id):
#     """Open a group DM with the EM and Senior EM; return the channel ID."""
#     resp = requests.post(
#         "https://slack.com/api/conversations.open",
#         headers={"Authorization": f"Bearer {bot_token}",
#                  "Content-Type": "application/json"},
#         json={"users": f"{em_id},{sem_id}"},
#         timeout=10,
#     )
#     resp.raise_for_status()
#     data = resp.json()
#     if not data.get("ok"):
#         raise RuntimeError(f"conversations.open failed: {data.get('error')}")
#     return data["channel"]["id"]
#
# def make_deep_link(workspace_id, channel_id):
#     """Return a slack:// URI that opens the DM directly in the desktop app."""
#     return f"slack://channel?team={workspace_id}&id={channel_id}"
