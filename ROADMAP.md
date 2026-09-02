# Report Enhancement Ideas

High-value, low-effort additions to the generated HTML report, ranked by payoff per unit of work.

Baseline (already shipped, do not re-implement): DataTables search + sort, export buttons
(copy / CSV / Excel / print / column visibility), Dashboard charts, Trends, Suite Highlights,
Archives, Screenshots on failure, API Logs (attached calls, JSON and text), and rerun support.

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

### 3. Slowest-tests panel — SHIPPED
`ConfigVars._duration` is already captured per test (`html_reporter.py:41`) and rendered into
`%(dur)%`. Sort it, take the top 10, render a horizontal bar list on the Dashboard.

*Why:* free performance visibility from data already collected.
*Effort:* ~40 lines.
*Shipped as:* a horizontal bar chart on the Analytics tab rather than on the Dashboard, which is a
fixed-height one-screen viewport with no room left in it. Tests measuring 0.0s are left out — ten
rows of "slowest test: no time at all" reads as a chart that failed to load rather than as a fast
suite. It sits beside a duration histogram, which answers the question the top-10 cannot: two
thousand tests at 300ms each is a different problem from ten tests at a minute.

### 4. Copy-error and copy-rerun-command buttons — SHIPPED
Next to each failure message, a copy icon for the full traceback and one that yields
`pytest path/to/test.py::test_name`. Suite name and test name are both already in the row —
it is string concatenation.

*Why:* removes the most repeated manual step in day-to-day triage.
*Effort:* ~20 lines.
*Shipped as:* both halves, the copy button first and the rerun command after it.
`FloatingError` now renders an expand, a copy and a rerun button carrying the error and the command
in `data-` attributes. The command is built from the test's node id rather than by concatenating the
two names in the row: those are what a person reads, and a test inside a class is listed under its
own name where pytest wants the class in front of it. A node id a shell would not read as one word
is quoted, since a parametrised test's brackets are a glob pattern to zsh.
and the `(...)` link and its per-row Bootstrap modal are gone: the full error opens in the same
overlay the `Logs` column uses, which gave the dialog a `Copy` button and a `<pre>` body for free.
The old modal's `<p>` had been collapsing every traceback into one run-on line. One delegated click
handler serves the rows, because DataTables rebuilds them on each sort, search and page change.

Since #5 there are four of these buttons, and the tick that replaces an icon is the same tick for
all of them — so a click also puts a word in the middle of the page: `Error copied`, `Command
copied`, `Link copied`, faded in and gone in a second and a half. That is both the half that is
legible from wherever the pointer is, 22 pixels of button at the end of a long row not being it,
and the half that says *which* of the three landed. A refused clipboard — which is what `file://`
gets in some browsers — says `Press Ctrl+C to copy` there rather than leaving a button that did
nothing and no reason why. It takes no clicks, so the row underneath stays live while it is up. It
also shows what went onto the clipboard rather than only a word about it, four lines of it, with
anything past that faded out rather than cut off square — the preview is `aria-hidden`, because the
panel is a live region and a traceback read out after `Error copied` is not the news.

The four of them also fold away. At one button per action a table of forty failures carries 160 of
them for the one somebody wants, so they collapse behind the `...` — width and opacity rather than
`display: none`, which cannot be transitioned and leaves nothing to animate — and unfold along the
row a tenth of a second apart when it is pressed. One row is open at a time, and a click anywhere
else or Escape shuts it: this is the set of actions on one failure, not a mode the table stays in.

Their widths are taken in **one step**, with only the opacity and the transform animated. Growing
the widths reflowed the cell on every frame of the animation, so a strip with no room left on its
line jumped to the next one part-way through, at whichever frame it stopped fitting. Settling the
layout in one go leaves a single known move, which `slideRowActions` animates by putting the strip
back where it was and letting it travel — the row's height still changes in one step, but following
the strip is what makes the new line read as somewhere it went rather than somewhere it reappeared.

The cut message itself no longer ends in an ellipsis either — its last eight characters fade out,
which is the answer the report title already gave to the same question and costs none of a narrow
cell's width. Painted on those characters rather than as a mask down the cell's right-hand edge, so
it lands on the end of the text wherever the line wraps; and the gradient names `--text-body`
rather than `currentcolor`, because painting text with a background means `color: transparent` and
`currentcolor` would then fade from nothing to nothing. The ellipsis stays in the cell, hidden: the
CSV, Excel and print exports are built from cell text, they cannot carry a gradient, and a message
cut short with nothing to say so is a trap in a file read a week later.

### 5. Deep-linkable rows — SHIPPED
The template already listens for `hashchange` (`template.html:2990`). Give each test row an
anchor id so a failure can be pasted into Slack and open directly. Pairs with #4.

*Effort:* ~15 lines.
*Shipped as:* `row_anchor` in `util.py` and `anchor_for_row` on the reporter, an `id` on every
`<tr>`, a fourth `msg-link` button in `FloatingError`, and `scrollToTestRow` / `pageToTestRow` /
`markTestRow` behind a `#test-...` branch in `openPageFromHash`.

**The id the rows already had was the one thing the anchor could not be.** `runt` numbers them
`suite-row` in the order they are written, and it is what the Logs, Data and Steps buttons open
their panels by — but a link is pasted into a chat window and opened hours later, against whatever
report is at that address by then. A positional anchor still *resolves*: it opens whichever test
has since taken that place, with nothing on the page to say it is not the one that was sent. The
anchor is built from the node id instead, so it survives three tests being added in front of it,
and a link into a CI job's latest report keeps pointing at the same test build after build.

**Readable, not a bare hash.** The node id flattened to letters, digits and dashes and cut back to
a whole word, with six hex digits of the *whole* node id after it. The slug is what says which test
a link opens while it is still sitting in the chat window; the digits are what keep two tests apart
when the slug is cut to the same string, or when they differ only in the punctuation the slug drops
— `test_one[a-b]` beside `test_one[a_b]`. Percent-escaping the node id instead would have kept it
exact, but a fragment of `%5B` and `%3A%3A` is not a link anyone reads, and brackets do not survive
every chat client's own linkifier intact.

**The row is found through the DataTables API, not with `getElementById`.** Only the current page
of the table is in the document, so a row on page four is not there to be found at all: its
position in the filtered, sorted set is what its page is computed from, and the table is paged to
it before anything is scrolled. Every filter hiding it is cleared first — the search box, the
column searches, and the status chips (#2), which are a column search with a piece of state of
their own, so clearing one without the other leaves the chips holding the counts of a filter that
is no longer on.

Three smaller decisions. The tab is opened by calling `openPage` directly rather than clicking the
nav link, whose `href` would replace the row anchor in the URL with `#test-metrics` — the same
thing the archive deep link had to do, for the same reason. The jump waits for `window.load` when
the page is still coming up, because the table it pages through is built there and the flash saying
which row it is would otherwise burn out behind the loader. And a node id that appears twice —
`pytest-repeat`, or a rerun collected rather than merged — has its repeats numbered: two rows
answering to one link is invalid HTML, and it would silently open the first of them.

---

## Tier 2 — small collection change, big payoff

### 6. Markers and parametrize as columns / badges — SHIPPED
`item` is available in `pytest_runtest_teardown`; `item.own_markers` and `item.callspec.params`
come free. Adds `@smoke` / `@regression` badges and makes marker-based filtering work through the
existing search box.

*Why:* parametrized cases currently show only as opaque `test_x[a-b-c]`.
*Effort:* ~25 lines.
*Shipped as:* `pytest_html_reporter/markers.py`, rendered as badges on the `Test Steps` tab (#16) rather
than as a Test Metrics column — the table already carries eight columns, and a marker list is a fact
about a test rather than a value to sort a table by. Marker text is in the tab's search index, so
marker-based filtering works there.

**`own_markers` was the wrong source, and it fails silently.** It holds only the markers written on the
test itself, so a module-level `pytestmark`, a `@pytest.mark.parametrize` on the class, and anything
applied by a plugin are all absent from it — nothing errors, the badges are just quietly incomplete.
`iter_markers_with_node()` walks out through class, module, package and session and hands back the node
each marker came from, which is also what lets a badge say *where* it was written — the answer when
nobody remembers applying it. Its pairs are `(node, mark)`, which reads like the wrong way round and
takes down every test in the run if you believe the reading.

Two markers are deliberately cut down. `parametrize` carries every row the test will ever run with — a
hundred rows on one badge — so only the argument names are kept, and this case's own row is shown as its
parameters, read off `callspec.params`. And a `skipif` condition is evaluated at import, so it arrives as
a bare `True`/`False` rather than `sys.platform == "win32"`; the reason is shown instead of a bool that
means nothing.

Fixtures come from the test's own signature plus `usefixtures`, not from `item.fixturenames` — that is the
whole transitive closure, so asking for `tmp_path` dragged in `tmp_path_factory` and every autouse fixture
in every conftest above the test, and a test naming two fixtures read as a test naming nine.

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

### 8. Flaky test detection from archives — SHIPPED
`load_archive` already reads every archived `output.json`. Flag any test whose status flipped
across retained builds as flaky, with a "flakiest tests" card.

*Why:* genuinely differentiating, and the data is already on disk.
*Effort:* ~50 lines in `pytest_html_reporter/util.py`, reusing the existing archive loop.
*Shipped as:* `pytest_html_reporter/analytics.py` and the whole Analytics tab, not a card. Once the
archives are being read per test rather than per build, a flake rate is one of about eight things
that fall out of the same pass — pass-rate drift, failing streaks, fixed/regressed/added/dropped
between builds, duration bands — and a single card would have thrown the other seven away.

It is its own module rather than more of `util.py`: the archive loop there builds page fragments as
it goes, and this needs the builds as data first and rendering second. Two things had to be settled
before any of the numbers meant anything. Flaky and always-failing are counted apart — a test that
only ever fails is a bug with an owner, and putting it top of a flakiness list sends somebody
hunting a race that is not there. And skips are excluded from the pass/fail arithmetic rather than
counted against a test, or a test skipped for three builds between two passes reads as two flips.

`output.json` gained a per-test `duration` in the same change. Without it the duration panels could
only ever describe the current run, because a number that was never stored is a number no later
build can show; archives written before it have no key and are read as *not measured*, never as zero.

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

### 11. Delta vs previous run — SHIPPED
"+3 failures since last build" on the Dashboard, computed from the most recent archive JSON
that is already loaded.

*Why:* direction of travel matters more than the absolute count.
*Effort:* ~20 lines.
*Shipped as:* `run_delta` / `format_run_delta` / `run_delta_class` / `run_delta_title` and
`run_delta_figure` / `run_delta_unit` / `generate_run_delta` in `util.py`, rendered as a
`.delta-highlight` tile - arrow, signed figure, unit, right-pinned caption - as the second entry in
the Highlights card, which lost its "Suite" prefix in the process because it now holds two kinds of
thing.

Read off `ConfigVars.tfail` rather than re-reading the archive folder: `update_trends` has already
built the per-build list - this run first, then the archived builds newest first - and taking the
headline from the same list the Trends chart is drawn from means the two cannot disagree. That also
settles what a "failure" is here: failures and errors together, which is what the chart's Failed
series plots - and it is why the line ended up on the Trends card rather than the summary card,
where it read as a fourth statistic about this build instead of the headline for the chart it
describes.

The Trends card was tried first and given up: as a subtitle it pushed the chart down, and
`.dashboard__headers`' own `-4%` bottom margin - tuned for a heading of one line - then pulled the
chart back up over it; absolutely positioned in the card's corner it cleared the chart but needed
two separately scoped offsets, one to dodge the `position: fixed` download icon and one for the
width below which it and the centred heading stop fitting on a row. The Highlights card takes it
with none of that: the card is a list of findings about the run, so a second entry is what it is
already shaped for.

Three decisions worth keeping. No change is written **`±0`**, not `0`: beside `SINCE LAST BUILD` a
bare `0 failures` says the opposite of what it means. The arrow is a **plain character**, not an
icon font - it inherits colour and size for free and cannot render as a missing glyph in a report
opened somewhere the font never loaded. And a first build hides the **whole tile, caption
included**, via `is-empty` on the wrapper rather than `:empty` on the text: a lone
`SINCE LAST BUILD` over blank space reads as a bug.

Two decisions worth keeping: a **first build shows nothing at all** rather than "no change", which
would claim a previous build that does not exist - the placeholder fills in empty and `:empty`
collapses the line. And the colours **run the opposite way to the coverage chip's**: there, up is
the good direction; here, more failures than last time is the bad one, so the classes are named
`is-worse` / `is-better` rather than reusing `is-up` / `is-down` and quietly inverting them.

### 12. Build / commit metadata option
A `--build-info` option accepting arbitrary `key=value` pairs (CI job URL, git SHA, branch)
rendered in the header.

*Why:* makes the report meaningfully more useful in CI.
*Effort:* ~25 lines.

---

### 13. Text and API-call attachments — SHIPPED
Issue #191: a picture is no use when the thing under test is an API.

*Shipped as:* `pytest_html_reporter/attachments.py` (`attach_text`, `attach_json`, `attach_api`,
`attach_file`), the four `Attachment*` components, an `API Logs` tab, a `Data` column on Test
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

### 14. Archive retention by age — SHIPPED
Issue #223: an hourly schedule keeps every build for ever, and two months in, the report is slow to open.

*Shipped as:* `--archive-days` and `--archive-since` beside the existing `--archive-count`, with `archive_count`,
`archive_days` and `archive_since` ini keys, and the retention logic itself in `util.py`
(`archive_cutoff`, `archive_timestamp`, `expired_archives`).

The issue asked for a date *range*; the answer is a rolling window instead. Removing a middle slice while keeping
older builds either side is not a retention policy — it leaves a hole in the trends chart, which reads straight off
the same files. The limits intersect rather than override, so a count and an age can be set together without either
one quietly widening the other.

Nothing else needed changing: the archives tab, the trends chart and Suite Highlights all glob the same
`archive/*.json`, so pruning the folder shrinks the page for free. At roughly 5KB of page per retained build, that is
the whole of the load-time complaint.

Two bugs surfaced on the way. `--archive-count` computed its folder from `self.path`, so it silently did nothing
whenever `--html-report` named the `.html` file itself; and retention sorted on mtime, which in CI is the moment of
the checkout rather than the moment of the run — the run's real start time was in the file name all along.

---

### 15. Test coverage — SHIPPED
Issue #203: a percentage on the page, "a cake graph ... or a circle percentage bar", and either the
coverage html report embedded or a section of its own. A later comment asked for two things by name:
custom links in the menu, and the numbers from `pytest-cov`.

*Shipped as:* `pytest_html_reporter/coverage_report.py`, a `Test Coverage` tab, the `CoverageRow` /
`CoverageTile` / `CoverageChip` components, `--report-coverage`, `--report-coverage-file`,
`--report-coverage-limit`, and `--report-link` for the menu half.

**The embed was the wrong half of the ask.** An iframe over `htmlcov/` breaks the one property the
whole reporter is built on — a single file you can mail, publish as a CI artifact, or open off a
stick — and it breaks it *silently*, showing an empty frame wherever the folder did not travel with
the page. So the numbers are read and drawn natively, and `htmlcov` is **linked**, which is the only
part of it a summary genuinely cannot replace. The link is offered only when the folder's `index.html`
was written after this run started: coverage.py names that folder whether or not `--cov-report=html`
was asked for, so a stale one sits there looking exactly like a fresh one.

**Read, not measured, and no hook to order.** pytest-cov calls `cov_controller.finish()` from
`pytest_runtestloop` — stopping, saving and combining every xdist worker's data — which is long over
by the time this report is written from `pytest_terminal_summary`. So the `Coverage` object is simply
read off `config.pluginmanager.getplugin('_cov')`, and nothing had to be declared `trylast` to race it.

**The number is coverage.py's own.** Taken through the public `json_report()` API — to a temp file,
because it writes to a path rather than a file object — rather than summed out of `analysis2()` or
lifted from `coverage.jsonreport`. That round trip buys the one guarantee worth having: with
`--cov-branch` on, `percent_covered` already folds branches in the way pytest-cov folds them in, so
the tab and the terminal beside it cannot print different totals. A report that disagrees with the
terminal it was generated next to is a bug report waiting to be filed. The same reasoning gave the ring
its colour: `--cov-fail-under`, when set, is the line the colour is drawn at, because the project has
already said where its own bar is.

Three sources, in that order of trust: the live plugin, then a `coverage.json` or Cobertura
`coverage.xml` found beside the report, then a file named outright. The xml path needs no `coverage`
package installed at all, which is what makes it the useful one when the reporting job is not the job
that ran the tests. A `.coverage` data file is read only when named — one is usually left over from a
run days ago, and quietly publishing last Tuesday's number is worse than publishing none. Every source
is stated in the tab, with the file's own timestamp when it has one.

`output.json` gained a `coverage` block beside the test counts rather than a file of its own: the
archives, the trend chart and Suite Highlights all read that file already, so one percentage kept there
is a percentage every one of them can reach. That is where the `+0.8 since the last build` and the
trend line come from, at no new cost. A build that measured nothing is `None`, not `0` — a gap in the
line rather than a cliff it never fell off.

Two smaller decisions worth keeping. Files are sorted **least covered first**, which is both the useful
default and the only defensible way to cut the list when `--report-coverage-limit` bites: a cap that
kept the alphabetical head would hide exactly the files the tab is opened to find. And the `Branches`
column is **dropped** when a run measured no branches, rather than filled with a column of dashes whose
only message is that `--cov-branch` was not passed.

The dashboard got a chip, not the ring. Same finding as #1: the dashboard is a fixed-height flex column
at >=1200px, and a third row compresses both chart rows. The chip states the figure and crosses to the
tab, where the ring, the per-file split and the trend all have room.

---


---

### 16. Test steps — SHIPPED
Nested, individually timed steps with per-step attachments, after Allure's steps feature.

*Shipped as:* `pytest_html_reporter/steps.py` (the `step` decorator / context manager),
`markers.py` (#6), `bdd.py` (pytest-bdd), `step_report.py` (rendering), eight `Step*` components, a
`Test Steps` tab, a `Steps` column on Test Metrics, and `--report-steps` / `--report-step-limit`.

**A tab of its own, not a panel inside Test Suites.** Allure keeps steps inside its suites view; the cost
is a high-level page you can no longer skim, and the high-level page is the one most people open first.
Here the drill-down is the tab's whole job — suite, then test, then what the test did — and Test Suites
stays a page of totals.

**The tab had to be worth opening before anyone writes a single `step()`.** A feature that shows an empty
panel until the suite is rewritten is a feature nobody adopts. So the tree is built from what pytest
already knows: every test has a set up, a body and a tear down, each timed from pytest's own per-phase
report, and every test carries its markers, parameters, fixtures and docstring. Naming steps makes the
tree deeper — it does not bring it into existence. The teaching panel only appears while nobody has named
one, and the tree stays visible underneath it.

**Gherkin was free, and had one landmine.** A pytest-bdd scenario is already a list of named steps, so its
Given/When/Then arrive with no changes to the suite. The landmine is the guard: pytest does not warn about
an unknown hook and does not skip it — it *refuses to start*, with
`PluginValidationError: unknown hook 'pytest_bdd_after_step'`. Declaring those hooks plainly would have
broken every run that does not have pytest-bdd installed, which is most of them. `optionalhook=True` is
the whole of the defence, and there is a test asserting it on every one of them, because the failure mode
is a hard stop for users who never asked for the feature.

Four decisions worth keeping:

*The message goes on the step that raised.* An exception walks out through every step it was raised
inside, and each of those genuinely failed — but printing the traceback once per level put the only one
that says *where* furthest down the page. Ancestors are marked failed without the text. Identity is
tracked by holding the exception object, not its `id()`: a caught exception is collected and CPython hands
the same id straight to the next one, which silently swallowed the second of two identical-looking
failures.

*Nesting is counted from each phase's floor.* A `yield` fixture holds its `with step(...)` open across the
whole test, so counting depth from the stack alone reported every step the test body ran as a step *of the
fixture* — one `Open a session` swallowing the test that used it.

*Bars are scaled within the test.* The question in front of a step tree is always "which part of this test
was slow", never "which test was slow" — scaling across the run draws a flat line for every test but one.

*Steps are per-thread.* One stack shared by every thread came back nested in whatever order the threads
interleaved: a tree that never existed. Each thread nests within itself, and a background thread's steps
land at the top level.

The tab's own durations are summed from the per-phase milliseconds rather than the record's
seconds-rounded-to-two-places, where every test faster than 5ms arrived as a flat `0`. Step trees are
parked outside the metrics table for the same reason logs and attachments are, and a retry reports the
steps of the attempt that stuck — the failing attempt's tree beside a green test would describe a run that
did not happen.

---

## Suggested next release

**#1, #2, #4, #7.** Together they are roughly one afternoon, need no schema change to
`output.json`, and address the two most common complaints about HTML reporters: "I can't see the
logs" and "I can't filter to just the failures."

All four have shipped, #4 and the deep links (#5) that pair with it last. #13 shipped separately, off
issue #191, #14 off #223 and #15 off #203.
