from click import FileError
from pytest import mark

from cellophane.testing import BaseTest, Invocation, literal


class Test_exceptions(BaseTest):
    args = ["--workdir out", "--samples_file samples.yaml"]
    structure = {
        "samples.yaml": """
            - id: a
              files:
              - input/a.txt
            - id: b
              files:
              - input/b.txt
        """,
        "input/a.txt": "INPUT_A",
        "input/b.txt": "INPUT_B",
    }

    @mark.override(
        mocks={"cellophane.modules.dispatcher.Dispatcher.run_pre_hooks": {"side_effect": Exception("DUMMY")}}
    )
    def test_unhandled_exception(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("Unhandled exception: Exception('DUMMY')")
        assert invocation.exit_code == 1

    @mark.override(args=[*args, "--config_file missing.yaml"])
    def test_missing_config(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, FileError)
        assert (
            "[Errno 2] No such file or directory: 'missing.yaml'"
            in invocation.exception.args
        )
        assert invocation.exit_code == 1

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner, Sample

                class SampleMixin(Sample):
                    foo: str = "foo"

                @Sample.merge.register("foo")
                def merge_foo(this, that):
                    raise Exception("DUMMY")

                @runner()
                def runner_a(samples, **_):
                    ...

                @runner()
                def runner_b(samples, **_):
                    ...
            """,
        },
    )
    def test_merge_exception(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("Unhandled exception when merging samples: Exception('DUMMY')")
        assert invocation.exit_code == 0

    @mark.override(
        args=[*args, "--samples_file samples.yaml"],
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner(samples, **_):
                    ...
            """,
        },
        mocks={
            "cellophane.modules.dispatcher.WorkerPool.apply_async": {
                "side_effect": KeyboardInterrupt
            }
        },
    )
    def test_keyboard_interrupt(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Received SIGINT, telling runners to shut down..."
        )
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner(samples, **_):
                    raise Exception("DUMMY")
            """,
        },
    )
    def test_runner_exception(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unhandled exception in runner 'runner': Exception('DUMMY')",
            "Clearing outputs and failing samples",
            "Sample a failed - Unhandled exception in runner 'runner': Exception('DUMMY')",
            "Sample b failed - Unhandled exception in runner 'runner': Exception('DUMMY')",
        )
        assert invocation.exit_code == 0
