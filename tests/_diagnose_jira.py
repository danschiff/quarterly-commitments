"""Diagnose Jira connectivity and discover issue types + accessible issues."""
import os, yaml, requests
from requests.auth import HTTPBasicAuth

with open("config.yaml") as f:
    cfg = yaml.safe_load(f)

j = cfg["jira"]
auth = HTTPBasicAuth(j["email"], os.environ[j["api_token_env"]])
base = j["base_url"].rstrip("/")
headers = {"Accept": "application/json", "Content-Type": "application/json"}

# 1. Sample any issues to confirm access
r = requests.post(
    f"{base}/rest/api/3/search/jql",
    json={"jql": "updated >= -30d ORDER BY updated DESC", "fields": ["issuetype", "summary"], "maxResults": 5},
    headers=headers, auth=auth, timeout=15,
)
if not r.ok:
    print(f"Search failed {r.status_code}: {r.text[:400]}")
    r.raise_for_status()
data = r.json()
issues = data.get("issues", [])
print(f"Sample query — issues returned: {len(issues)}")
for i in issues:
    itype = i["fields"]["issuetype"]["name"]
    key   = i["key"]
    summ  = i["fields"]["summary"][:50]
    print(f"  {key:15s}  type={itype:15s}  {summ}")

# 2. Check issue types
r2 = requests.get(
    f"{base}/rest/api/3/issuetype",
    headers={"Accept": "application/json"}, auth=auth, timeout=15,
)
r2.raise_for_status()
types = [t["name"] for t in r2.json()]
print()
print("All issue types:", types)
