"""Tests for jira_client.py.

All HTTP calls are mocked — no real Jira connection is made.
Run with:  python -m pytest tests/ -v
       or: python -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, call, patch

# Allow running from the project root without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jira_client as jc


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "jira": {
        "base_url": "https://test.atlassian.net",
        "email": "test@example.com",
        "api_token_env": "TEST_JIRA_TOKEN",
        "committed_quarter_field": "cf[11245]",
        "team_field": "cf[10817]",
        "story_points_field": "customfield_10016",
        "current_quarter": "FY26 Quarter 4",
        "epic_link_mode": "parent",
    }
}


def _mock_response(data, status_code=200):
    """Return a MagicMock that quacks like a requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


def _mock_session(post_return=None, post_side_effect=None):
    """Return a MagicMock session whose .post() is pre-configured."""
    session = MagicMock()
    if post_side_effect is not None:
        session.post.side_effect = post_side_effect
    else:
        session.post.return_value = post_return
    return session


# ---------------------------------------------------------------------------
# _cf_to_customfield
# ---------------------------------------------------------------------------

class TestCfToCustomfield(unittest.TestCase):

    def test_converts_cf_notation(self):
        self.assertEqual(jc._cf_to_customfield("cf[10817]"), "customfield_10817")

    def test_converts_with_whitespace(self):
        self.assertEqual(jc._cf_to_customfield("  cf[11245]  "), "customfield_11245")

    def test_passes_through_already_converted(self):
        self.assertEqual(jc._cf_to_customfield("customfield_10016"), "customfield_10016")

    def test_passes_through_plain_field(self):
        self.assertEqual(jc._cf_to_customfield("summary"), "summary")


# ---------------------------------------------------------------------------
# _team_field_value
# ---------------------------------------------------------------------------

class TestTeamFieldValue(unittest.TestCase):

    def test_plain_string(self):
        self.assertEqual(jc._team_field_value("Recruiting"), "Recruiting")

    def test_select_list_object(self):
        self.assertEqual(
            jc._team_field_value({"value": "Onboarding", "id": "1"}),
            "Onboarding",
        )

    def test_none(self):
        self.assertIsNone(jc._team_field_value(None))

    def test_dict_missing_value_key(self):
        self.assertIsNone(jc._team_field_value({"id": "5"}))


# ---------------------------------------------------------------------------
# _get_auth
# ---------------------------------------------------------------------------

class TestGetAuth(unittest.TestCase):

    def test_returns_basic_auth_when_env_set(self):
        with patch.dict(os.environ, {"TEST_JIRA_TOKEN": "mysecret"}):
            auth = jc._get_auth(BASE_CONFIG)
        self.assertEqual(auth.username, "test@example.com")
        self.assertEqual(auth.password, "mysecret")

    def test_raises_when_env_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "TEST_JIRA_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                jc._get_auth(BASE_CONFIG)
        self.assertIn("TEST_JIRA_TOKEN", str(ctx.exception))


# ---------------------------------------------------------------------------
# _search_jql  (pagination)
# ---------------------------------------------------------------------------

class TestSearchJql(unittest.TestCase):

    def setUp(self):
        os.environ["TEST_JIRA_TOKEN"] = "token123"

    def tearDown(self):
        os.environ.pop("TEST_JIRA_TOKEN", None)

    @patch("jira_client._make_session")
    def test_single_page(self, mock_make_session):
        session = _mock_session(_mock_response({"issues": [{"key": "A-1"}, {"key": "A-2"}], "isLast": True}))
        mock_make_session.return_value = session

        results = jc._search_jql(BASE_CONFIG, "project = TEST", ["summary"])

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["key"], "A-1")
        session.post.assert_called_once()

    @patch("jira_client._make_session")
    def test_multi_page_uses_next_page_token(self, mock_make_session):
        page1 = _mock_response({"issues": [{"key": "A-1"}], "isLast": False, "nextPageToken": "tok_page2"})
        page2 = _mock_response({"issues": [{"key": "A-2"}, {"key": "A-3"}], "isLast": True})
        session = _mock_session(post_side_effect=[page1, page2])
        mock_make_session.return_value = session

        results = jc._search_jql(BASE_CONFIG, "project = TEST", ["summary"])

        self.assertEqual([r["key"] for r in results], ["A-1", "A-2", "A-3"])
        self.assertEqual(session.post.call_count, 2)

        # Second call must carry the nextPageToken
        _, kwargs = session.post.call_args_list[1]
        self.assertEqual(kwargs["json"]["nextPageToken"], "tok_page2")

    @patch("jira_client._make_session")
    def test_stops_when_no_next_page_token_even_if_not_last(self, mock_make_session):
        """Guard against an API response that omits isLast=True but also
        provides no nextPageToken — should not loop forever."""
        session = _mock_session(_mock_response({"issues": [{"key": "A-1"}], "isLast": False}))
        mock_make_session.return_value = session

        results = jc._search_jql(BASE_CONFIG, "project = TEST", ["summary"])

        self.assertEqual(len(results), 1)
        session.post.assert_called_once()

    @patch("jira_client._make_session")
    def test_raises_on_http_error(self, mock_make_session):
        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        session = _mock_session(resp)
        mock_make_session.return_value = session

        with self.assertRaises(Exception, msg="401 Unauthorized"):
            jc._search_jql(BASE_CONFIG, "project = TEST", ["summary"])

    @patch("jira_client._make_session")
    def test_correct_url_and_headers(self, mock_make_session):
        session = _mock_session(_mock_response({"issues": [], "isLast": True}))
        mock_make_session.return_value = session
        jc._search_jql(BASE_CONFIG, "project = TEST", ["summary"])

        _, kwargs = session.post.call_args
        self.assertEqual(
            session.post.call_args[0][0],
            "https://test.atlassian.net/rest/api/3/search/jql",
        )
        self.assertEqual(kwargs["headers"]["Accept"], "application/json")
        self.assertEqual(kwargs["timeout"], 30)


# ---------------------------------------------------------------------------
# fetch_committed_epics
# ---------------------------------------------------------------------------

class TestFetchCommittedEpics(unittest.TestCase):

    def setUp(self):
        os.environ["TEST_JIRA_TOKEN"] = "token123"

    def tearDown(self):
        os.environ.pop("TEST_JIRA_TOKEN", None)

    def _make_raw_epic(self, key, summary, team_value, parent=None):
        return {
            "key": key,
            "fields": {
                "summary": summary,
                "customfield_10817": {"value": team_value, "id": "1"},
                "parent": parent,
            },
        }

    @patch("jira_client._make_session")
    def test_returns_mapped_epics(self, mock_make_session):
        session = _mock_session(_mock_response({
            "issues": [
                self._make_raw_epic("PROJ-1", "Epic A", "Recruiting"),
                self._make_raw_epic("PROJ-2", "Epic B", "Onboarding"),
            ],
            "isLast": True,
        }))
        mock_make_session.return_value = session

        result = jc.fetch_committed_epics(BASE_CONFIG)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {
            "key": "PROJ-1",
            "summary": "Epic A",
            "team_field_value": "Recruiting",
            "initiative_key": None,
            "initiative_summary": None,
            "health": None,
        })
        self.assertEqual(result[1]["team_field_value"], "Onboarding")

    @patch("jira_client._make_session")
    def test_jql_contains_committed_quarter_field_and_value(self, mock_make_session):
        session = _mock_session(_mock_response({"issues": [], "isLast": True}))
        mock_make_session.return_value = session
        jc.fetch_committed_epics(BASE_CONFIG)

        body = session.post.call_args[1]["json"]
        self.assertIn("cf[11245]", body["jql"])
        self.assertIn("FY26 Quarter 4", body["jql"])
        self.assertIn("issuetype = Epic", body["jql"])

    @patch("jira_client._make_session")
    def test_team_field_included_in_fields(self, mock_make_session):
        session = _mock_session(_mock_response({"issues": [], "isLast": True}))
        mock_make_session.return_value = session
        jc.fetch_committed_epics(BASE_CONFIG)

        body = session.post.call_args[1]["json"]
        self.assertIn("customfield_10817", body["fields"])
        self.assertIn("parent", body["fields"])

    @patch("jira_client._make_session")
    def test_missing_team_field_value_returns_none(self, mock_make_session):
        session = _mock_session(_mock_response({
            "issues": [{"key": "P-1", "fields": {"summary": "No team", "customfield_10817": None, "parent": None}}],
            "isLast": True,
        }))
        mock_make_session.return_value = session

        result = jc.fetch_committed_epics(BASE_CONFIG)
        self.assertIsNone(result[0]["team_field_value"])

    @patch("jira_client._make_session")
    def test_plain_string_team_field(self, mock_make_session):
        """Some Jira configs return the team field as a plain string, not an object."""
        session = _mock_session(_mock_response({
            "issues": [{"key": "P-1", "fields": {"summary": "S", "customfield_10817": "Learning", "parent": None}}],
            "isLast": True,
        }))
        mock_make_session.return_value = session

        result = jc.fetch_committed_epics(BASE_CONFIG)
        self.assertEqual(result[0]["team_field_value"], "Learning")


# ---------------------------------------------------------------------------
# fetch_epic_children
# ---------------------------------------------------------------------------

class TestFetchEpicChildren(unittest.TestCase):

    def setUp(self):
        os.environ["TEST_JIRA_TOKEN"] = "token123"

    def tearDown(self):
        os.environ.pop("TEST_JIRA_TOKEN", None)

    def _make_raw_child(self, key, status_category, story_points):
        return {
            "key": key,
            "fields": {
                "summary": f"Task {key}",
                "status": {
                    "statusCategory": {"key": status_category},
                },
                "customfield_10016": story_points,
            },
        }

    @patch("jira_client._make_session")
    def test_returns_children_with_correct_fields(self, mock_make_session):
        session = _mock_session(_mock_response({
            "issues": [
                self._make_raw_child("P-10", "done", 5),
                self._make_raw_child("P-11", "indeterminate", 3),
                self._make_raw_child("P-12", "new", None),
            ],
            "isLast": True,
        }))
        mock_make_session.return_value = session

        result = jc.fetch_epic_children(BASE_CONFIG, "P-5")

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], {
            "key": "P-10",
            "summary": "Task P-10",
            "status_category": "done",
            "story_points": 5.0,
        })
        self.assertIsNone(result[2]["story_points"])

    @patch("jira_client._make_session")
    def test_next_gen_jql_uses_parent(self, mock_make_session):
        session = _mock_session(_mock_response({"issues": [], "isLast": True}))
        mock_make_session.return_value = session
        jc.fetch_epic_children(BASE_CONFIG, "P-5")

        body = session.post.call_args[1]["json"]
        self.assertIn("parent = P-5", body["jql"])
        self.assertNotIn("Epic Link", body["jql"])

    @patch("jira_client._make_session")
    def test_classic_jql_uses_epic_link(self, mock_make_session):
        session = _mock_session(_mock_response({"issues": [], "isLast": True}))
        mock_make_session.return_value = session
        classic_config = {
            "jira": {**BASE_CONFIG["jira"], "epic_link_mode": "epic_link"}
        }

        jc.fetch_epic_children(classic_config, "P-5")

        body = session.post.call_args[1]["json"]
        self.assertIn('"Epic Link" = P-5', body["jql"])
        self.assertNotIn("parent =", body["jql"])

    @patch("jira_client._make_session")
    def test_story_points_coerced_to_float(self, mock_make_session):
        """Jira sometimes returns story points as an integer."""
        session = _mock_session(_mock_response({
            "issues": [self._make_raw_child("P-10", "done", 8)],
            "isLast": True,
        }))
        mock_make_session.return_value = session

        result = jc.fetch_epic_children(BASE_CONFIG, "P-5")
        self.assertIsInstance(result[0]["story_points"], float)
        self.assertEqual(result[0]["story_points"], 8.0)

    @patch("jira_client._make_session")
    def test_missing_status_category_defaults_to_new(self, mock_make_session):
        session = _mock_session(_mock_response({
            "issues": [{
                "key": "P-20",
                "fields": {
                    "summary": "No status",
                    "status": {},
                    "customfield_10016": 2,
                },
            }],
            "isLast": True,
        }))
        mock_make_session.return_value = session

        result = jc.fetch_epic_children(BASE_CONFIG, "P-5")
        self.assertEqual(result[0]["status_category"], "new")

    @patch("jira_client._make_session")
    def test_story_points_field_included_in_request(self, mock_make_session):
        session = _mock_session(_mock_response({"issues": [], "isLast": True}))
        mock_make_session.return_value = session
        jc.fetch_epic_children(BASE_CONFIG, "P-5")

        body = session.post.call_args[1]["json"]
        self.assertIn("customfield_10016", body["fields"])
        self.assertIn("status", body["fields"])


if __name__ == "__main__":
    unittest.main()
