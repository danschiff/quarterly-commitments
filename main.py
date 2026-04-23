"""Weekly commitment tracker — entry point.

Usage:
    python main.py              # use today's cached data file (data-YYYY-MM-DD.json)
    python main.py --refresh    # re-fetch from Jira and overwrite the cache
    python main.py --data FILE  # use a specific data file instead of today's default

Requires environment variables (only when fetching from Jira):
    JIRA_API_TOKEN   — Jira API token for the account in config.yaml
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

import jira_client as jc
from progress import quarter_pct_elapsed, epic_progress, is_slipping
from report import print_report, write_markdown_report, write_per_team_reports, write_slack_drafts


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def _team_managers(team_cfg):
    """Normalize a team config entry to a list of manager dicts.

    Supports two forms:
      - new: team_cfg["managers"] is a list of {em_slack_id, sem_slack_id} dicts
      - legacy: team_cfg["em_slack_id"] + team_cfg["sem_slack_id"] (single manager)

    Returns a list of {em_slack_id, sem_slack_id} dicts (always at least one entry).
    """
    managers = team_cfg.get("managers")
    if managers:
        return [
            {"em_slack_id": m["em_slack_id"], "sem_slack_id": m["sem_slack_id"]}
            for m in managers
        ]
    return [{
        "em_slack_id":  team_cfg["em_slack_id"],
        "sem_slack_id": team_cfg["sem_slack_id"],
    }]


# ---------------------------------------------------------------------------
# Jira fetch → raw data
# ---------------------------------------------------------------------------

def fetch_raw_data(config):
    """Fetch all committed epics + their children from Jira.

    Returns a dict ready to be serialised to JSON:
    {
        "fetched_at": "<ISO datetime>",
        "teams": [
            {
                "name": str,
                "team_field_value": str,
                "managers": [ {em_slack_id, sem_slack_id}, ... ],
                "epics": [
                    {
                        "key": str,
                        "summary": str,
                        "initiative_key": str | None,
                        "initiative_summary": str | None,
                        "children": [ {key, summary, status_category, story_points}, ... ]
                    }
                ]
            }
        ]
    }
    """
    print("Fetching committed epics from Jira...", flush=True)
    all_epics = jc.fetch_committed_epics(config)
    print(f"  Found {len(all_epics)} committed epic(s) across all teams.", flush=True)

    # Group epics by configured team
    epics_by_team = {t["team_field_value"]: [] for t in config["teams"]}
    unmatched = set()
    for epic in all_epics:
        tv = epic["team_field_value"]
        if tv in epics_by_team:
            epics_by_team[tv].append(epic)
        else:
            unmatched.add(tv)

    if unmatched:
        sorted_unmatched = sorted((v for v in unmatched if v is not None), key=str)
        if None in unmatched:
            sorted_unmatched.append(None)
        print(f"  Warning: {len(unmatched)} team value(s) in Jira not found in config "
              f"and will be skipped: {sorted_unmatched}", flush=True)

    teams = []
    for team_cfg in config["teams"]:
        tv    = team_cfg["team_field_value"]
        epics = epics_by_team.get(tv, [])

        print(f"  Processing {team_cfg['name']} ({len(epics)} epic(s))...", flush=True)

        enriched_epics = []
        for epic in epics:
            children = jc.fetch_epic_children(config, epic["key"])
            enriched_epics.append({
                "key":               epic["key"],
                "summary":           epic["summary"],
                "initiative_key":    epic.get("initiative_key"),
                "initiative_summary": epic.get("initiative_summary"),
                "health":            epic.get("health"),
                "children":          children,
            })

        teams.append({
            "name":             team_cfg["name"],
            "team_field_value": tv,
            "managers":         _team_managers(team_cfg),
            "epics":            enriched_epics,
        })

    # Collect all unique initiative keys and bulk-fetch their metadata
    initiative_keys = {
        epic["initiative_key"]
        for team in teams
        for epic in team["epics"]
        if epic.get("initiative_key")
    }
    print(f"  Fetching metadata for {len(initiative_keys)} initiative(s)...", flush=True)
    initiatives = jc.fetch_initiatives(config, initiative_keys)

    return {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "teams": teams,
        "initiatives": initiatives,
    }


# ---------------------------------------------------------------------------
# JSON cache
# ---------------------------------------------------------------------------

def save_raw_data(data, path):
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_raw_data(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Build report summaries from raw data
# ---------------------------------------------------------------------------

def build_summaries_from_raw(raw_data, config, quarter_pct):
    """Compute progress and slippage from cached raw data.

    Filters out epics where no work has been completed yet
    (done_issues == 0) — these haven't started and aren't relevant.
    Epics that are 100% complete are kept to celebrate progress.

    Returns the same list-of-team-dicts structure that print_report()
    and write_markdown_report() expect.
    """
    threshold = config["slippage_threshold"]
    current_quarter = config["jira"]["current_quarter"]
    initiatives = raw_data.get("initiatives", {})
    # Manager info is config-only (not Jira data), so always read it from
    # the current config rather than the (possibly stale) cache. Fall back
    # to the cache's fields only if the team is missing from config.
    cfg_by_name = {t["name"]: t for t in config["teams"]}

    summaries = []
    for team_data in raw_data["teams"]:
        enriched = []
        for epic_data in team_data["epics"]:
            prog = epic_progress(epic_data["children"])

            # Skip epics where no work has been completed yet
            if prog["done_issues"] == 0:
                continue

            slipping = (
                not prog["unestimated"]
                and is_slipping(prog["pct_complete"], quarter_pct, threshold)
            )

            ikey = epic_data.get("initiative_key")
            init_data = initiatives.get(ikey, {}) if ikey else {}
            committed_this_quarter = (
                init_data.get("committed_quarter") == current_quarter
            )

            enriched.append({
                "key":                   epic_data["key"],
                "summary":               epic_data["summary"],
                "initiative_key":        ikey,
                "initiative_summary":    epic_data.get("initiative_summary"),
                "committed_this_quarter": committed_this_quarter,
                "health":                epic_data.get("health"),
                "initiative_health":     init_data.get("health"),
                "progress":              prog,
                "slipping":              slipping,
            })

        team_cfg = cfg_by_name.get(team_data["name"])
        if team_cfg is not None:
            managers = _team_managers(team_cfg)
        else:
            # Fall back to cache fields (new 'managers' or legacy single-EM)
            managers = team_data.get("managers") or [{
                "em_slack_id":  team_data["em_slack_id"],
                "sem_slack_id": team_data["sem_slack_id"],
            }]

        summaries.append({
            "name":         team_data["name"],
            "managers":     managers,
            "epics":        enriched,
            "any_slipping": any(e["slipping"] for e in enriched),
            "any_needs_attention": any(
                e["slipping"] or e["progress"]["unestimated"]
                for e in enriched
            ),
        })

    return summaries


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Windows consoles default to cp1252 which can't encode the block-bar
    # characters (█ ░) used in the progress display.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Weekly commitment tracker — generate slippage report from Jira."
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="Re-fetch from Jira even if today's data file already exists.",
    )
    parser.add_argument(
        "--data", metavar="FILE",
        help="Path to data JSON file (default: data-YYYY-MM-DD.json in cwd).",
    )
    args = parser.parse_args()

    config = load_config()

    data_path = Path(args.data) if args.data else Path(f"data-{date.today().isoformat()}.json")

    if args.refresh or not data_path.exists():
        # Validate Jira token before hitting the API
        jira_token_var = config["jira"]["api_token_env"]
        if not os.environ.get(jira_token_var):
            print(f"Error: environment variable '{jira_token_var}' is not set.", file=sys.stderr)
            sys.exit(1)

        raw_data = fetch_raw_data(config)
        save_raw_data(raw_data, data_path)
        print(f"  Data saved to {data_path}", flush=True)
    else:
        print(f"Using cached data from {data_path}", flush=True)
        raw_data = load_raw_data(data_path)

    quarter_pct = quarter_pct_elapsed(config)
    summaries   = build_summaries_from_raw(raw_data, config, quarter_pct)
    print_report(summaries, quarter_pct, config)
    md_path = write_markdown_report(summaries, quarter_pct, config)
    print(f"Markdown report written to: {md_path.resolve()}")
    team_paths = write_per_team_reports(summaries, quarter_pct, config)
    print(f"Per-team reports written to: reports/{date.today().isoformat()}/ ({len(team_paths)} files)")
    drafts_path = write_slack_drafts(summaries, quarter_pct, config)
    print(f"Slack drafts written to: {drafts_path.resolve()}")


if __name__ == "__main__":
    main()
