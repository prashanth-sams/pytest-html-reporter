"""A stand-in for pytest's Config, for a render that has no pytest run behind it.

The merge command builds a report out of shard files. There is no session, no
collection and no plugin manager, but the render pipeline it drives was written
against a real ``Config`` and reaches for one in a dozen places. Rather than
thread an "am I a merge?" flag through util.py, coverage_report.py and
report_opener.py, the merge hands them an object that answers the same
questions from a dict.

Everything the render path actually reaches, and where:

``getoption(name, default=None)``
    util.report_path (``path``), util.environment_name (``environment``),
    util.build_info (``build_info``), util.report_links (``report_link``),
    util.archive_count / archive_days / archive_since, util's five
    report_* mode helpers, util._capture_is_off (``capture``),
    util._log_level_name (``log_level``), report_opener.open_mode
    (``report_open``), coverage_report's coverage_mode / coverage_file /
    coverage_limit and coverage_target (``cov_fail_under``). Every one of them
    passes a default, so an option the merge never heard of answers None and
    the helper falls back the way it does under a pytest that never registered
    it.

``getini(name)``
    Raises ValueError, always. That is not laziness - it is the contract
    ``util._ini`` is written against (it catches AttributeError, ValueError and
    KeyError and returns None), and it is the same answer the test suite's own
    _FakeConfig gives. A merge has no ini file; every option resolves from the
    command line or from its default.

``option``
    A namespace view of the same dict, because plugin.py assigns
    ``config.option.path`` and anything reading an option that way has to see
    what getoption sees.

``rootpath``
    coverage_report.collect_coverage and util.generate_environment_info read
    it for a root to relativise against.

``invocation_params.args``
    util._invocation_args, for the Arguments row of the Environment panel.

``pluginmanager.hasplugin(name)``
    False, always, and load-bearing twice. HTMLReporter.__init__ asks whether
    pytest-rerunfailures is installed and keeps the answer in ``rerun_plugin``;
    a merge must never fold records on the strength of what happens to be
    installed on the merging machine. coverage_report.live_coverage asks for
    ``_cov``; there is no pytest-cov run to read here, and the coverage the
    merge shows comes from the shards or from --report-coverage-file.

``pluginmanager.getplugin(name)`` and ``list_plugin_distinfo()``
    None and []. list_plugin_distinfo is the one genuinely unguarded
    plugin-manager call in the tree (util._plugin_versions), reached from
    generate_environment_info - which the merge replaces, but a shim that
    crashes the moment somebody calls the function it replaced is not a shim.
"""

import os
import sys


class _StubPluginManager(object):
    """No plugins, and every question about one answered rather than raised."""

    def hasplugin(self, name):
        return False

    def getplugin(self, name):
        return None

    def get_plugin(self, name):
        return None

    def list_plugin_distinfo(self):
        return []


class _OptionNamespace(object):
    """Attribute access over the very dict getoption reads.

    Not a copy: plugin.py resolves --html-report once and writes the expanded
    value back onto ``config.option.path`` so that everything reading it later
    agrees. A namespace holding its own copy would let the two views drift, and
    the drift would show up as a report written to one path and screenshots
    written to another.
    """

    def __init__(self, options):
        object.__setattr__(self, '_options', options)

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, '_options')[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        object.__getattribute__(self, '_options')[name] = value


class _InvocationParams(object):
    """What util._invocation_args reads to fill the Arguments row."""

    def __init__(self, args):
        self.args = tuple(args)


class MergeConfig(object):
    """The config a merged render is driven with.

    Constructed from a plain dict of option values so the merge CLI can map its
    own flags onto the names the render pipeline asks for - ``--coverage-target``
    becomes ``cov_fail_under``, ``--html-report`` becomes ``path`` - without any
    of those helpers learning that a merge exists.
    """

    def __init__(self, options=None, rootpath=None, args=None):
        self._options = dict(options or {})
        self.option = _OptionNamespace(self._options)
        self.pluginmanager = _StubPluginManager()

        # A str rather than a pathlib.Path: every reader in the tree does
        # str(config.rootpath) or feeds it to os.path, and nothing calls a Path
        # method on it.
        self.rootpath = str(rootpath or os.getcwd())
        self.rootdir = self.rootpath

        self.invocation_params = _InvocationParams(
            args if args is not None else sys.argv[1:])

    def getoption(self, name, default=None):
        value = self._options.get(name, default)

        return default if value is None else value

    def getini(self, name):
        """Always a ValueError - see the module docstring.

        util._ini catches it and returns None, which is the answer that makes
        every option helper fall through to its own default. Returning '' here
        instead would work for the string options and quietly break the ones
        that treat '' as a deliberate answer, ``archive_count`` first among
        them ('' keeps every build, '0' keeps none).
        """
        raise ValueError(name)
