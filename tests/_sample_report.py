"""One-off sample report for a single team. Delete after use."""
import os, sys, yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jira_client as jc
from progress import quarter_pct_elapsed, epic_progress, is_slipping

with open("config.yaml") as f:
    config = yaml.safe_load(f)

TARGET_TEAM = "Learning"   # team_field_value to inspect
BAR_WIDTH   = 20

quarter_pct = quarter_pct_elapsed(config)
threshold   = config["slippage_threshold"]

def progress_bar(pct, width=BAR_WIDTH):
    filled = round(pct * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"

# ── fetch all committed epics for this team ───────────────────────────────
print(f"Fetching committed epics for team '{TARGET_TEAM}'...")
all_epics = jc.fetch_committed_epics(config)
team_epics = [e for e in all_epics if e["team_field_value"] == TARGET_TEAM]

if not team_epics:
    distinct = sorted({e["team_field_value"] for e in all_epics if e["team_field_value"]})
    print(f"\nNo epics found for team '{TARGET_TEAM}'.")
    print("Available team_field_value options in Jira:")
    for t in distinct:
        print(f"  {t!r}")
    sys.exit(0)

# ── header ────────────────────────────────────────────────────────────────
print()
print("=" * 66)
print(f"  WEEKLY COMMITMENT REPORT — {config['jira']['current_quarter']}")
print(f"  Quarter progress: {progress_bar(quarter_pct)} {quarter_pct*100:.1f}%")
print("=" * 66)
print(f"\n  Team: {TARGET_TEAM}  ({len(team_epics)} committed epic(s))\n")

any_slipping = False

for epic in team_epics:
    children = jc.fetch_epic_children(config, epic["key"])
    prog     = epic_progress(children)

    if prog["unestimated"]:
        status_tag = "  ⚠  UNESTIMATED"
        slipping   = False
    elif is_slipping(prog["pct_complete"], quarter_pct, threshold):
        status_tag = "  ⚠  SLIPPING"
        slipping   = True
        any_slipping = True
    else:
        status_tag = "  ✓  on track"
        slipping   = False

    bar  = progress_bar(prog["pct_complete"])
    pct  = prog["pct_complete"] * 100
    pts  = f"{prog['done_pts']:.0f}/{prog['total_pts']:.0f} pts"
    iss  = f"{prog['done_issues']}/{prog['total_issues']} issues"

    print(f"  {epic['key']:12s}  {bar} {pct:5.1f}%  ({pts}, {iss}){status_tag}")
    print(f"              {epic['summary'][:60]}")
    print()

# ── slippage summary ──────────────────────────────────────────────────────
if any_slipping:
    print("-" * 66)
    print("  DRAFT OUTREACH MESSAGE")
    print("-" * 66)
    slipping_epics = [
        e for e in team_epics
        if not epic_progress(jc.fetch_epic_children(config, e["key"]))["unestimated"]
        and is_slipping(
            epic_progress(jc.fetch_epic_children(config, e["key"]))["pct_complete"],
            quarter_pct, threshold
        )
    ]
    epic_lines = "\n".join(f"  • {e['key']}: {e['summary'][:55]}" for e in slipping_epics)
    print(f"""
Hi [EM name] and [Senior EM name],

Doing my weekly check-in on quarterly commitments. The {TARGET_TEAM} team
is currently behind the expected burn-down rate ({quarter_pct*100:.0f}% through
the quarter) on the following commitment(s):

{epic_lines}

A few questions:
  1. Are you still on track to deliver these by end of quarter?
  2. Are there any blockers I should know about?
  3. Is there anything you need help with?

Thanks!
""")
else:
    print("  All epics on track — no outreach needed this week.")

print("=" * 66)
