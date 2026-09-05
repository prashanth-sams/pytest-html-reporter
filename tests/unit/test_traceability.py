"""Turning a marker into a link, an owner and a testcase property.

`@pytest.mark.jira("PROJ-123")` has always been collected and always been shown
- as a flat badge, because nothing in the report knew that PROJ-123 was an id
rather than a word. These cover the half that was missing: the pattern that
says where a marker points, the badge that opens it, the owner pulled out of
the row of tags, and the <property> that reaches the tools which never open an
html report at all.

The rules worth pinning are the ones that would be silently wrong if they
changed: a scheme that must not survive into an href, an argument that must not
be pasted into a url raw, a marker with empty brackets that must not become
half a link, and a suite that configured none of this getting exactly the
report it had before.
"""

from collections import OrderedDict

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.junit import junit_document
from pytest_html_reporter.markers import (
    OWNER_MARKER,
    SEVERITY_MARKER,
    describe,
    severity_rank,
    severity_value,
)
from pytest_html_reporter.step_report import (
    OWNER_SEPARATOR,
    _facts,
    _label,
    _severity_badges,
    _traced,
    generate_steps_view,
)
from pytest_html_reporter.util import (
    link_patterns,
    record_owners,
    record_severity,
    marker_url,
    parse_link_patterns,
    trace_markers,
)


class _Config:
    """Enough of pytest's Config for the option helpers to answer."""

    def __init__(self, options=None, ini=None):
        self._options = options or {}
        self._ini = ini or {}

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


def _marker(name, *args, **overrides):
    marker = {"name": name, "text": "%s(%s)" % (name, ", ".join(args)) if args else name,
              "args": list(args), "scope": "function", "kind": "user"}
    marker.update(overrides)
    return marker


@pytest.fixture
def isolate_patterns():
    """The rendering helpers read the resolved patterns off ConfigVars.

    Saved and put back rather than cleared: ConfigVars is class-level state, so
    a test that leaves its own patterns behind changes what the next one sees.
    """
    before = ConfigVars._link_patterns
    yield
    ConfigVars._link_patterns = before


@pytest.fixture
def patterns(isolate_patterns):
    ConfigVars._link_patterns = {"jira": "https://acme/browse/{}",
                                 "testcase": "https://rail/{}"}


def _record(*markers, **overrides):
    record = {"suite_name": "tests/test_pay.py", "test_name": "test_card",
              "status": "PASS", "steps": [], "attachments": [], "phases": {},
              "meta": {"markers": list(markers), "params": [], "fixtures": [], "doc": ""}}
    record.update(overrides)
    return record


# ------------------------------------------------------------- the pattern ---

def test_a_pattern_is_read_from_the_command_line_and_the_ini_together():
    config = _Config(options={"report_link_pattern": ["jira=https://acme/browse/{}"]},
                     ini={"report_link_pattern": ["testcase=https://rail/{}"]})

    assert link_patterns(config) == {"jira": "https://acme/browse/{}",
                                     "testcase": "https://rail/{}"}


def test_whitespace_around_the_marker_and_the_url_is_not_part_of_either():
    """An ini linelist is indented under its key, and a person types spaces."""
    assert parse_link_patterns(["  jira = https://acme/browse/{}  "]) == {
        "jira": "https://acme/browse/{}"}


def test_a_scheme_the_report_will_not_render_is_dropped_rather_than_linked():
    """The one rule here that is not a convenience.

    A badge is built per test out of whatever a marker said and lands in a file
    that gets published and mailed on. javascript: in an href is a way to run
    something in whoever opens the report.
    """
    patterns = parse_link_patterns(["bad=javascript:alert(1)",
                                    "worse=data:text/html;base64,x",
                                    "fine=https://acme/browse/{}"])

    assert patterns == {"fine": "https://acme/browse/{}"}


def test_an_entry_with_no_url_names_no_link():
    assert parse_link_patterns(["jira=", "=https://acme/{}", ""]) == {}


# ----------------------------------------------------------------- the url ---

def test_the_first_argument_is_what_goes_in_the_url():
    patterns = {"jira": "https://acme/browse/{}"}

    assert marker_url(patterns, _marker("jira", "PROJ-123")) == "https://acme/browse/PROJ-123"


def test_an_id_is_percent_encoded_on_the_way_into_the_url():
    """Ids are pasted out of trackers and arrive with whatever those allow."""
    patterns = {"jira": "https://acme/browse/{}"}

    assert marker_url(patterns, _marker("jira", "A B/C&D")) == \
        "https://acme/browse/A%20B%2FC%26D"


def test_a_url_keeps_the_braces_that_are_not_the_placeholder():
    """Substituted, never formatted.

    str.format reads every brace in the string, and a url is a place people put
    them - so formatting somebody's templated query throws KeyError instead of
    rendering their link.
    """
    assert marker_url({"page": "https://wiki/{space}/{}"}, _marker("page", "7")) == \
        "https://wiki/{space}/7"


def test_a_marker_with_empty_brackets_links_nowhere():
    """Half a url opens the tracker's front page and looks like it worked."""
    assert marker_url({"jira": "https://acme/browse/{}"}, _marker("jira")) == ""


def test_a_pattern_with_no_placeholder_is_a_fixed_destination():
    """`docs = https://wiki/testing` is a page, not a forgotten placeholder."""
    assert marker_url({"docs": "https://wiki/testing"}, _marker("docs")) == \
        "https://wiki/testing"


def test_a_marker_nobody_configured_points_nowhere():
    assert marker_url({"jira": "https://acme/{}"}, _marker("slow")) == ""
    assert marker_url({}, _marker("jira", "PROJ-1")) == ""


# ------------------------------------------------------------- the collector ---

def test_the_arguments_are_kept_beside_the_signature():
    """`text` is one string and cannot be taken back apart to find the id."""
    class Mark:
        name = "jira"
        args = ("PROJ-123",)
        kwargs = {}

    class Function:
        pass

    class Item:
        def iter_markers_with_node(self):
            return [(Function(), Mark())]

    marker = describe(Item())["markers"][0]

    assert marker["text"] == "jira(PROJ-123)"
    assert marker["args"] == ["PROJ-123"]


def test_an_owner_is_its_own_kind_of_marker():
    class Mark:
        name = OWNER_MARKER
        args = ("payments-team",)
        kwargs = {}

    class Function:
        pass

    class Item:
        def iter_markers_with_node(self):
            return [(Function(), Mark())]

    assert describe(Item())["markers"][0]["kind"] == "owner"


# ------------------------------------------------------------- the grouping ---

def test_linked_markers_are_grouped_by_the_marker_they_were_written_as(patterns):
    """A bare PROJ-123 says nothing about which system it is an id in."""
    linked, plain = _traced([_marker("jira", "PROJ-9"), _marker("slow"),
                             _marker("jira", "PROJ-10"), _marker("testcase", "C1")])

    assert list(linked) == ["jira", "testcase"]
    assert [m["args"][0] for m in linked["jira"]] == ["PROJ-9", "PROJ-10"]
    assert [m["name"] for m in plain] == ["slow"]


def test_a_marker_name_becomes_the_label_of_the_row_its_ids_sit_in():
    assert _label("jira") == "Jira"
    assert _label("test_case") == "Test case"
    assert _label("") == ""


# ----------------------------------------------------------------- the page ---

def test_an_id_is_rendered_as_a_link_that_opens_the_tracker(patterns):
    facts = _facts(_record(_marker("jira", "PROJ-123")))

    assert 'href="https://acme/browse/PROJ-123"' in facts
    assert 'rel="noopener noreferrer"' in facts
    assert ">Jira<" in facts

    # The marker's name is already the row's label; repeating it on the badge
    # says `jira` twice.
    assert ">PROJ-123<" in facts
    assert "jira(PROJ-123)" not in facts


def test_an_owner_is_pulled_out_of_the_row_of_tags(patterns):
    facts = _facts(_record(_marker("slow"), _marker(OWNER_MARKER, "payments-team",
                                                    kind="owner")))

    assert ">1 owner<" in facts
    assert "step-badge--owner" in facts
    assert ">payments-team<" in facts

    # And is not counted among the markers it was lifted out of.
    assert ">1 marker<" in facts


def test_a_marker_with_no_pattern_is_the_badge_it_has_always_been(patterns):
    facts = _facts(_record(_marker("slow")))

    assert "<a " not in facts
    assert ">slow<" in facts
    assert ">1 marker<" in facts


def test_a_suite_that_configured_nothing_gets_the_report_it_had_before(isolate_patterns):
    ConfigVars._link_patterns = {}

    facts = _facts(_record(_marker("jira", "PROJ-123"), _marker("slow")))

    assert "<a " not in facts
    assert ">2 markers<" in facts
    assert ">jira(PROJ-123)<" in facts


# ---------------------------------------------------------------- the xml ---

def _cases(records, **kw):
    root = junit_document(records, **kw)
    return root.find("testsuite").findall("testcase")


def test_an_id_reaches_the_xml_as_a_property_on_the_testcase():
    """The tools that ingest issue keys never open an html report."""
    case = _cases([_record(_marker("jira", "PROJ-123"),
                           _marker(OWNER_MARKER, "payments-team", kind="owner"))],
                  trace_markers=trace_markers({"jira": "https://acme/{}"}))[0]

    properties = case.find("properties")
    pairs = [(p.get("name"), p.get("value")) for p in properties.findall("property")]

    assert ("jira", "PROJ-123") in pairs
    assert ("owner", "payments-team") in pairs


def test_the_properties_come_before_the_outcome():
    """Where pytest's own writer puts them, and so where consumers look."""
    case = _cases([_record(_marker("jira", "PROJ-1"), status="FAIL", message="boom")],
                  trace_markers=["jira"])[0]

    assert [child.tag for child in case][:2] == ["properties", "failure"]


def test_a_marker_that_was_not_named_as_traceability_stays_out_of_the_xml():
    case = _cases([_record(_marker("slow"), _marker("jira", "PROJ-1"))],
                  trace_markers=["jira"])[0]

    pairs = [(p.get("name"), p.get("value")) for p in case.find("properties").findall("property")]

    assert pairs == [("jira", "PROJ-1")]


def test_a_marker_with_empty_brackets_writes_no_property():
    """An empty property is a row every consumer shows and none can use."""
    case = _cases([_record(_marker("jira"))], trace_markers=["jira"])[0]

    assert case.find("properties") is None


def test_a_run_that_named_no_trace_markers_writes_the_document_it_always_did():
    case = _cases([_record(_marker("jira", "PROJ-1"))])[0]

    assert case.find("properties") is None


def test_the_marker_names_are_the_built_in_ones_plus_whatever_was_configured():
    """Owner and severity need no configuration; everything else is invented."""
    assert trace_markers({"jira": "u", "testcase": "u"}) == ["owner", "severity", "jira", "testcase"]
    assert trace_markers({}) == ["owner", "severity"]


# ------------------------------------------------------------- the rail ---

def test_a_tests_owners_reach_the_rail_as_one_attribute():
    """The filter reads them off the button; one attribute has to hold both."""
    record = _record(_marker(OWNER_MARKER, "platform", kind="owner"),
                     _marker(OWNER_MARKER, "payments", kind="owner"),
                     _marker("slow"))

    assert record_owners(record) == ["platform", "payments"]
    assert OWNER_SEPARATOR.join(record_owners(record)) == "platform|payments"


def test_an_owner_written_twice_is_one_owner():
    """`pytestmark` on the module and the same marker on the test is two
    records of one fact, and two identical pills would be a filter that splits
    a team in half."""
    record = _record(_marker(OWNER_MARKER, "platform", kind="owner"),
                     _marker(OWNER_MARKER, "platform", kind="owner"))

    assert record_owners(record) == ["platform"]


def test_an_owner_marker_with_empty_brackets_owns_nothing():
    assert record_owners(_record(_marker(OWNER_MARKER, kind="owner"))) == []


def test_a_test_with_no_owner_marker_has_no_owners():
    assert record_owners(_record(_marker("slow"))) == []
    assert record_owners({}) == []


# ------------------------------------------------------------ the severity ---

def _severity(*levels, **kw):
    """A record carrying severity markers, nearest first, as markers() yields them."""
    scope = kw.pop("scope", "function")
    scopes = kw.pop("scopes", None) or [scope] * len(levels)

    return _record(*[_marker(SEVERITY_MARKER, level, kind="severity", scope=where)
                     for level, where in zip(levels, scopes)], **kw)


def test_a_severity_is_its_own_kind_of_marker():
    class Mark:
        name = SEVERITY_MARKER
        args = ("critical",)
        kwargs = {}

    class Function:
        pass

    class Item:
        def iter_markers_with_node(self):
            return [(Function(), Mark())]

    assert describe(Item())["markers"][0]["kind"] == "severity"


def test_a_severity_with_empty_brackets_is_an_ordinary_marker():
    """It is not a sixth level and it is not `normal` - it is unfinished."""
    class Mark:
        name = SEVERITY_MARKER
        args = ()
        kwargs = {}

    class Function:
        pass

    class Item:
        def iter_markers_with_node(self):
            return [(Function(), Mark())]

    assert describe(Item())["markers"][0]["kind"] == "user"


def test_the_ladder_is_ranked_worst_first():
    assert severity_rank("blocker") < severity_rank("critical") < severity_rank("normal")
    assert severity_rank("normal") < severity_rank("minor") < severity_rank("trivial")


def test_a_word_nobody_recognises_ranks_after_every_level():
    """A typo is not a sixth level, and must not outrank blocker."""
    assert severity_rank("high") > severity_rank("trivial")


def test_a_level_is_the_same_level_however_it_was_capitalised():
    """Two spellings of one word must not split a suite's counts in half."""
    assert severity_value(_marker(SEVERITY_MARKER, "  Critical ")) == "critical"


def test_the_nearest_severity_is_the_one_that_applies():
    """A class rated above its module is somebody correcting the outer word."""
    record = _severity("critical", "normal", scopes=["class", "module"])

    assert record_severity(record) == "critical"


def test_two_at_one_scope_are_read_as_the_worse_of_them():
    """Nothing is nearer, and reading a blocker down to minor hides work."""
    record = _severity("minor", "blocker")

    assert record_severity(record) == "blocker"


def test_a_test_nobody_rated_is_unrated_rather_than_normal():
    """Allure defaults; this does not - six hundred unrated tests are not normal."""
    assert record_severity(_record(_marker("slow"))) == ""


def test_the_severity_reaches_the_rail_as_its_own_attribute():
    """The filter reads it off the button, already resolved to one word."""
    generate_steps_view(OrderedDict([("tests/test_pay.py", [
        _severity("critical", "normal", scopes=["function", "module"]),
    ])]))

    assert 'data-severity="critical"' in ConfigVars._step_tree
    assert 'data-severity="normal"' not in ConfigVars._step_tree


def test_the_overridden_severity_is_shown_and_struck_through():
    """The tab promises every marker, and says which one decided the colour."""
    badges = _severity_badges(
        _severity("critical", "normal", scopes=["function", "module"])["meta"]["markers"],
        "critical")

    assert "step-badge--severity-critical" in badges
    assert "step-badge--severity-past" in badges
    assert "overridden by critical" in badges


def test_the_severity_row_stays_out_of_the_row_of_tags(patterns):
    """It answers `how bad`, which is not what a row of `slow` and `smoke` says."""
    record = _severity("blocker")
    record["meta"]["markers"].append(_marker("slow"))

    _linked, plain = _traced([marker for marker in record["meta"]["markers"]
                              if marker.get("kind") not in ("owner", "severity")])

    assert [marker["name"] for marker in plain] == ["slow"]
    assert "Severity" in _facts(record)


def test_the_severity_reaches_the_xml_once_and_already_resolved():
    """A testcase carrying both `normal` and `critical` is one nobody can rank."""
    case = _cases([_severity("critical", "normal", scopes=["function", "module"])],
                  trace_markers=trace_markers({}))[0]

    pairs = [(p.get("name"), p.get("value")) for p in case.find("properties").findall("property")]

    assert pairs == [("severity", "critical")]


def test_a_run_that_rated_nothing_writes_no_severity_property():
    case = _cases([_record(_marker("slow"))], trace_markers=trace_markers({}))[0]

    assert case.find("properties") is None
