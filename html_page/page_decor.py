import os
import re
import sys


def html_page(cls):
    def __init__(self, *args, **kwargs):
        if args:
            raise ValueError("HTML code behind class receives keyword only parameters. Positional are not allowed.")

        self.__content = None
        self.__inline_attributes = list()
        self.__inline_code_snippets = list()

        for inline_attribute in self.inline_attributes:
            if inline_attribute in dict(kwargs).keys():
                setattr(self, inline_attribute, kwargs[inline_attribute])
            else:
                setattr(self, inline_attribute, "")

    def __str__(self):
        res = self.content
        for inln in self.inline_attributes:
            res = res.replace(f"%({inln})", getattr(self, inln))

        for cd_snpt in self.inline_code_snippets:
            res = res.replace(f"$({cd_snpt})s", eval(cd_snpt))

        return res

    @property
    def content(self):
        if not self.__content:
            fname_list = os.path.abspath(__file__).split(os.path.sep)
            fname = os.path.join(*fname_list[:fname_list.index("pytest-html-reporter") + 1]) \
                if sys.platform.startswith("win") or sys.platform == "cygwin" \
                else os.path.join(os.path.sep, *fname_list[:fname_list.index("pytest-html-reporter") + 1])

            with open(os.path.join(fname, "html", f"{cls.__doc__.strip()}.html")) as html:
                self.__content = html.read()

        return self.__content

    @property
    def inline_attributes(self):
        if not self.__inline_attributes:
            self.__inline_attributes = re.findall("%\((.+?)\)", self.content)

        return self.__inline_attributes

    @property
    def inline_code_snippets(self):
        if not self.__inline_code_snippets:
            self.__inline_code_snippets = re.findall("\$\((.+?)\)s", self.content)

        return self.__inline_code_snippets

    def format(self, **params):
        return self.template.format(**params)

    def replace(self, one, another):
        return str(self).replace(one, another)

    cls.__init__ = __init__
    cls.__str__ = __str__
    cls.content = content
    cls.inline_attributes = inline_attributes
    cls.inline_code_snippets = inline_code_snippets
    cls.format = format
    cls.replace = replace

    return cls