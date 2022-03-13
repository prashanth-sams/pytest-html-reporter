import os
import sys


def html_page(cls):
    def __str__(self):
        if not hasattr(self, "template"):
            fname_list = os.path.abspath(__file__).split(os.path.sep)
            fname = os.path.join(*fname_list[:fname_list.index("pytest-html-reporter") + 1]) \
                if sys.platform.startswith("win") or sys.platform == "cygwin" \
                else os.path.join(os.path.sep, *fname_list[:fname_list.index("pytest-html-reporter") + 1])

            with open(os.path.join(fname, "html", f"{cls.__doc__.strip()}.html")) as html:
                self.template = html.read()

        return self.template

    def format(self, **params):
        return self.template.format(**params)

    def replace(self, one, another):
        return str(self).replace(one, another)

    cls.__str__ = __str__
    cls.format = format
    cls.replace = replace

    return cls