"""Test cellphane.src.executors."""

import time
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

from pytest import LogCaptureFixture, fixture, raises
from pytest_mock import MockerFixture

from cellophane import data, executors, logs


@fixture(scope="function")
def spe(tmp_path: Path) -> Generator[executors.SubprocessExecutor, None, None]:
    """Return a SubprocessExecutor."""
    config = data.Container(
        workdir=tmp_path,
        logdir=tmp_path,
        executor={"cpus": 1, "memory": 1},
    )

    log_queue, log_listener = logs.start_logging_queue_listener()

    with executors.SubprocessExecutor(config=config, log_queue=log_queue) as executor:
        yield executor

    log_listener.stop()


class Test_SubprocessExecutor:
    """Test SubprocessExecutor."""

    @staticmethod
    def test_callback(
        spe: executors.SubprocessExecutor,  # pylint: disable=redefined-outer-name
    ) -> None:
        """Test callback."""
        _callback = MagicMock()
        _error_callback = MagicMock()
        assert not _callback.called
        assert not _error_callback.called
        spe.submit(
            "sleep 0",
            name="sleep",
            wait=True,
            callback=_callback,
            error_callback=_error_callback,
        )
        assert _callback.called
        assert not _error_callback.called
        spe.submit(
            "exit 42",
            name="exception",
            wait=True,
            callback=_callback,
            error_callback=_error_callback,
        )
        assert _error_callback.called

    def test_executor_terminate_all(
        self,
        spe: executors.SubprocessExecutor,  # pylint: disable=redefined-outer-name
    ) -> None:
        """Test that all processes are terminated when the executor is terminated."""
        results = [
            spe.submit("sleep 1", name="sleep")[0],
            spe.submit("sleep 1", name="sleep")[0],
            spe.submit("sleep 1", name="sleep")[0],
        ]
        time.sleep(0.1)
        assert not any(r.ready() for r in results), [r.get() for r in results]
        spe.terminate()
        spe.wait()
        assert all(r.ready() for r in results)

    @staticmethod
    def test_command_exception(
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
        spe: executors.SubprocessExecutor,  # pylint: disable=redefined-outer-name
    ) -> None:
        """Test command exception."""
        mocker.patch(
            "cellophane.executors.subprocess_executor.sp.Popen",
            side_effect=Exception("DUMMY"),
        )

        with (
            caplog.at_level("DEBUG"),
            raises(SystemExit) as exc,
        ):
            result = spe.submit("exit", name="exception")[0]

            spe.wait()
            result.get()

        assert repr(exc.value) == "SystemExit(1)"
        assert "Command failed with exception: Exception('DUMMY')" in caplog.messages

    @staticmethod
    def test_wait_for_uuid(
        spe: executors.SubprocessExecutor,  # pylint: disable=redefined-outer-name
    ) -> None:
        """Test wait_for_uuid."""
        result1, uuid1 = spe.submit("sleep .1", name="sleep")
        result2, _ = spe.submit("sleep 2", name="sleep")

        spe.wait(uuid1)
        spe.terminate()

        assert result1.ready()
        assert not result2.successful()
