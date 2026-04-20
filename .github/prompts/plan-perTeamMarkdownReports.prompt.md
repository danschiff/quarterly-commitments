# Plan: Per-Team Markdown Reports

Generate a separate markdown file per team in `reports/YYYY-MM-DD/`, in addition to the existing combined report.

---

## Phase 1 — Extract shared rendering helper in `report.py`

**Step 1:** Add `_slugify(name)` — lowercase, replace spaces/`&`/special chars with hyphens, strip consecutive hyphens. Simple `re.sub`, no deps.

**Step 2:** Add `_render_team_lines(team, quarter_pct, config, header_level=2)` — returns `list[str]` of markdown lines for one team. Extracted from the per-team loop in `write_markdown_report()` (lines 206–260). `header_level` controls `##` (combined) vs `#` (per-team); initiative headers are always one level below.

**Step 3:** Refactor `write_markdown_report()` inner loop to call `_render_team_lines()`. Output must be byte-identical.

---

## Phase 2 — Add per-team file writing in `report.py`

**Step 4:** Add `write_team_markdown_report(team, quarter_pct, config, path)` — writes single-team file with H1 team header, metadata block, body from `_render_team_lines(header_level=1)`. Returns `Path`.

**Step 5:** Add `write_per_team_reports(team_summaries, quarter_pct, config, output_dir=None)` — creates `reports/YYYY-MM-DD/`, writes `_slugify(name).md` per team. Returns `list[Path]`.

---

## Phase 3 — Wire into `main.py`

**Step 6:** Import `write_per_team_reports`, call after `write_markdown_report()`, print `"Per-team reports written to reports/2026-04-20/ (8 files)"`.

---

## Files Changed

| File | Change |
|---|---|
| `report.py` | Add `_slugify()`, `_render_team_lines()`, `write_team_markdown_report()`, `write_per_team_reports()`; refactor inner loop of `write_markdown_report()` |
| `main.py` | Add `write_per_team_reports` import; add call + print after `write_markdown_report()` |

---

## Verification

1. `pytest tests/ -v` — existing tests pass (no changes needed)
2. `python main.py` — produces `report-2026-04-20.md` + `reports/2026-04-20/*.md` (8 files)
3. Spot-check `reports/2026-04-20/recruiting.md` — H1 team, H2 initiatives, same table data
4. Diff combined report against current output — no regressions

---

## Decisions

- Combined report preserved; per-team files are additional
- Output in `reports/YYYY-MM-DD/` subfolder
- Initiative headers promoted one level in per-team files (H2 vs H3)
- Always generated — no opt-out flag
- No new tests — verification is end-to-end
