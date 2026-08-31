# Report Enhancement Ideas

High-value, low-effort additions to the generated HTML report, ranked by payoff per unit of work.

Baseline (already shipped, do not re-implement): DataTables search + sort, export buttons
(copy / CSV / Excel / print / column visibility), Dashboard charts, Trends, Suite Highlights,
Archives, Screenshots on failure, Attachments (text / JSON / API calls), and rerun support.

---

## Tier 1 — nearly free, high value

### 1. Environment / run metadata block — SHIPPED
The code is already written and commented out in `pytest_html_reporter/html_reporter.py:512-515`
(`platform.uname()`, python version, generated date), but the matching `__executed_by__` /
`__os_name__` / `__python_version__` / `__generated_date__` placeholders no longer exist in
`html_page/html/template.html`. Re-add them as a small card on the Dashboard, plus pytest
version, CLI args, and the active plugin list.

*Why:* anyone triaging a failure asks "which machine / which Python?" first.
*Effort:* ~30 lines. Zero new data collection.
*Shipped as:* `generate_environment_info` in `util.py`, the `EnvRow` component, and an overlay
opened from a chip on the summary card's existing "Time taken" line. An inline strip was tried first and rejected: the
dashboard is a fixed-height flex column at >=1200px, so a third row compressed both chart rows.
The overlay adds nothing to that layout.

### 2. Status filter chips on Test Metrics
The Dashboard already renders PASS / FAIL / SKIP / xPASS / xFAIL / ERROR counts. Make those pills
clickable so they drive `table.column(2).search(...)` on the existing DataTable.

*Why:* one-click "show me only the failures" is the most common action on a report like this.
*Effort:* ~15 lines of JS. The DataTables API is already loaded.

### 3. Slowest-tests panel
`ConfigVars._duration` is already captured per test (`html_reporter.py:41`) and rendered into
`%(dur)%`. Sort it, take the top 10, render a horizontal bar list on the Dashboard.

*Why:* free performance visibility from data already collected.
*Effort:* ~40 lines.

### 4. Copy-error and copy-rerun-command buttons
Next to each failure message, a copy icon for the full traceback and one that yields
`pytest path/to/test.py::test_name`. Suite name and test name are both already in the row —
it is string concatenation.

*Why:* removes the most repeated manual step in day-to-day triage.
*Effort:* ~20 lines.

### 5. Deep-linkable rows
The template already listens for `hashchange` (`template.html:2990`). Give each test row an
anchor id so a failure can be pasted into Slack and open directly. Pairs with #4.

*Effort:* ~15 lines.

---

## Tier 2 — small collection change, big payoff

### 6. Markers and parametrize as columns / badges
`item` is available in `pytest_runtest_teardown`; `item.own_markers` and `item.callspec.params`
come free. Adds `@smoke` / `@regression` badges and makes marker-based filtering work through the
existing search box.

*Why:* parametrized cases currently show only as opaque `test_x[a-b-c]`.
*Effort:* ~25 lines.

### 7. Captured stdout / stderr / logs — SHIPPED
`rep.capstdout`, `rep.capstderr`, and `rep.caplog` are already on the report object handled in
`pytest_runtest_makereport` (`html_reporter.py:141`) — currently only `longreprtext` lines
starting with `E ` are kept. Show the rest in a collapsible section under the error.

*Why:* this is the biggest single gap versus `pytest-html`.
*Effort:* ~40 lines, mostly template.
*Shipped as:* a `Logs` column on Test Metrics opening a shared overlay, with the section helpers in
`util.py`, the `TestLog` / `TestLogSection` components, and `--report-logs` / `--report-log-limit`.
It covers every test rather than only failures, and every phase rather than only `call`: a record is
built from the teardown hook, before pytest has finished capturing that phase, so the teardown
sections are folded into the stored record afterwards. The text is parked outside the table — a cell
holding it would be pulled into the DataTables search index and into every CSV / Excel / print
export. A per-test character cap keeps one chatty test from outweighing the rest of the file.

### 8. Flaky test detection from archives
`load_archive` already reads every archived `output.json`. Flag any test whose status flipped
across retained builds as flaky, with a "flakiest tests" card.

*Why:* genuinely differentiating, and the data is already on disk.
*Effort:* ~50 lines in `pytest_html_reporter/util.py`, reusing the existing archive loop.

### 9. Failure grouping by exception type
Parse the first line of each captured error and group — "12 failures, 9 are `TimeoutException`".
Pure post-processing on `_current_error`.

*Why:* turns a wall of red into one actionable insight.
*Effort:* ~30 lines.

---

## Tier 3 — polish, still cheap

### 10. Dark mode toggle
The CSS is one large block with hardcoded colors. Converting to CSS custom properties plus a
`[data-theme]` override and a `localStorage`-backed toggle is mechanical work.

*Effort:* a couple of hours, mostly find-and-replace.

### 11. Delta vs previous run
"+3 failures since last build" on the Dashboard, computed from the most recent archive JSON
that is already loaded.

*Effort:* ~20 lines.

### 12. Build / commit metadata option
A `--build-info` option accepting arbitrary `key=value` pairs (CI job URL, git SHA, branch)
rendered in the header.

*Why:* makes the report meaningfully more useful in CI.
*Effort:* ~25 lines.

---

### 13. Text and API-call attachments — SHIPPED
Issue #191: a picture is no use when the thing under test is an API.

*Shipped as:* `pytest_html_reporter/attachments.py` (`attach_text`, `attach_json`, `attach_api`,
`attach_file`), the four `Attachment*` components, an `Attachments` tab, a `Data` column on Test
Metrics, and `--report-attachments` / `--report-attachment-limit`. The collection path mirrors
screenshots (a buffer drained by every record, so nothing leaks to the next test) and the storage
path mirrors logs (payloads parked outside the table, out of its search index and its exports).

Three decisions worth keeping: response objects are read by **duck typing**, so requests and httpx
both work with no new dependency and every field stays overridable for clients that resemble
neither; credentials are **redacted by default**, because a report is a build artifact that gets
published and pasted around; and a trimmed payload keeps its **head**, the opposite of a trimmed
log, because a response puts its status and its error field at the top while a log puts the
interesting lines at the end.

---

## Suggested next release

**#1, #2, #4, #7.** Together they are roughly one afternoon, need no schema change to
`output.json`, and address the two most common complaints about HTML reporters: "I can't see the
logs" and "I can't filter to just the failures."

#1, #2 and #7 have shipped; #4 is what is left of that set. #13 shipped separately, off issue #191.
