"""Cover what a test says about itself: its markers, parameters and fixtures.

Driven through a real run rather than through hand-built objects. Everything
interesting here is a property of how pytest *collects* a test - a marker on
the module, one on the class, one added while the test ran - and a stub item
would only ever prove that the stub was built the way the assertion expected.
"""

import json
import os
import subprocess
import sys
import textwrap


CONFTEST = '''
    import json, sys
    sys.path.insert(0, %(root)r)
    import pytest
    from pytest_html_reporter.markers import describe

    SEEN = []

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(item, nextitem):
        yield
        SEEN.append(dict(nodeid=item.nodeid, **describe(item)))

    def pytest_sessionfinish(session):
        json.dump(SEEN, open("described.json", "w"))
'''

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _describe(tmp_path, body):
    """Run a generated suite and hand back what describe() saw, by nodeid."""
    (tmp_path / "conftest.py").write_text(textwrap.dedent(CONFTEST % {"root": ROOT}))
    (tmp_path / "test_described.py").write_text(textwrap.dedent(body))

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q"],
        cwd=str(tmp_path), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    described = tmp_path / "described.json"
    assert described.is_file(), result.stdout

    return {entry["nodeid"]: entry for entry in json.loads(described.read_text())}


def _texts(entry):
    return [marker["text"] for marker in entry["markers"]]


def test_a_module_level_pytestmark_is_not_missed(tmp_path):
    # item.own_markers - the obvious source, and the one the roadmap suggested
    # - holds only what was written on the test itself, so a module-level
    # pytestmark vanished from it entirely.
    seen = _describe(tmp_path, '''
        import pytest
        pytestmark = pytest.mark.suite("checkout")

        def test_one():
            assert True
    ''')

    assert _texts(seen["test_described.py::test_one"]) == ["suite(checkout)"]


def test_a_marker_on_the_class_is_not_missed(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.mark.slow
        class TestThing:
            def test_one(self):
                assert True
    ''')

    assert _texts(seen["test_described.py::TestThing::test_one"]) == ["slow"]


def test_a_marker_added_while_the_test_ran_is_not_missed(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest

        def test_one(request):
            request.node.add_marker(pytest.mark.quarantined(by="triage"))
    ''')

    assert _texts(seen["test_described.py::test_one"]) == ["quarantined(by=triage)"]


def test_a_marker_says_where_it_was_written(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest
        pytestmark = pytest.mark.from_module

        @pytest.mark.from_class
        class TestThing:
            @pytest.mark.from_method
            def test_one(self):
                assert True
    ''')

    scopes = {marker["name"]: marker["scope"]
              for marker in seen["test_described.py::TestThing::test_one"]["markers"]}

    assert scopes == {"from_method": "function", "from_class": "class", "from_module": "module"}


def test_the_same_marker_written_twice_is_said_once(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest
        pytestmark = pytest.mark.shared

        @pytest.mark.shared
        class TestThing:
            @pytest.mark.shared
            def test_one(self):
                assert True
    ''')

    assert _texts(seen["test_described.py::TestThing::test_one"]) == ["shared"]


def test_the_same_marker_carrying_different_values_is_said_each_time(tmp_path):
    # tier('unit') and tier('slow') are two different things to say, however
    # alike they look.
    seen = _describe(tmp_path, '''
        import pytest
        pytestmark = pytest.mark.tier("module")

        @pytest.mark.tier("method")
        def test_one():
            assert True
    ''')

    assert _texts(seen["test_described.py::test_one"]) == ["tier(method)", "tier(module)"]


def test_pytests_own_markers_are_told_apart_from_everyone_elses(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.mark.skipif(False, reason="never")
        @pytest.mark.mine
        def test_one():
            assert True
    ''')

    kinds = {marker["name"]: marker["kind"] for marker in seen["test_described.py::test_one"]["markers"]}

    assert kinds == {"skipif": "builtin", "mine": "user"}


def test_a_parametrize_marker_shows_its_names_not_every_row(tmp_path):
    # The marker carries every row the test will ever run with; this case is
    # one of them, and its own row is shown as its parameters.
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.mark.parametrize("n", list(range(50)))
        def test_one(n):
            assert True
    ''')

    assert _texts(seen["test_described.py::test_one[0]"]) == ["parametrize(n)"]


def test_a_skipif_condition_is_not_shown_as_the_bool_it_became(tmp_path):
    # pytest evaluates the condition at import, so what arrives is False - not
    # sys.platform == 'win32'. The reason is the half that still means something.
    seen = _describe(tmp_path, '''
        import sys, pytest

        @pytest.mark.skipif(sys.platform == "nonexistent", reason="only on nonexistent")
        def test_one():
            assert True
    ''')

    assert _texts(seen["test_described.py::test_one"]) == ["skipif(reason=only on nonexistent)"]


def test_an_exception_class_in_a_marker_is_named_not_repred(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.mark.xfail(raises=ValueError, strict=True)
        def test_one():
            raise ValueError("expected")
    ''')

    assert _texts(seen["test_described.py::test_one"]) == ["xfail(raises=ValueError, strict=True)"]


def test_the_parameters_are_this_cases_own_row(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.mark.parametrize("n,label", [(1, "one"), (2, "two")])
        def test_one(n, label):
            assert True
    ''')

    assert seen["test_described.py::test_one[2-two]"]["params"] == [["label", "two"], ["n", "2"]]


def test_the_fixtures_are_the_ones_the_test_asked_for(tmp_path):
    # item.fixturenames is the whole transitive closure - every autouse fixture
    # above the test, plus the fixtures its fixtures depend on. Asking for
    # tmp_path dragged in tmp_path_factory, and a test naming two fixtures read
    # as a test naming nine.
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.fixture
        def widget(): return 1

        @pytest.fixture(autouse=True)
        def always(): return 2

        def test_one(widget, tmp_path):
            assert True
    ''')

    assert seen["test_described.py::test_one"]["fixtures"] == ["widget", "tmp_path"]


def test_a_usefixtures_marker_counts_as_asking(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.fixture
        def widget(): return 1

        @pytest.mark.usefixtures("widget")
        def test_one():
            assert True
    ''')

    assert seen["test_described.py::test_one"]["fixtures"] == ["widget"]


def test_a_parametrized_argument_is_a_parameter_rather_than_a_fixture(tmp_path):
    seen = _describe(tmp_path, '''
        import pytest

        @pytest.mark.parametrize("n", [1])
        def test_one(n):
            assert True
    ''')

    entry = seen["test_described.py::test_one[1]"]

    assert entry["params"] == [["n", "1"]]
    assert entry["fixtures"] == []


def test_the_docstring_is_kept_as_one_paragraph(tmp_path):
    seen = _describe(tmp_path, '''
        def test_one():
            """Buys a thing
            and checks the cart."""
            assert True
    ''')

    assert seen["test_described.py::test_one"]["doc"] == "Buys a thing and checks the cart."


def test_a_class_docstring_is_not_repeated_under_every_method(tmp_path):
    seen = _describe(tmp_path, '''
        class TestThing:
            """Describes the class, not any test in it."""

            def test_one(self):
                assert True
    ''')

    assert seen["test_described.py::TestThing::test_one"]["doc"] == ""
