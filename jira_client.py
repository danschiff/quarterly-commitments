import os
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry


def _token_expiry_warning(config):
    """Return a human-readable warning string if the configured Jira API
    token expiration date is near or past, otherwise None.
    """
    expires_str = config.get("jira", {}).get("api_token_expires")
    if not expires_str:
        return None
    try:
        expires = date.fromisoformat(str(expires_str))
    except ValueError:
        return f"(could not parse jira.api_token_expires={expires_str!r})"
    today = date.today()
    days = (expires - today).days
    if days < 0:
        return (
            f"Your Jira API token expired on {expires.isoformat()} "
            f"({-days} day(s) ago). Generate a new one at "
            "https://id.atlassian.com/manage-profile/security/api-tokens "
            "and update JIRA_API_TOKEN and config.yaml:jira.api_token_expires."
        )
    if days <= 14:
        return (
            f"Your Jira API token expires on {expires.isoformat()} "
            f"(in {days} day(s))."
        )
    return None


def _make_session():
    """Return a requests Session with automatic retry on transient errors.

    Retries up to 4 times with exponential backoff (0.5s, 1s, 2s, 4s) on
    connection resets, 502/503/504 responses, and read timeouts.
    """
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=[429, 502, 503, 504],
        allowed_methods=["POST", "GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_auth(config):
    """Build HTTPBasicAuth from config, reading the token from an env var."""
    env_var = config["jira"]["api_token_env"]
    token = os.environ.get(env_var)
    if not token:
        raise RuntimeError(
            f"Environment variable '{env_var}' is not set. "
            "Generate a Jira API token at "
            "https://id.atlassian.com/manage-profile/security/api-tokens"
        )
    return HTTPBasicAuth(config["jira"]["email"], token)


def _cf_to_customfield(cf_str):
    """Convert JQL shorthand 'cf[10817]' to the API field key 'customfield_10817'.

    JQL queries accept cf[XXXXX] notation, but the `fields` list in the
    search request body requires the customfield_XXXXX form.
    If the value is already in customfield_XXXXX form it is returned unchanged.
    """
    s = cf_str.strip()
    if s.startswith("cf[") and s.endswith("]"):
        return f"customfield_{s[3:-1]}"
    return s


def _team_field_value(raw):
    """Extract a plain string from a Jira field that may be a string or a
    select-list object like {"value": "Recruiting", "id": "..."}.
    """
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def _search_jql(config, jql, fields, max_results=100):
    """Paginate through all results of a JQL query.

    Uses POST /rest/api/3/search/jql (the current, non-deprecated endpoint).
    Returns a flat list of raw issue dicts.
    """
    auth = _get_auth(config)
    base_url = config["jira"]["base_url"].rstrip("/")
    url = f"{base_url}/rest/api/3/search/jql"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    issues = []
    next_page_token = None
    session = _make_session()

    while True:
        body = {
            "jql": jql,
            "fields": fields,
            "maxResults": max_results,
        }
        if next_page_token:
            body["nextPageToken"] = next_page_token

        response = session.post(
            url, json=body, headers=headers, auth=auth, timeout=30
        )
        if not response.ok:
            hint = ""
            if response.status_code in (401, 403):
                warning = _token_expiry_warning(config)
                if warning:
                    hint = f" — {warning}"
                else:
                    hint = (
                        " — Jira rejected the credentials. Verify "
                        "JIRA_API_TOKEN is current and not expired "
                        "(see config.yaml:jira.api_token_expires)."
                    )
            raise requests.HTTPError(
                f"{response.status_code} {response.reason} from {url}{hint}",
                response=response,
            )
        data = response.json()

        issues.extend(data.get("issues", []))

        if data.get("isLast", True):
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    return issues


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_committed_epics(config):
    """Return all Epics that are committed for the current quarter.

    Uses JQL:
        issuetype = Epic AND cf[11245] = "<current_quarter>"

    Returns a list of dicts:
        {
            "key":              str,   # e.g. "PROJ-123"
            "summary":          str,
            "team_field_value": str | None,  # raw value of cf[10817]
        }
    """
    jira_cfg = config["jira"]
    quarter = jira_cfg["current_quarter"]
    committed_field = jira_cfg["committed_quarter_field"]   # cf[11245]
    team_field = jira_cfg["team_field"]                     # cf[10817]
    team_cf_key = _cf_to_customfield(team_field)            # customfield_10817

    health_cf_key = _cf_to_customfield(jira_cfg.get("health_field", ""))  # customfield_10883

    jql = (
        f'issuetype = Epic AND {committed_field} = "{quarter}"'
        f' ORDER BY {team_field} ASC'
    )
    fields = ["summary", team_cf_key, "parent"]
    if health_cf_key:
        fields.append(health_cf_key)

    raw_issues = _search_jql(config, jql, fields)

    results = []
    for issue in raw_issues:
        f = issue.get("fields", {})
        parent = f.get("parent") or {}
        health_raw = f.get(health_cf_key) if health_cf_key else None
        health = health_raw.get("value") if isinstance(health_raw, dict) else health_raw
        results.append({
            "key": issue["key"],
            "summary": f.get("summary", ""),
            "team_field_value": _team_field_value(f.get(team_cf_key)),
            "initiative_key": parent.get("key"),
            "initiative_summary": (
                parent.get("fields", {}).get("summary") or parent.get("key")
            ),
            "health": health,
        })
    return results


def fetch_epic_children(config, epic_key):
    """Return all direct child issues of the given Epic.

    Respects config["jira"]["epic_link_mode"]:
        "parent"     → parent = EPIC_KEY       (next-gen / team-managed projects)
        "epic_link"  → "Epic Link" = EPIC_KEY  (classic / company-managed projects)

    Returns a list of dicts:
        {
            "key":             str,
            "summary":         str,
            "status_category": str,         # "new" | "indeterminate" | "done"
            "story_points":    float | None,
        }
    """
    jira_cfg = config["jira"]
    sp_field = jira_cfg["story_points_field"]   # e.g. "customfield_10016"
    mode = jira_cfg["epic_link_mode"]           # "parent" | "epic_link"

    if mode == "epic_link":
        jql = f'"Epic Link" = {epic_key} ORDER BY created ASC'
    else:
        jql = f"parent = {epic_key} ORDER BY created ASC"

    fields = ["summary", "status", sp_field]
    raw_issues = _search_jql(config, jql, fields)

    children = []
    for issue in raw_issues:
        f = issue.get("fields", {})

        status_category = (
            f.get("status", {})
            .get("statusCategory", {})
            .get("key", "new")
        )

        sp_raw = f.get(sp_field)
        story_points = float(sp_raw) if sp_raw is not None else None

        children.append({
            "key": issue["key"],
            "summary": f.get("summary", ""),
            "status_category": status_category,
            "story_points": story_points,
        })

    return children


def fetch_initiatives(config, keys):
    """Fetch initiative metadata for the given collection of issue keys.

    keys: iterable of str issue keys (e.g. {"PROJ-1", "PROJ-2"})

    Returns a dict mapping key -> {
        "committed_quarter": str | None   (value of customfield_11245)
    }
    """
    if not keys:
        return {}

    jira_cfg = config["jira"]
    committed_cf_key = _cf_to_customfield(jira_cfg["committed_quarter_field"])  # customfield_11245
    health_cf_key = _cf_to_customfield(jira_cfg.get("health_field", ""))        # customfield_10883

    fetch_fields = [committed_cf_key, "labels"]
    if health_cf_key:
        fetch_fields.append(health_cf_key)

    keys_sorted = sorted(keys)
    result = {}

    # Chunk to avoid JQL length limits
    chunk_size = 50
    for i in range(0, len(keys_sorted), chunk_size):
        chunk = keys_sorted[i:i + chunk_size]
        keys_jql = ", ".join(chunk)
        jql = f"key in ({keys_jql})"
        raw_issues = _search_jql(config, jql, fetch_fields)

        for issue in raw_issues:
            f = issue.get("fields", {})
            cf_raw = f.get(committed_cf_key)
            committed_quarter = (
                cf_raw.get("value") if isinstance(cf_raw, dict) else cf_raw
            )
            health_raw = f.get(health_cf_key) if health_cf_key else None
            health = health_raw.get("value") if isinstance(health_raw, dict) else health_raw
            labels = f.get("labels") or []
            result[issue["key"]] = {
                "committed_quarter": committed_quarter,
                "health": health,
                "rolling": "Rolling" in labels,
            }

    return result
