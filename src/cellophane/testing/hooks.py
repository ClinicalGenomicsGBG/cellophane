import logging
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import pytest


@pytest.fixture(scope="function", autouse=True)
def housekeeping() -> Iterable[None]:
    # Add the tests/site to the Python path to override config.py
    sys.path.insert(0, str(Path(__file__).parent / "site"))
    reset_modules = sys.modules.copy()
    log_handlers = logging.root.handlers.copy()

    yield

    # Reset the modules to their original state
    for module in set(sys.modules) - set(reset_modules):
        del sys.modules[module]

    # Remove the tests/site from the Python path
    sys.path.remove(str(Path(__file__).parent / "site"))

    # Reset the logging handlers
    logging.root.handlers = log_handlers
    # Clear the loggers
    logging.root.manager.loggerDict.clear()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Iterable[pytest.TestReport]:
    """Hook to add commandline, logs and output to test reports."""
    del call  # Unused

    # NOTE: This syntax is a bit esoteric, and mypy doesn't like it
    # but this is paraphrased from the pytest docs
    report: pytest.TestReport = yield  # type: ignore[misc, assignment]
    if invocation_ := item.funcargs.get("invocation"):
        report.sections.append(("Args", " ".join(invocation_.args)))
        report.sections.append(("stdout/stderr", invocation_.output))
        report.sections.append(("Exception", repr(invocation_.exception)))
    return report


def _is_regex(obj: Any) -> bool:
    # NOTE: We need to use this convoluted check because the class differs
    # if it is imporeted using the deprecated location in `cellphane.src`
    # This behavior should be removed when support for the deprecated
    # location is dropped
    cls = obj if isinstance(obj, type) else obj.__class__
    return (
        cls.__module__ in ("cellophane.testing.util", "cellophane.src.testing.util")
        and cls.__name__ == "regex"
    )


def _is_literal(obj: Any) -> bool:
    # NOTE: We need to use this convoluted check because the class differs
    # if it is imporeted using the deprecated location in `cellphane.src`
    # This behavior should be removed when support for the deprecated
    # location is dropped
    cls = obj if isinstance(obj, type) else obj.__class__
    return (
        cls.__module__ in ("cellophane.testing.util", "cellophane.src.testing.util")
        and cls.__name__ == "literal"
    )


def _is_regex_or_literal(obj: Any) -> bool:
    # NOTE: We need to use this convoluted check because the class differs
    # if it is imporeted using the deprecated location in `cellphane.src`
    # This behavior should be removed when support for the deprecated
    # location is dropped
    return _is_regex(obj) or _is_literal(obj)


@pytest.hookimpl()
def pytest_assertrepr_compare(op: str, left: Any, right: Any) -> list[str] | None:
    if not any(_is_regex_or_literal(obj) for obj in (left, right)):
        # No regexes in the comparison
        return None

    _pattern, _data = (left, right) if _is_regex_or_literal(left) else (right, left)
    _MATCH = (
        ("\033[032m" if op == "==" else "\033[031m")
        + "  [MATCH]    '{pattern}'"
        + "\033[0m"
    )
    _NO_MATCH = (
        ("\033[031m" if op == "==" else "\033[032m")
        + "  [NO MATCH] '{pattern}'"
        + "\033[0m"
    )

    _repr = [f"matching '{type(_data).__name__} with regex:"]
    if isinstance(_data, str):
        _content = _data
    elif isinstance(_data, Path):
        _content = _data.read_text()
    elif isinstance(_data, Iterable):
        _content = "\n".join(_data)
    else:
        _content = repr(_data)

    if "\n" not in _content:
        _repr.append(f"Data: {_content}")
    else:
        _rows = _content.strip().splitlines()
        _repr.append("Data:")
        _repr.extend(f"  {row}" for row in _rows)

    _repr.append("Patterns:")
    for p in _pattern.patterns:
        if _is_literal(_pattern):
            pattern_representation = re.sub(r"\\", "", p.pattern)
        else:
            pattern_representation = p.pattern

        if p.search(_content):
            _repr.append(_MATCH.format(pattern=pattern_representation))
        else:
            _repr.append(_NO_MATCH.format(pattern=pattern_representation))

    return _repr


@pytest.hookimpl()
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "override(structure,args,mocks,subprocess_mocks): "
        "Override the default values for the test class.",
    )
