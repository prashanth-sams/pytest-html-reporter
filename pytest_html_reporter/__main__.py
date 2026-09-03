"""``python -m pytest_html_reporter`` - an exact alias for the console script.

Worth the five lines because the console script is only on PATH once the
package has been installed with its entry points, and the everyday merge runs
in a CI container that pip-installed a wheel, a tox environment, or a checkout
somebody is trying the feature out in. ``python -m`` works in all three, so a
pipeline never has to find out which of them it is in.

``main`` returns the exit code rather than raising, so the exit happens here -
in one place - and every caller of ``cli.main`` (this module, the console
script's own generated wrapper, and the tests) agrees about who owns
``SystemExit``.
"""

import sys

from pytest_html_reporter.cli import main


if __name__ == "__main__":
    sys.exit(main())
