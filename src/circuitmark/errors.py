"""Errors and warnings carry a file name and a line number so editors can jump to them."""
from __future__ import annotations


class CircuitError(Exception):
    def __init__(self, message: str, line: int = 0, filename: str = "<string>", hint: str = ""):
        super().__init__(message)
        self.message = message
        self.line = line
        self.filename = filename
        self.hint = hint

    def __str__(self) -> str:
        where = "%s:%d: " % (self.filename, self.line) if self.line else "%s: " % self.filename
        s = where + "error: " + self.message
        if self.hint:
            s += "\n  hint: " + self.hint
        return s


class Warning:  # noqa: A001 - a plain record, not the builtins.Warning class
    __slots__ = ("message", "line", "filename")

    def __init__(self, message: str, line: int = 0, filename: str = "<string>"):
        self.message = message
        self.line = line
        self.filename = filename

    def __str__(self) -> str:
        where = "%s:%d: " % (self.filename, self.line) if self.line else "%s: " % self.filename
        return where + "warning: " + self.message

    def __repr__(self) -> str:
        return "Warning(%r, line=%d)" % (self.message, self.line)
