"""Slack integration helpers.

Currently only draft_message() is implemented — no bot token required.
When a SLACK_BOT_TOKEN becomes available, uncomment and complete
open_group_dm() and make_deep_link() to enable one-click DM opening.
"""


def draft_message(team_name, em_slack_id, sem_slack_id, slipping_epics, quarter_pct, unestimated_epics=None):
    """Return a ready-to-paste Slack message for a team needing attention.

    The <@USER_ID> syntax renders as a clickable @mention when pasted
    into any Slack message box.

    Args:
        team_name:         str   — display name of the team
        em_slack_id:       str   — Slack user ID of the Engineering Manager
        sem_slack_id:      str   — Slack user ID of the Senior Engineering Manager
        slipping_epics:    list  — epic dicts with keys "key" and "summary"
        quarter_pct:       float — fraction of quarter elapsed (e.g. 0.211)
        unestimated_epics: list  — epic dicts with keys "key" and "summary" (optional)

    Returns:
        str
    """
    if unestimated_epics is None:
        unestimated_epics = []

    pct_str = f"{quarter_pct * 100:.0f}%"
    parts = []

    parts.append(
        f"Hi <@{em_slack_id}> and <@{sem_slack_id}>,\n\n"
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
