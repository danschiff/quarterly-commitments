"""Sample recent Epics and print every distinct value found in customfield_11245."""
import os, yaml, requests
from requests.auth import HTTPBasicAuth

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

j = cfg["jira"]
auth = HTTPBasicAuth(j["email"], os.environ[j["api_token_env"]])
base = j["base_url"].rstrip("/")

body = {
    "jql": "issuetype = Epic ORDER BY updated DESC",
    "fields": ["summary", "customfield_11245"],
    "maxResults": 50,
}
r = requests.post(
    f"{base}/rest/api/3/search/jql",
    json=body,
    headers={"Accept": "application/json", "Content-Type": "application/json"},
    auth=auth,
    timeout=15,
)
r.raise_for_status()
issues = r.json().get("issues", [])
print(f"Sampled {len(issues)} recent epics\n")

seen = {}
for issue in issues:
    raw = issue["fields"].get("customfield_11245")
    val = raw.get("value") if isinstance(raw, dict) else raw
    key = repr(val)
    if key not in seen:
        seen[key] = issue["key"]

if seen:
    print("Distinct customfield_11245 values found:")
    for v, example in seen.items():
        print(f"  {v:40s}  (e.g. {example})")
else:
    print("customfield_11245 is null/unset on all sampled epics.")
    print("The field ID may be different. Printing all non-null custom fields from the first epic:")
    if issues:
        for k, v in issues[0]["fields"].items():
            if v is not None and k.startswith("customfield_"):
                print(f"  {k}: {repr(v)[:80]}")
