from cellophane.testing import BaseTest, Invocation, literal
from pytest import mark


class Test_samples(BaseTest):
    args = ["--workdir out", "--samples_file samples.yml"]
    structure = {
        "samples.yml": """
            - id: a
              files: ["input.txt"]
            - id: b
              files: ["input.txt"]
            - id: c
              files: []
            - id: d
              files: ["missing.txt"]
            - id: d
              files: ["also_missing.txt"]
        """,
        "input.txt": "hello",
    }

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner, post_hook

                @runner(split_by="id")
                def test_runner(samples, **_):
                    if samples[0].id == "fail":
                        samples[0].fail("SOME FAILURE")

                @post_hook()
                def test_hook(samples, logger, **_):
                    for sample in samples.failed:
                        logger.info(f"Failed: {sample} - {sample.failed}")
                    for sample in samples.complete:
                        logger.info(f"Complete: {sample}")
            """,
            "samples.yml": """
                - id: pass
                  files: ["input.txt"]
                - id: fail
                  files: ["input.txt"]
                - id: no_files
                  files: []
            """,
        }
    )
    def test_failed_complete(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Failed: fail - SOME FAILURE",
            "Failed: no_files - Missing files",
            "Complete: pass",
        )

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import pre_hook
                from uuid import uuid4

                @pre_hook()
                def test_hook(samples, logger, **_):
                    samples[0]["files"] = ["new.txt"]
                    logger.info(f"{samples[0].files=}")

            """,
        }
    )
    def test_sample_setitem(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("samples[0].files=[PosixPath('new.txt')]")

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import pre_hook

                @pre_hook()
                def test(samples, logger, **_):
                    for id, group in samples.split(by=None):
                        logger.info(f"ID: '{id}' - {len(group)} samples - {group==samples=}")

                    for id, group in samples.split(by="id"):
                        logger.info(f"ID: '{id}' - {len(group)} samples - {group==samples=}")
            """,
        }
    )
    def test_split_by(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "ID: 'None' - 5 samples - group==samples=True",
            "ID: 'a' - 1 samples - group==samples=False",
            "ID: 'b' - 1 samples - group==samples=False",
            "ID: 'c' - 1 samples - group==samples=False",
            "ID: 'd' - 2 samples - group==samples=False",
        )

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner, post_hook, data

                @runner()
                def a(samples, logger, **_):
                    for sample in samples:
                        if sample.id == "files":
                            sample.files += ["extra_a.txt"]
                        elif sample.id == "meta":
                            sample.meta = {"common_key": ["value_a"], "a": "unique_for_a"}
                        elif sample.id == "fail":
                            sample.fail("Reason A")

                @runner()
                def b(samples, logger, **_):
                    for sample in samples:
                        if sample.id == "files":
                            sample.files += ["extra_b.txt"]
                        elif sample.id == "meta":
                            sample.meta = {"common_key": ["value_b"], "b": "unique_for_b"}
                        elif sample.id == "fail":
                            sample.fail("Reason B")

                @post_hook()
                def test_hook(samples, logger, **_):
                    for sample in samples:
                        if sample.id == "files":
                            logger.info(f"Files: {sorted([str(f) for f in sample.files])}")
                        elif sample.id == "meta":
                            logger.info(f"meta.common_key={sorted(sample.meta['common_key'])}")
                            logger.info(f"meta.a={sample.meta['a']}")
                            logger.info(f"meta.b={sample.meta['b']}")
                        elif sample.id == "fail":
                            logger.info(f"Failed: {sample.failed}")
            """,
            "samples.yml": """
                - id: files
                  files: ["input.txt"]
                - id: meta
                  files: ["input.txt"]
                - id: fail
                  files: ["input.txt"]
            """,
        }
    )
    def test_merge(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Files: ['extra_a.txt', 'extra_b.txt', 'input.txt']",
            "meta.common_key=['value_a', 'value_b']",
            "meta.a=unique_for_a",
            "meta.b=unique_for_b",
        )
        assert (
            invocation.logs == literal("Failed: Reason A\nReason B")
            or invocation.logs == literal("Failed: Reason B\nReason A")
        )


class Test_mixins(BaseTest):
    args = ["--workdir out"]
    structure = {
        "modules/mixins.py": """
            from cellophane import Sample
            from attrs import define

            @define(slots=True)
            class SampleMixin(Sample):
                x: int = 1
        """,
    }

    def test_slotted_mixin(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "SampleMixin: Mixins must not have __slots__ (use @define(slots=False) and don't set __slots__ in the class body)"
        )
