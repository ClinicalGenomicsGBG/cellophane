# ruff: noqa: E402

import pytest

pytest.register_assert_rewrite("cellophane.testing.legacy")

from .hooks import (
    housekeeping,
    pytest_assertrepr_compare,
    pytest_configure,
    pytest_runtest_makereport,
)
from .invocation import BaseTest, Invocation, deferred_invocation, invocation
from .util import PathDict, literal, regex

__all__ = [
    "Invocation",
    "deferred_invocation",
    "invocation",
    "PathDict",
    "regex",
    "literal",
    "BaseTest",
    "parametrize_from_yaml",
    "run_definition",
    "housekeeping",
    "pytest_assertrepr_compare",
    "pytest_configure",
    "pytest_runtest_makereport",
]
