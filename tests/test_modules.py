"""Test modules."""

# pylint: disable=protected-access

import logging
import subprocess as sp
from collections import UserList
from copy import copy
from graphlib import CycleError
from logging.handlers import QueueListener
from multiprocessing import Queue
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock

from cloudpickle import dumps, loads
from psutil import Process, TimeoutExpired
from pytest import LogCaptureFixture, mark, param, raises
from pytest_mock import MockerFixture

from cellophane.src import data, modules
from cellophane.src.data import Sample, Samples
from cellophane.src.executors import SubprocesExecutor
from cellophane.src.modules import Hook, Runner

LIB = Path(__file__).parent / "lib"


class Test__cleanup:
    """Test cleanup function."""

    @staticmethod
    def dummy_procs(n: int = 1) -> tuple[list[sp.Popen], list[int]]:
        """Create dummy processes."""
        _procs = [sp.Popen(["sleep", "1"]) for _ in range(n)]
        _pids = [p.pid for p in _procs]

        return _procs, _pids

    @mark.parametrize(
        "timeout,log_line",
        [
            param(False, "Waiting for sleep ({pid})", id="no_timeout"),
            param(True, "Killing unresponsive process sleep ({pid})", id="timeout"),
        ],
    )
    def test__cleanup(
        self,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
        log_line: str,
        timeout: bool,
    ) -> None:
        """Test cleanup function."""
        procs, pids = self.dummy_procs(3)

        mocker.patch(
            "cellophane.src.modules.psutil.Process.children",
            return_value=[Process(pid=p) for p in pids],
        )

        if timeout:
            mocker.patch(
                "cellophane.src.modules.psutil.Process.terminate",
                side_effect=TimeoutExpired(10),
            )

        assert all(p.poll() is None for p in procs)

        with raises(SystemExit), caplog.at_level("DEBUG"):
            logger = logging.LoggerAdapter(logging.getLogger(), {"label": "DUMMY"})
            modules._cleanup(logger)()

        assert all(p.poll() is not None for p in procs)
        for p in pids:
            assert log_line.format(pid=p) in caplog.messages


class Test__instance_or_subclass:
    """Test _is_instance_or_subclass function."""

    class _SampleSub(data.Sample):
        pass

    class _SamplesSub(data.Samples):
        pass

    hook = modules.pre_hook()(lambda: ...)
    runner = modules.runner()(lambda: ...)

    @staticmethod
    @mark.parametrize(
        "obj,cls,expected",
        [
            (_SampleSub, data.Sample, True),
            (_SamplesSub, data.Samples, True),
            (_SamplesSub, UserList, True),
            (_SamplesSub, list, False),
            (hook, modules.Hook, True),
            (hook, Callable, True),
            (hook, str, False),
            (runner, modules.Runner, True),
            (runner, Callable, True),
            (runner, str, False),
        ],
    )
    def test_instance_or_subclass(
        obj: type[_SampleSub] | type[_SamplesSub] | Any | Runner,
        cls: (
            type[Sample]
            | type[dict]
            | type[Samples]
            | type[UserList]
            | type[list]
            | type[Hook]
            | type[Callable[..., Any]]
            | type[str]
            | type[Runner]
        ),
        expected: bool,
    ) -> None:
        """Test _is_instance_or_subclass function."""
        assert modules._is_instance_or_subclass(obj, cls) == expected


class Test_Runner:
    """Test Runner class."""

    samples: data.Samples = data.Samples(
        [
            data.Sample(id="a"),
            data.Sample(id="b"),
            data.Sample(id="c"),
        ]
    )

    @staticmethod
    @mark.parametrize(
        "kwargs",
        [
            param(
                {},
                id="no_args",
            ),
            param(
                {"label": "test"},
                id="label",
            ),
            param(
                {"split_by": "test"},
                id="split_by",
            ),
        ],
    )
    def test_decorator(kwargs: dict[str, Any]) -> None:
        """Test Runner decorator."""

        @modules.runner(**kwargs)
        def _dummy() -> None:
            pass

        assert _dummy.__name__ == "_dummy"
        assert _dummy.label == kwargs.get("label", "_dummy")
        assert _dummy.split_by == kwargs.get("split_by")

    @mark.parametrize(
        "runner_mock,runner_kwargs,expected_fail,log_lines",
        [
            param(
                MagicMock(return_value=None),
                {},
                [False] * 3,
                [["Runner did not return any samples"]],
                id="None",
            ),
            param(
                MagicMock(side_effect=RuntimeError),
                {},
                ["Sample was not processed"] * 3,
                [
                    [
                        "3 samples failed",
                        "Sample a failed - Sample was not processed",
                        "Sample b failed - Sample was not processed",
                        "Sample c failed - Sample was not processed",
                    ]
                ],
                id="Exception",
            ),
            param(
                lambda samples, **_: samples[0].fail("DUMMY") or samples,
                {},
                ["DUMMY", False, False],
                [
                    ["Sample a failed - DUMMY"],
                    ["Sample b processed successfully"],
                    ["Sample c processed successfully"],
                ],
                id="failed_sample",
            ),
            param(
                MagicMock(return_value="INVALID"),
                {},
                [False] * 3,
                [["Unexpected return type <class 'str'>"]],
                id="invalid_return",
            ),
        ],
    )
    def test_call(
        self,
        caplog: LogCaptureFixture,
        tmp_path: Path,
        mocker: MockerFixture,
        runner_mock: data.Samples,
        runner_kwargs: dict[str, Any],
        expected_fail: list[int],
        log_lines: list[list[str]],
    ) -> None:
        """Test Runner call."""
        setattr(runner_mock, "__name__", "runner_mock")
        setattr(runner_mock, "__qualname__", "runner_mock")
        _runner = modules.runner(**runner_kwargs)(runner_mock)
        _config_mock = MagicMock()

        mocker.patch(
            "cellophane.src.modules._cleanup",
            return_value=_config_mock,
        )

        with caplog.at_level("DEBUG"):
            _log_queue: Queue = Queue()
            _listener = QueueListener(_log_queue, *logging.getLogger().handlers)
            _listener.start()
            _ret = _runner(
                _log_queue,
                config=MagicMock(timestamp="DUMMY", log_level=None),
                root=tmp_path / "root",
                samples_pickle=dumps(self.samples),
                executor_cls=SubprocesExecutor,
            )
            _listener.stop()

            for line in log_lines:
                assert "\n".join(line) in "\n".join(caplog.messages)
        assert [s.failed for s in loads(_ret)] == expected_fail


class Test_Hook:
    """Test Hook class."""

    samples: data.Samples = data.Samples(
        [
            data.Sample(id="a"),
            data.Sample(id="b"),
            data.Sample(id="c"),
        ]
    )

    @staticmethod
    @mark.parametrize(
        "when",
        [
            param("pre", id="pre"),
            param("post", id="post"),
        ],
    )
    @mark.parametrize(
        "kwargs,expected_before,expected_after",
        [
            param({}, ["after_all"], ["before_all"], id="base"),
            param({"before": "all"}, ["before_all"], [], id="before_all"),
            param({"after": "all"}, [], ["after_all"], id="after_all"),
            param(
                {"before": "all", "after": ["AFTER_A", "AFTER_B"]},
                ["before_all"],
                ["AFTER_A", "AFTER_B"],
                id="before_all_after_some",
            ),
            param(
                {"after": "all", "before": ["BEFORE_A", "BEFORE_B"]},
                ["BEFORE_A", "BEFORE_B"],
                ["after_all"],
                id="before_some_after_all",
            ),
        ],
    )
    def test_decorator(
        when: str,
        kwargs: dict[str, Any],
        expected_before: list[str],
        expected_after: list[str],
    ) -> None:
        """Test Hook decorator."""
        _kwargs = {
            k: v for k, v in kwargs.items() if when == "post" or k != "condition"
        }

        _decorator = getattr(modules, f"{when}_hook")
        _hook = _decorator(**_kwargs)(lambda: ...)
        assert _hook.when == when
        assert _hook.condition == _kwargs.get("condition", "always")

        assert _hook.before == expected_before
        assert _hook.after == expected_after

    @staticmethod
    @mark.parametrize(
        "when,kwargs,exception",
        [
            param(
                "pre",
                {"before": "all", "after": "all"},
                ValueError,
                id="before_after_all",
            ),
            param(
                "post",
                {"condition": "invalid"},
                ValueError,
                id="invalid_condition",
            ),
        ],
    )
    def test_hook_exceptions(
        when: str,
        kwargs: dict[str, Any],
        exception: type[Exception],
    ) -> None:
        """Test Hook decorator exceptions."""
        _decorator = getattr(modules, f"{when}_hook")
        with raises(exception):

            @_decorator(**kwargs)
            def _() -> None: ...

    @staticmethod
    @mark.parametrize(
        "when,kwargs,input_value,return_value,expected,logs",
        [
            param(
                "pre",
                {},
                MagicMock(spec=data.Samples, value="INPUT"),
                MagicMock(spec=data.Samples, value="RETURNED"),
                "RETURNED",
                [],
                id="pre",
            ),
            param(
                "post",
                {"condition": "complete"},
                MagicMock(spec=data.Samples, value="INPUT"),
                MagicMock(spec=data.Samples, value="RETURNED"),
                "RETURNED",
                [],
                id="post_complete",
            ),
            param(
                "post",
                {"condition": "complete"},
                MagicMock(spec=data.Samples, value="INPUT"),
                str,
                "INPUT",
                ["Unexpected return type"],
                id="invalid_return",
            ),
            param(
                "post",
                {"condition": "complete"},
                MagicMock(spec=data.Samples, value="INPUT"),
                None,
                "INPUT",
                ["Hook did not return any samples"],
                id="no_return",
            ),
        ],
    )
    def test_call(
        tmp_path: Path,
        when: str,
        kwargs: dict[str, Any],
        input_value: type[Any],
        return_value: type[Any],
        expected: Any,
        logs: list[str],
        caplog: LogCaptureFixture,
    ) -> None:
        """Test Hook call."""
        _decorator = getattr(modules, f"{when}_hook")
        _hook = _decorator(**kwargs)(
            lambda **_: return_value,
        )

        with caplog.at_level("DEBUG"):
            _ret = _hook(
                samples=input_value,
                config=MagicMock(workdir=tmp_path, timestamp="DUMMY", log_level=None),
                root=Path(),
                executor_cls=SubprocesExecutor,
                log_queue=Queue(),
            )

        for log_line in logs:
            assert log_line in "\n".join(caplog.messages)
        assert _ret.value == expected


class Test__resolve_hook_dependencies:
    """Test _resolve_hook_dependencies function."""

    @staticmethod
    def func(name: str) -> Callable[[], None]:
        """Create dummy function."""

        def _dummy() -> None:
            pass

        _dummy.__name__ = name
        _dummy.__qualname__ = name

        return _dummy

    @staticmethod
    @mark.parametrize(
        "hooks,expected",
        [
            param(
                [modules.pre_hook()(func("a"))],
                ["a"],
                id="single",
            ),
            param(
                [
                    modules.pre_hook()(func("a")),
                    modules.pre_hook(before=["a"])(func("b")),
                ],
                ["b", "a"],
                id="b_before_a",
            ),
            param(
                [
                    modules.pre_hook(after=["b"])(func("a")),
                    modules.pre_hook()(func("b")),
                ],
                ["b", "a"],
                id="a_after_b",
            ),
            param(
                [
                    modules.pre_hook()(func("a")),
                    modules.pre_hook(before=["a"])(func("b")),
                    modules.pre_hook(before="all")(func("c")),
                ],
                ["c", "b", "a"],
                id="c_before_all",
            ),
            param(
                [
                    modules.pre_hook(after="all")(func("a")),
                    modules.pre_hook(after=["c"])(func("b")),
                    modules.pre_hook()(func("c")),
                ],
                ["c", "b", "a"],
                id="a_after_all",
            ),
            param(
                [
                    modules.pre_hook(after="all", before=["b"])(func("a")),
                    modules.pre_hook(after="all")(func("b")),
                    modules.pre_hook()(func("c")),
                ],
                ["c", "a", "b"],
                id="a_before_b_after_all",
            ),
        ],
    )
    @mark.repeat(10)
    def test_resolve(
        hooks: list[modules.Hook],
        expected: list[str],
    ) -> None:
        """Test _resolve_hook_dependencies function."""
        # FIXME: Hook order is non-deterministic if there are no dependencies
        _resolved = modules._resolve_hook_dependencies(hooks)
        assert [m.label for m in _resolved] == expected

    @staticmethod
    @mark.parametrize(
        "hooks",
        [
            param(
                [
                    modules.pre_hook(before=["a"])(func("a")),
                    modules.pre_hook(before=["b"])(func("b")),
                ],
                id="simple_loop",
            ),
            param(
                [
                    modules.pre_hook(before=["b"])(func("a")),
                    modules.pre_hook(after=["a"], before=["c"])(func("b")),
                    modules.pre_hook(before=["a"])(func("c")),
                ],
                id="complex_loop",
            ),
            param(
                [
                    modules.pre_hook(before="all", after=["b"])(func("a")),
                    modules.pre_hook()(func("b")),
                ],
                id="a_before_all_after_b",
            ),
            param(
                [
                    modules.pre_hook(after="all", before=["b"])(func("a")),
                    modules.pre_hook()(func("b")),
                ],
                id="a_after_all_before_b",
            ),
        ],
    )
    def test_resolve_exception(hooks: list[type[modules.Hook]]) -> None:
        """Test _resolve_hook_dependencies function exceptions."""
        assert raises(CycleError, modules._resolve_hook_dependencies, hooks)


class Test_load:
    """Test modules load function."""

    @staticmethod
    @mark.parametrize(
        "path,expected",
        [
            param(
                LIB / "modules" / "mod_basic",
                {
                    "hooks": {"pre_hook_basic", "post_hook_basic"},
                    "runners": {"runner_basic"},
                    "sample_mixins": {"SampleMixinBasic"},
                    "samples_mixins": {"SamplesMixinBasic"},
                },
                id="basic",
            ),
            param(
                LIB / "modules" / "mod_directory",
                {
                    "hooks": {"pre_hook_directory", "post_hook_directory"},
                    "runners": {"runner_directory"},
                    "sample_mixins": {"SampleMixinDirectory"},
                    "samples_mixins": {"SamplesMixinDirectory"},
                },
                id="directory",
            ),
        ],
    )
    def test_load(path: Path, expected: dict) -> None:
        """Test modules load function."""
        (
            _hooks,
            _runners,
            _sample_mixins,
            _samples_mixins,
            _executors,
        ) = modules.load(path)
        assert {h.name for h in _hooks} == expected.get("hooks", {})
        assert {r.name for r in _runners} == expected.get("runners", {})
        assert {m.__name__ for m in _sample_mixins} == expected.get("sample_mixins", {})
        assert {m.__name__ for m in _samples_mixins} == expected.get(
            "samples_mixins", []
        )

    @staticmethod
    def test_load_exception() -> None:
        """Test modules load function exceptions."""
        with raises(ImportError):
            modules.load(LIB / "modules" / "mod_invalid")

    @staticmethod
    def test_load_override_logging() -> None:
        """Test modules load function log hander reset."""
        handlers = copy(logging.getLogger().handlers)
        modules.load(LIB / "modules" / "mod_override_logging")
        assert logging.getLogger().handlers == handlers
