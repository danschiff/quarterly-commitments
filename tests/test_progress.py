"""Tests for progress.py — pure math, no I/O, no mocking needed."""

import sys
import os
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from progress import quarter_pct_elapsed, epic_progress, is_slipping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(start, end):
    return {"quarter": {"start": start, "end": end}}


def _child(status_category, story_points):
    return {"status_category": status_category, "story_points": story_points}


# ---------------------------------------------------------------------------
# quarter_pct_elapsed
# ---------------------------------------------------------------------------

class TestQuarterPctElapsed(unittest.TestCase):

    def test_exactly_halfway(self):
        start = date(2026, 4, 1)
        end   = date(2026, 6, 30)
        mid   = start + timedelta(days=(end - start).days // 2)
        # Patch date.today by subclassing — simpler than mocking the C extension
        import progress
        original_date = progress.date

        class FakeDate(date):
            @classmethod
            def today(cls):
                return mid

        progress.date = FakeDate
        try:
            pct = quarter_pct_elapsed(_config("2026-04-01", "2026-06-30"))
            self.assertAlmostEqual(pct, 0.5, delta=0.01)
        finally:
            progress.date = original_date

    def test_before_quarter_clamps_to_zero(self):
        import progress
        original_date = progress.date

        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 3, 15)   # before Apr 1

        progress.date = FakeDate
        try:
            pct = quarter_pct_elapsed(_config("2026-04-01", "2026-06-30"))
            self.assertEqual(pct, 0.0)
        finally:
            progress.date = original_date

    def test_after_quarter_clamps_to_one(self):
        import progress
        original_date = progress.date

        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 7, 15)   # after Jun 30

        progress.date = FakeDate
        try:
            pct = quarter_pct_elapsed(_config("2026-04-01", "2026-06-30"))
            self.assertEqual(pct, 1.0)
        finally:
            progress.date = original_date

    def test_first_day_of_quarter(self):
        import progress
        original_date = progress.date

        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 4, 1)

        progress.date = FakeDate
        try:
            pct = quarter_pct_elapsed(_config("2026-04-01", "2026-06-30"))
            self.assertEqual(pct, 0.0)
        finally:
            progress.date = original_date

    def test_last_day_of_quarter(self):
        import progress
        original_date = progress.date

        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 6, 30)

        progress.date = FakeDate
        try:
            pct = quarter_pct_elapsed(_config("2026-04-01", "2026-06-30"))
            self.assertEqual(pct, 1.0)
        finally:
            progress.date = original_date

    def test_degenerate_start_equals_end(self):
        import progress
        original_date = progress.date

        class FakeDate(date):
            @classmethod
            def today(cls):
                return date(2026, 4, 1)

        progress.date = FakeDate
        try:
            pct = quarter_pct_elapsed(_config("2026-04-01", "2026-04-01"))
            self.assertEqual(pct, 1.0)
        finally:
            progress.date = original_date


# ---------------------------------------------------------------------------
# epic_progress
# ---------------------------------------------------------------------------

class TestEpicProgress(unittest.TestCase):

    def test_all_done_with_points(self):
        children = [
            _child("done", 5),
            _child("done", 3),
        ]
        r = epic_progress(children)
        self.assertEqual(r["total_pts"], 8.0)
        self.assertEqual(r["done_pts"], 8.0)
        self.assertAlmostEqual(r["pct_complete"], 1.0)
        self.assertFalse(r["unestimated"])
        self.assertEqual(r["done_issues"], 2)
        self.assertEqual(r["total_issues"], 2)

    def test_none_done(self):
        children = [_child("new", 5), _child("indeterminate", 3)]
        r = epic_progress(children)
        self.assertEqual(r["done_pts"], 0.0)
        self.assertAlmostEqual(r["pct_complete"], 0.0)
        self.assertEqual(r["done_issues"], 0)

    def test_partial_progress(self):
        children = [
            _child("done", 20),
            _child("new", 30),
            _child("indeterminate", 10),
        ]
        r = epic_progress(children)
        self.assertEqual(r["total_pts"], 60.0)
        self.assertEqual(r["done_pts"], 20.0)
        self.assertAlmostEqual(r["pct_complete"], 20 / 60)
        self.assertFalse(r["unestimated"])

    def test_no_story_points_is_unestimated(self):
        children = [_child("done", None), _child("new", None)]
        r = epic_progress(children)
        self.assertTrue(r["unestimated"])
        self.assertEqual(r["pct_complete"], 0.0)
        self.assertEqual(r["total_pts"], 0.0)

    def test_zero_story_points_is_unestimated(self):
        children = [_child("done", 0), _child("new", 0)]
        r = epic_progress(children)
        self.assertTrue(r["unestimated"])

    def test_mixed_none_and_numeric_points(self):
        """None story points count as 0, not as errors."""
        children = [
            _child("done", 5),
            _child("new", None),
        ]
        r = epic_progress(children)
        self.assertEqual(r["total_pts"], 5.0)
        self.assertEqual(r["done_pts"], 5.0)
        self.assertFalse(r["unestimated"])

    def test_empty_children(self):
        r = epic_progress([])
        self.assertEqual(r["total_pts"], 0.0)
        self.assertTrue(r["unestimated"])
        self.assertEqual(r["total_issues"], 0)

    def test_indeterminate_not_counted_as_done(self):
        children = [_child("indeterminate", 8)]
        r = epic_progress(children)
        self.assertEqual(r["done_pts"], 0.0)
        self.assertEqual(r["done_issues"], 0)


# ---------------------------------------------------------------------------
# is_slipping
# ---------------------------------------------------------------------------

class TestIsSlipping(unittest.TestCase):

    def test_exactly_at_target_not_slipping(self):
        # 50% through quarter, 50% complete → gap = 0, not slipping
        self.assertFalse(is_slipping(0.50, 0.50, 0.10))

    def test_within_buffer_not_slipping(self):
        # 50% through, 42% complete → gap = 8%, threshold = 10% → not slipping
        self.assertFalse(is_slipping(0.42, 0.50, 0.10))

    def test_exactly_at_threshold_boundary_not_slipping(self):
        # gap == threshold (not strictly greater) → not slipping
        self.assertFalse(is_slipping(0.40, 0.50, 0.10))

    def test_just_over_threshold_is_slipping(self):
        # 50% through, 39% complete → gap = 11% > 10% → slipping
        self.assertTrue(is_slipping(0.39, 0.50, 0.10))

    def test_far_behind_is_slipping(self):
        self.assertTrue(is_slipping(0.10, 0.75, 0.10))

    def test_ahead_of_target_not_slipping(self):
        # More done than expected
        self.assertFalse(is_slipping(0.80, 0.50, 0.10))

    def test_zero_progress_early_in_quarter_not_slipping(self):
        # 5% through the quarter, 0% done → gap = 5% < 10% → not slipping
        self.assertFalse(is_slipping(0.0, 0.05, 0.10))

    def test_zero_progress_halfway_through_is_slipping(self):
        # 50% through, 0% done → gap = 50% > 10% → slipping
        self.assertTrue(is_slipping(0.0, 0.50, 0.10))

    def test_custom_threshold(self):
        # With a 20% threshold, 35% complete at 50% elapsed → gap 15% < 20% → not slipping
        self.assertFalse(is_slipping(0.35, 0.50, 0.20))
        # But with 10% threshold the same numbers would slip
        self.assertTrue(is_slipping(0.35, 0.50, 0.10))


if __name__ == "__main__":
    unittest.main()
