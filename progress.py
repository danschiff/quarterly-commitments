from datetime import date


def quarter_pct_elapsed(config):
    """Return the fraction of the quarter that has elapsed as of today.

    Clamps to [0.0, 1.0] so values before the quarter start or after
    quarter end don't produce nonsense percentages.

    Args:
        config: parsed config dict with config["quarter"]["start"] and ["end"]
                as ISO-format date strings (e.g. "2026-04-01").

    Returns:
        float in [0.0, 1.0]
    """
    q = config["quarter"]
    start = date.fromisoformat(q["start"])
    end   = date.fromisoformat(q["end"])
    today = date.today()

    total_days = (end - start).days
    if total_days <= 0:
        return 1.0

    elapsed = (today - start).days
    return max(0.0, min(1.0, elapsed / total_days))


def epic_progress(children):
    """Compute story-point progress for a single epic.

    Args:
        children: list of child-issue dicts as returned by
                  jira_client.fetch_epic_children(), each with:
                      "status_category": "new" | "indeterminate" | "done"
                      "story_points":    float | None

    Returns:
        dict with keys:
            "total_pts"    float  — sum of story points on all children
            "done_pts"     float  — sum of story points on "done" children
            "pct_complete" float  — done_pts / total_pts, or 0.0 if no points
            "unestimated"  bool   — True when total_pts == 0
            "total_issues" int    — total number of child issues
            "done_issues"  int    — number of child issues in "done" category
    """
    total_pts = 0.0
    done_pts  = 0.0
    total_issues = len(children)
    done_issues  = 0

    for child in children:
        sp = child.get("story_points") or 0.0
        total_pts += sp
        if child.get("status_category") == "done":
            done_pts += sp
            done_issues += 1

    unestimated  = total_pts == 0.0
    pct_complete = (done_pts / total_pts) if not unestimated else 0.0

    return {
        "total_pts":    total_pts,
        "done_pts":     done_pts,
        "pct_complete": pct_complete,
        "unestimated":  unestimated,
        "total_issues": total_issues,
        "done_issues":  done_issues,
    }


def is_slipping(epic_pct, quarter_pct, threshold):
    """Return True if an epic is more than `threshold` behind the linear target.

    Unestimated epics (pct_complete == 0 with no story points) should be
    checked separately — call epic_progress() and inspect "unestimated" before
    calling this function.

    Args:
        epic_pct:    float — epic's pct_complete (0.0–1.0)
        quarter_pct: float — fraction of the quarter elapsed (0.0–1.0)
        threshold:   float — grace buffer, e.g. 0.10 for 10 percentage points

    Returns:
        bool
    """
    return (quarter_pct - epic_pct) > threshold
