from cellophane.testing import BaseTest, Invocation, literal
from pytest import mark


class Test_hooks(BaseTest):
    args = ["--workdir out"]

    @mark.override(
        args=[*args, "--samples_file samples.yaml"],
        structure={
            "modules/a.py": """
                from cellophane import runner, post_hook, pre_hook

                @runner()
                def runner_a(samples, **_):
                    for sample in samples:
                        if sample.id == "fail":
                            sample.fail("DUMMY FAIL")
                    return samples

                @post_hook(condition="always")
                def always_hook(samples, **_):
                    ...

                @post_hook(condition="complete")
                def complete_hook(samples, **_):
                    ...

                @post_hook(condition="failed")
                def fail_hook(samples, **_):
                    ...
            """,
            "samples.yaml": """
                - id: pass
                  files:
                  - input/pass.txt
                - id: fail
                  files:
                  - input/fail.txt
            """,
            "input/pass.txt": "PASS",
            "input/fail.txt": "FAIL",
        },
    )
    def test_hooks(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Running fail_hook hook",
            "Running always_hook hook",
            "Running complete_hook hook",
        )

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import pre_hook, Samples

                class TestSamples(Samples):
                    executed = set()

                    @property
                    def not_executed(self):
                        return {
                            "a",
                            "before_all_a",
                            "before_all_after_a",
                            "before_x",
                            "before_xy",
                            "x",
                            "y",
                            "after_x_before_y",
                            "after_x",
                            "after_xy",
                            "after_all_before_b",
                            "after_all_b",
                            "b",
                        } - self.executed

                def hook_info(samples, msg=None):
                    return "".join(
                        (
                            (f"{msg}\\n" if msg else ""),
                            f"Executed: {', '.join(samples.executed)}\\n",
                            f"Not executed: {', '.join(samples.not_executed)}\\n",
                        )
                    )

                @pre_hook(before="all")
                def a(samples, logger, **_):
                    assert "before_all_a" in samples.executed, hook_info(samples, msg="Expected before_all_a to be executed")
                    assert "before_all_after_a" in samples.not_executed, hook_info(samples, msg="Expected before_all_after_a to not be executed")
                    samples.executed.add("a")

                @pre_hook(before=["all", "a"])
                def before_all_a(samples, logger, **_):
                    assert not samples.executed, hook_info(samples, msg="Expected no hooks to be executed")
                    samples.executed.add("before_all_a")

                @pre_hook(before="all", after="a")
                def before_all_after_a(samples, logger, **_):
                    assert "a" in samples.executed, hook_info(samples, msg="Expected 'a' to be executed")
                    samples.executed.add("before_all_after_a")

                @pre_hook(before="x")
                def before_x(samples, logger, **_):
                    assert "x" in samples.not_executed, hook_info(samples, msg="Expected 'x' to not be executed")
                    samples.executed.add("before_x")

                @pre_hook(before=["x", "y"])
                def before_xy(samples, logger, **_):
                    samples.executed.add("before_xy")

                @pre_hook()
                def x(samples, logger, **_):
                    samples.executed.add("x")

                @pre_hook()
                def y(samples, logger, **_):
                    samples.executed.add("y")

                @pre_hook(after="x", before="y")
                def after_x_before_y(samples, logger, **_):
                    assert "x" in samples.executed, hook_info(samples, msg="Expected 'x' to be executed")
                    assert "y" not in samples.executed, hook_info(samples, msg="Expected 'y' to not be executed")
                    samples.executed.add("after_x_before_y")

                @pre_hook(after="x")
                def after_x(samples, logger, **_):
                    assert "x" in samples.executed, hook_info(samples, msg="Expected 'x' to be executed")
                    samples.executed.add("after_x")

                @pre_hook(after=["x", "y"])
                def after_xy(samples, logger, **_):
                    assert {"x", "y"} <= samples.executed, hook_info(samples, msg="Expected 'x' and 'y' to be executed")
                    samples.executed.add("after_xy")

                @pre_hook(after="all", before="b")
                def after_all_before_b(samples, logger, **_):
                    assert "b" not in samples.executed, hook_info(samples, msg="Expected 'b' to not be executed")
                    samples.executed.add("after_all_before_b")

                @pre_hook(after=["all", "b"])
                def after_all_b(samples, logger, **_):
                    assert "db" in samples.executed, hook_info(samples, msg="Expected 'b' to be executed")
                    samples.executed.add("after_all_b")

                @pre_hook(after="all")
                def b(samples, logger, **_):
                    samples.executed.add("b")
            """,
        },
    )
    def test_hooks_order(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Running a hook",
            "Running before_all_a hook",
            "Running before_all_after_a hook",
            "Running before_x hook",
            "Running before_xy hook",
            "Running x hook",
            "Running after_x_before_y hook",
            "Running after_x hook",
            "Running after_xy hook",
            "Running after_all_before_b hook",
            "Running after_all_b hook",
            "Running b hook",
        )

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import pre_hook

                class INVALID: ...

                @pre_hook(before=INVALID)
                def a(samples, logger, **_):
                    ...
            """
        },
    )
    def test_invalid_hook_before(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unable to import module 'a': ValueError(\"a: before=<class 'modules.a.INVALID'>, after=[]\")"
        )

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import pre_hook

                class INVALID: ...

                @pre_hook(after=INVALID)
                def a(samples, logger, **_):
                    ...
            """
        },
    )
    def test_invalid_hook_after(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unable to import module 'a': ValueError(\"a: before=[], after=<class 'modules.a.INVALID'>\")"
        )

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import pre_hook

                class INVALID: ...

                @pre_hook()
                def return_samples(samples, logger, **_):
                    return samples

                @pre_hook()
                def return_none(samples, logger, **_):
                    ...

                @pre_hook()
                def return_invalid(samples, logger, **_):
                    return INVALID()
            """
        },
    )
    def test_hook_return(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unexpected return type <class 'modules.a.INVALID'>",
            "Hook did not return any samples",
        )

    @mark.override(
        args=[*args, "--samples_file samples.yaml"],
        structure={
            "modules/a.py": """
                from cellophane import pre_hook

                @pre_hook()
                def a(samples, logger, **_):
                    raise KeyboardInterrupt()
            """,
            "samples.yaml": """
                - id: a
                  files:
                  - input/a.txt
            """,
            "input/a.txt": "INPUT_A",
        },
    )
    def test_hook_keyboard_interrupt(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Keyboard interrupt received, failing samples and stopping execution"
        )

    @mark.override(
        args=[*args, "--samples_file samples.yaml"],
        structure={
            "modules/a.py": """
                from cellophane import pre_hook

                @pre_hook()
                def a(samples, logger, **_):
                    raise Exception("BOOM")
            """,
            "samples.yaml": """
                - id: a
                  files:
                  - input/a.txt
            """,
            "input/a.txt": "INPUT_A",
        },
    )
    def test_hook_exception(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("Exception in a: BOOM")

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import post_hook

                @post_hook(condition="INVALID")
                def a(**_): ...
            """
        },
    )
    def test_hook_invalid_condition(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unable to import module 'a': ValueError(\"condition='INVALID' must be one of 'always', 'complete', 'failed'\")"
        )
