"""Live integration smoke-test against the real Jira instance.

Run with:  python tests/integration_jira.py
Requires:  JIRA_API_TOKEN env var to be set.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import jira_client as jc

with open(os.path.join(os.path.dirname(__file__), "..", "config.yaml")) as f:
    config = yaml.safe_load(f)

print(f"Base URL : {config['jira']['base_url']}")
print(f"Quarter  : {config['jira']['current_quarter']}")
print()

# ── fetch_committed_epics ─────────────────────────────────────────────────
print("=== fetch_committed_epics ===")
epics = jc.fetch_committed_epics(config)
print(f"Found {len(epics)} committed epic(s)")

for e in epics[:10]:
    team = (e["team_field_value"] or "").ljust(25)
    print(f"  {e['key']:15s}  team={team}  {e['summary'][:60]}")

if len(epics) > 10:
    print(f"  ... and {len(epics) - 10} more")

if not epics:
    print("No epics found — check current_quarter value in config.yaml matches Jira exactly.")
    sys.exit(0)

# ── fetch_epic_children (first epic) ─────────────────────────────────────
first = epics[0]
print()
print(f"=== fetch_epic_children({first['key']}) ===")
children = jc.fetch_epic_children(config, first["key"])
print(f"Found {len(children)} child issue(s)")

done  = sum(1 for c in children if c["status_category"] == "done")
total_pts = sum(c["story_points"] or 0 for c in children)
done_pts  = sum(c["story_points"] or 0 for c in children if c["status_category"] == "done")

for c in children[:10]:
    sp = str(c["story_points"]) if c["story_points"] is not None else "—"
    print(f"  {c['key']:15s}  status={c['status_category']:15s}  pts={sp:>5}  {c['summary'][:50]}")

if len(children) > 10:
    print(f"  ... and {len(children) - 10} more")

print()
print(f"  Done: {done}/{len(children)} issues  |  {done_pts:.0f}/{total_pts:.0f} pts")
