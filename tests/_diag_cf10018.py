"""Diagnostic: inspect the raw format of customfield_10018 (Initiative field).

Run from the project root:
    python tests/_diag_cf10018.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml
from jira_client import _search_jql

config = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config.yaml")))
jql = 'issuetype = Epic AND cf[11245] = "FY26 Quarter 4"'
issues = _search_jql(config, jql, ["customfield_10018", "summary", "parent"], max_results=10)

print(f"Fetched {len(issues)} epics\n")
for issue in issues:
    key = issue["key"]
    summary = issue["fields"].get("summary", "")[:55]
    raw_10018 = issue["fields"].get("customfield_10018")
    parent    = issue["fields"].get("parent")

    print(f"{key}  {summary}")
    print(f"  cf10018  type={type(raw_10018).__name__!r:12s}  value={raw_10018!r}")
    if parent:
        psummary = (parent.get("fields") or {}).get("summary", "")[:45]
        print(f"  parent   key={parent.get('key')}  summary={psummary!r}")
    else:
        print(f"  parent   None")
    print()
