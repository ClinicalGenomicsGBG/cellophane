from cellophane.testing import BaseTest, Invocation, literal
from mpire.pool import WorkerPool as WorkerPool
from pytest import mark


class Test_runners(BaseTest):
    args = ["--workdir out", "--samples_file samples.yaml"]
    structure = {
        "samples.yaml": """
            - id: a
              files:
              - input/a.txt
        """,
        "input/a.txt": "INPUT_A",
    }

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                class INVALID: ...

                @runner()
                def return_samples(samples, logger, **_):
                    return samples

                @runner()
                def return_none(samples, logger, **_):
                    ...

                @runner()
                def return_invalid(samples, logger, **_):
                    return INVALID()
            """,
        },
    )
    def test_runner_return(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unexpected return type <class 'modules.a.INVALID'>",
            "Runner did not return any samples",
        )

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner_(**_):
                    raise Exception("DUMMY")
            """,
        },
    )
    def test_runner_exception(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unhandled exception: Exception('DUMMY')",
            "Sample a failed - Unhandled exception in runner 'runner_' Exception('DUMMY')",
        )

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner_(**_):
                    raise SystemExit(1337)
            """,
        },
    )
    def test_runner_exit_non_zero(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Runner exited with non-zero status(1337)",
            "Sample a failed - Runner 'runner_' exitded with non-zero status(1337)",
        )

    @mark.override(structure={**structure})
    def test_no_runners(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("No runners to execute")

    @mark.override(
        args=["--workdir out"],
        structure={
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner_(**_): ...
            """
        },
    )
    def test_no_samples(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("No samples to process")

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner, Samples

                class TestSamples(Samples):
                    a: int = 1

                    @Samples.merge.register("a")
                    def merge_a(this, that):
                        raise Exception("DUMMY")

                @runner()
                def a(**_): ...

                @runner()
                def b(**_): ...
            """,
        }
    )
    def test_results_exception(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Exception when merging samples: Exception('DUMMY')"
        )

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner, Sample

                class TestSample(Sample):
                    some_key: int = 0

                @runner(split_by="some_key")
                def a(samples, logger, **_):
                    logger.info(f"Runner a: {[str(s) for s in samples]}")
            """,
            "samples.yaml": """
                - id: a
                  some_key: 1
                  files: ["input/a.txt"]
                - id: b
                  some_key: 1
                  files: ["input/a.txt"]
                - id: c
                  some_key: 2
                  files: ["input/a.txt"]
                - id: d
                  some_key: 2
                  files: ["input/a.txt"]
            """,
        }
    )
    def test_runner_split_by(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Runner a: ['a', 'b']",
            "Runner a: ['c', 'd']",
        )
