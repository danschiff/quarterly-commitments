"""Terminal report renderer for the weekly commitment tracker."""

import re
from datetime import date
from pathlib import Path

from slack_client import draft_message, _dedupe_manager_ids

BAR_WIDTH = 20
SEPARATOR = "=" * 70
SUBSEP    = "-" * 70


def _format_dm_ids(managers, backticks=True):
    """Render `<@A>`, `<@B>`, and `<@C>` (or plain <@A>, ...) for all unique managers."""
    ids = _dedupe_manager_ids(managers)
    if backticks:
        mentions = [f"`<@{sid}>`" for sid in ids]
    else:
        mentions = [f"<@{sid}>" for sid in ids]
    if len(mentions) == 1:
        return mentions[0]
    if len(mentions) == 2:
        return f"{mentions[0]} and {mentions[1]}"
    return ", ".join(mentions[:-1]) + f", and {mentions[-1]}"


def _progress_bar(pct, width=BAR_WIDTH):
    filled = round(pct * width)
    return "[" + "\u2588" * filled + "\u2591" * (width - filled) + "]"


def _group_by_initiative(epics):
    """Return epics grouped by initiative, preserving encounter order.

    Returns a list of (initiative_key, initiative_summary, [epics]) tuples.
    Epics with no parent initiative are grouped last under (None, None, ...).
    """
    order = []        # preserves first-seen order of initiative keys
    groups = {}       # initiative_key -> {"summary": str, "epics": list}

    for epic in epics:
        ikey = epic.get("initiative_key")
        if ikey not in groups:
            order.append(ikey)
            groups[ikey] = {
                "summary": epic.get("initiative_summary"),
                "epics": [],
            }
        groups[ikey]["epics"].append(epic)

    # Sort: named initiatives first (alphabetically by key), None last
    named = sorted(
        (k for k in order if k is not None),
        key=lambda k: k or ""
    )
    order_sorted = named + ([None] if None in groups else [])

    return [
        (k, groups[k]["summary"], groups[k]["epics"])
        for k in order_sorted
    ]


def _slugify(name):
    """Convert a team name to a filesystem-safe slug.

    e.g. "Learning Management"   -> "learning-management"
         "Recognition & Rewards" -> "recognition-and-rewards"
    """
    slug = name.lower()
    slug = re.sub(r"&", "and", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _render_team_lines(team, quarter_pct, config, *, initiative_hlevel=3, include_draft=False):
    """Return a list[str] of markdown lines for one team's body section.

    Does NOT include the team-name heading — the caller writes that.

    Args:
        team:              team summary dict
        quarter_pct:       float — fraction of the quarter elapsed
        config:            parsed config dict
        initiative_hlevel: heading level for initiative headings
                           (3 in combined report, 2 in per-team files)
        include_draft:     if True, append the draft Slack message block
    """
    base_url          = config["jira"]["base_url"].rstrip("/")
    epics             = team["epics"]
    n_slipping        = sum(1 for e in epics if e["slipping"])
    n_unestimated     = sum(1 for e in epics if e["progress"]["unestimated"])
    n_on_track        = len(epics) - n_slipping - n_unestimated
    initiative_prefix = "#" * initiative_hlevel

    lines = []

    def w(text=""):
        lines.append(text)

    w(f"{len(epics)} epic(s) &nbsp;·&nbsp; "
      f"{n_on_track} on track &nbsp;·&nbsp; "
      f"{n_slipping} slipping &nbsp;·&nbsp; "
      f"{n_unestimated} unestimated")
    w()

    if epics:
        for ikey, isummary, iepics in _group_by_initiative(epics):
            if ikey:
                ilink = f"[{ikey}]({base_url}/browse/{ikey})"
                w(f"{initiative_prefix} {ilink} — {isummary}")
            else:
                w(f"{initiative_prefix} (no parent initiative)")
            w()
            w("| Epic | Summary | Progress | Status |")
            w("|------|---------|----------|--------|")            
            for epic in iepics:
                prog   = epic["progress"]
                link   = f"[{epic['key']}]({base_url}/browse/{epic['key']})"
                bar    = _progress_bar(prog["pct_complete"])
                pct    = f"{prog['pct_complete']*100:.1f}%"
                pts    = f"{prog['done_pts']:.0f}/{prog['total_pts']:.0f} pts"
                iss    = f"{prog['done_issues']}/{prog['total_issues']} issues"
                detail = f"{bar} {pct} ({pts}, {iss})"

                if prog["unestimated"]:
                    status = "⚠ UNESTIMATED"
                elif epic["slipping"]:
                    status = "⚠ SLIPPING"
                else:
                    status = "✓ on track"

                summary = epic["summary"].replace("|", "\\|")
                w(f"| {link} | {summary} | {detail} | {status} |")
            w()

    if include_draft and team["any_needs_attention"]:
        slipping_epics    = [e for e in epics if e["slipping"]]
        unestimated_epics = [e for e in epics if e["progress"]["unestimated"]]
        msg = draft_message(
            team_name         = team["name"],
            managers          = team["managers"],
            slipping_epics    = [{"key": e["key"], "summary": e["summary"]}
                                  for e in slipping_epics],
            unestimated_epics = [{"key": e["key"], "summary": e["summary"]}
                                  for e in unestimated_epics],
            quarter_pct       = quarter_pct,
        )
        w()
        w(f"**Draft Slack message** — DM {_format_dm_ids(team['managers'])}")
        w()
        w("```")
        w(msg)
        w("```")

    return lines


def print_report(team_summaries, quarter_pct, config):
    """Print the full weekly commitment report to stdout.

    Args:
        team_summaries: list of team dicts produced by main.build_team_summaries()
            Each dict has:
                name          str
                managers      list of {em_slack_id, sem_slack_id} dicts
                epics         list of epic dicts, each with:
                                  key, summary, progress (from progress.epic_progress),
                                  slipping (bool)
                any_slipping  bool
        quarter_pct:    float — fraction of the quarter elapsed
        config:         parsed config dict (used for quarter label)
    """
    today        = date.today().isoformat()
    quarter_label = config["jira"]["current_quarter"]
    total_teams   = len(team_summaries)
    attention_teams = [t for t in team_summaries if t["any_needs_attention"]]

    # ── header ───────────────────────────────────────────────────────────
    print()
    print(SEPARATOR)
    print(f"  WEEKLY COMMITMENT REPORT")
    print(f"  {today}  |  {quarter_label}")
    print(f"  Quarter progress: {_progress_bar(quarter_pct)} {quarter_pct*100:.1f}%")
    print(f"  Teams: {total_teams} total, {len(attention_teams)} requiring outreach")
    print(SEPARATOR)

    # ── per-team sections ─────────────────────────────────────────────────
    for team in team_summaries:
        epics        = team["epics"]
        n_slipping   = sum(1 for e in epics if e["slipping"])
        n_unestimated = sum(1 for e in epics if e["progress"]["unestimated"])
        n_on_track   = len(epics) - n_slipping - n_unestimated

        print()
        print(f"  ── {team['name']}  ({len(epics)} epic(s)  |  "
              f"{n_on_track} on track  "
              f"{n_slipping} slipping  "
              f"{n_unestimated} unestimated)")
        print()

        for ikey, isummary, iepics in _group_by_initiative(epics):
            label = (
                f"{ikey}  {isummary[:55]}" if ikey
                else "(no parent initiative)"
            )
            print(f"    ·· {label}")
            print()

            for epic in iepics:
                prog = epic["progress"]

                if prog["unestimated"]:
                    tag = "  ⚠  UNESTIMATED"
                elif epic["slipping"]:
                    tag = "  ⚠  SLIPPING"
                else:
                    tag = "  ✓  on track"

                bar  = _progress_bar(prog["pct_complete"])
                pct  = prog["pct_complete"] * 100
                pts  = f"{prog['done_pts']:.0f}/{prog['total_pts']:.0f} pts"
                iss  = f"{prog['done_issues']}/{prog['total_issues']} issues"

                print(f"      {epic['key']:14s} {bar} {pct:5.1f}%  ({pts}, {iss}){tag}")
                print(f"      {'':14s} {epic['summary'][:60]}")
            print()

        # ── draft message ─────────────────────────────────────────────
        if team["any_needs_attention"]:
            slipping_epics    = [e for e in epics if e["slipping"]]
            unestimated_epics = [e for e in epics if e["progress"]["unestimated"]]
            msg = draft_message(
                team_name         = team["name"],
                managers          = team["managers"],
                slipping_epics    = [{"key": e["key"], "summary": e["summary"]}
                                      for e in slipping_epics],
                unestimated_epics = [{"key": e["key"], "summary": e["summary"]}
                                      for e in unestimated_epics],
                quarter_pct       = quarter_pct,
            )
            print()
            print(f"    {SUBSEP[:66]}")
            print(f"    DRAFT — paste into a Slack DM with "
                  f"{_format_dm_ids(team['managers'], backticks=False)}")
            print(f"    {SUBSEP[:66]}")
            for line in msg.splitlines():
                print(f"    {line}")
            print(f"    {SUBSEP[:66]}")

    # ── summary footer ────────────────────────────────────────────────────
    print()
    print(SEPARATOR)
    if attention_teams:
        print(f"  ACTION NEEDED: {len(attention_teams)} team(s) require outreach:")
        for t in attention_teams:
            n_slip = sum(1 for e in t["epics"] if e["slipping"])
            n_unest = sum(1 for e in t["epics"] if e["progress"]["unestimated"])
            parts = []
            if n_slip:
                parts.append(f"{n_slip} slipping")
            if n_unest:
                parts.append(f"{n_unest} unestimated")
            print(f"    • {t['name']} ({', '.join(parts)})")
    else:
        print("  All teams on track — no outreach needed this week.")
    print(SEPARATOR)
    print()


def write_markdown_report(team_summaries, quarter_pct, config, path=None):
    """Write the weekly commitment report to a Markdown file.

    Args:
        team_summaries: same structure as print_report()
        quarter_pct:    float — fraction of the quarter elapsed
        config:         parsed config dict
        path:           output file path (str or Path).  Defaults to
                        report-YYYY-MM-DD.md in the current directory.

    Returns:
        Path: the file that was written
    """
    today         = date.today()
    quarter_label = config["jira"]["current_quarter"]
    slipping_teams  = [t for t in team_summaries if t["any_slipping"]]
    attention_teams = [t for t in team_summaries if t["any_needs_attention"]]

    if path is None:
        path = Path(f"report-{today.isoformat()}.md")
    else:
        path = Path(path)

    lines = []

    def w(text=""):
        lines.append(text)

    # ── header ────────────────────────────────────────────────────────────
    w(f"# Weekly Commitment Report")
    w()
    w(f"**Date:** {today.isoformat()} &nbsp;|&nbsp; **Quarter:** {quarter_label}  ")
    w(f"**Quarter elapsed:** {quarter_pct*100:.1f}%  ")
    w(f"**Teams:** {len(team_summaries)} total &nbsp;|&nbsp; "
      f"{len(attention_teams)} requiring outreach")
    w()
    w("---")

    # ── per-team sections ─────────────────────────────────────────────────
    for team in team_summaries:
        w()
        w(f"## {team['name']}")
        w()
        for line in _render_team_lines(team, quarter_pct, config, initiative_hlevel=3):
            w(line)

    # ── summary footer ────────────────────────────────────────────────────
    w()
    w("## Summary")
    w()
    if attention_teams:
        w(f"**{len(attention_teams)} team(s) require outreach:**")
        w()
        for t in attention_teams:
            n_slip  = sum(1 for e in t["epics"] if e["slipping"])
            n_unest = sum(1 for e in t["epics"] if e["progress"]["unestimated"])
            parts = []
            if n_slip:
                parts.append(f"{n_slip} slipping")
            if n_unest:
                parts.append(f"{n_unest} unestimated")
            w(f"- {t['name']} ({', '.join(parts)})")
    else:
        w("All teams on track — no outreach needed this week. ✓")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_slack_drafts(team_summaries, quarter_pct, config, path=None):
    """Write all draft Slack messages for slipping teams to a single file.

    Args:
        team_summaries: same structure as print_report()
        quarter_pct:    float — fraction of the quarter elapsed
        config:         parsed config dict
        path:           output file path.  Defaults to
                        slack-drafts-YYYY-MM-DD.md in the current directory.

    Returns:
        Path: the file that was written
    """
    today          = date.today()
    quarter_label  = config["jira"]["current_quarter"]
    attention_teams = [t for t in team_summaries if t["any_needs_attention"]]

    if path is None:
        path = Path(f"slack-drafts-{today.isoformat()}.md")
    else:
        path = Path(path)

    lines = []

    def w(text=""):
        lines.append(text)

    w("# Draft Slack Messages")
    w()
    w(f"**Date:** {today.isoformat()} &nbsp;|&nbsp; **Quarter:** {quarter_label}  ")
    w(f"**Quarter elapsed:** {quarter_pct*100:.1f}%")
    w()

    if not attention_teams:
        w("All teams on track — no outreach needed this week. ✓")
    else:
        w(f"{len(attention_teams)} team(s) require outreach.")
        w()
        w("---")
        for team in attention_teams:
            slipping_epics    = [e for e in team["epics"] if e["slipping"]]
            unestimated_epics = [e for e in team["epics"] if e["progress"]["unestimated"]]
            msg = draft_message(
                team_name         = team["name"],
                managers          = team["managers"],
                slipping_epics    = [{"key": e["key"], "summary": e["summary"]}
                                      for e in slipping_epics],
                unestimated_epics = [{"key": e["key"], "summary": e["summary"]}
                                      for e in unestimated_epics],
                quarter_pct       = quarter_pct,
            )
            w()
            w(f"## {team['name']}")
            w()
            w(f"DM {_format_dm_ids(team['managers'])}")
            w()
            w("```")
            w(msg)
            w("```")
            w()
            w("---")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_team_markdown_report(team, quarter_pct, config, path):
    """Write a single-team commitment report to a Markdown file.

    Args:
        team:        single team summary dict
        quarter_pct: float — fraction of the quarter elapsed
        config:      parsed config dict
        path:        output file path (str or Path)

    Returns:
        Path: the file that was written
    """
    today         = date.today()
    quarter_label = config["jira"]["current_quarter"]
    epics         = team["epics"]
    n_slipping    = sum(1 for e in epics if e["slipping"])
    n_unestimated = sum(1 for e in epics if e["progress"]["unestimated"])
    n_on_track    = len(epics) - n_slipping - n_unestimated

    lines = []

    def w(text=""):
        lines.append(text)

    w(f"# {team['name']} — Weekly Commitment Report")
    w()
    w(f"**Date:** {today.isoformat()} &nbsp;|&nbsp; **Quarter:** {quarter_label}  ")
    w(f"**Quarter elapsed:** {quarter_pct*100:.1f}%")
    w()
    w("---")
    w()
    for line in _render_team_lines(team, quarter_pct, config, initiative_hlevel=2):
        w(line)

    path = Path(path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_per_team_reports(team_summaries, quarter_pct, config, output_dir=None):
    """Write one markdown file per team into a dated subdirectory.

    Args:
        team_summaries: same structure as print_report()
        quarter_pct:    float — fraction of the quarter elapsed
        config:         parsed config dict
        output_dir:     directory to write files into.  Defaults to
                        reports/YYYY-MM-DD/ in the current directory.

    Returns:
        list[Path]: files written, one per team
    """
    if output_dir is None:
        output_dir = Path(f"reports/{date.today().isoformat()}")
    else:
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for team in team_summaries:
        filename = _slugify(team["name"]) + ".md"
        path = write_team_markdown_report(team, quarter_pct, config, output_dir / filename)
        paths.append(path)
    return paths
