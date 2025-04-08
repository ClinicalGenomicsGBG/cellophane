from cellophane.testing import BaseTest, Invocation, literal
from pytest import mark


class Test_hooks(BaseTest):
    args = ["--workdir out"]

    @mark.override(
        args=[*args, "--samples_file samples.yaml"],
        structure={
            "modules/a.py": """
                from cellophane import Sample, Samples, runner, post_hook, pre_hook
                from attrs import define, field

                @define(slots=False, init=False)
                class SampleMixin(Sample):
                    group: str | None = None
                    var: list[str] = field(factory=list)

                    @Sample.merge.register("var")
                    @staticmethod
                    def merge_var(this: list[str], that: list[str]):
                        return [*this, *that]

                @define(slots=False, init=False)
                class SamplesMixin(Samples):
                    var: list[str] = field(factory=list)

                    @Samples.merge.register("var")
                    @staticmethod
                    def merge_var(this: list[str], that: list[str]):
                        return [*this, *that]


                @runner(split_by="group")
                def runner_a(samples, logger, **_):
                    tag = "runner_a"
                    samples.var.append(tag)

                    for sample in samples:
                        sample.var.append(tag)
                        if sample.files[0].read_text() == "FAIL":
                            sample.fail("DUMMY FAIL")
                    return samples

                @runner(split_by="group")
                def runner_b(samples, logger, **_):
                    tag = "runner_b"
                    samples.var.append(tag)
                    logger.info(f"{tag}: {sorted(samples.unique_ids)}")
                    for sample in samples:
                        sample.var.append(tag)
                    return samples

                def hook_factory(tag):
                    def _hook(samples, logger, **_):
                        samples.var.append(tag)
                        logger.info(f"{tag}: {sorted(samples.unique_ids)}")
                        for sample in samples:
                            sample.var.append(tag)
                        return samples
                    _hook.__name__ = tag
                    return _hook

                pre = pre_hook()(hook_factory("pre"))
                post_always = post_hook(condition="always")(hook_factory("post_always"))
                post_complete = post_hook(condition="complete")(hook_factory("post_complete"))
                post_failed = post_hook(condition="failed")(hook_factory("post_failed"))
                pre_per_runner = pre_hook(per="runner")(hook_factory("pre_per_runner"))
                post_per_runner_always = post_hook(per="runner", condition="always")(hook_factory("post_per_runner_always"))
                post_per_runner_complete = post_hook(per="runner", condition="complete")(hook_factory("post_per_runner_complete"))
                post_per_runner_fail  = post_hook(per="runner", condition="failed")(hook_factory("post_per_runner_failed"))
                post_per_sample_always = post_hook(per="sample", condition="always")(hook_factory("post_per_sample_always"))
                post_per_sample_complete  = post_hook(per="sample", condition="complete")(hook_factory("post_per_sample_complete"))
                post_per_sample_failed = post_hook(per="sample", condition="failed")(hook_factory("post_per_sample_failed"))

                @post_hook(after="all")
                def log_var(samples, logger, **_):
                    logger.info(f"SAMPLES VAR: {samples.var}")
                    for sample in samples:
                        logger.info(f"SAMPLE VAR - {sample.id}: {sample.var}")
                    return samples
            """,
            "samples.yaml": """
                - id: pass_x_a
                  group: x
                  files:
                  - input/pass.txt
                - id: pass_x_b
                  group: x
                  files:
                  - input/pass.txt
                - id: pass_y_c
                  group: y
                  files:
                  - input/pass.txt
                - id: fail_x_a
                  group: x
                  files:
                  - input/fail.txt
                - id: fail_y_b
                  group: y
                  files:
                  - input/fail.txt
                - id: fail_y_c
                  group: y
                  files:
                  - input/fail.txt
            """,
            "input/pass.txt": "PASS",
            "input/fail.txt": "FAIL",
        },
    )
    def test_hooks(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Running pre hook",
            "Running post_always hook",
            "Running post_failed hook",
            "Running post_complete hook",
            "Running pre_per_runner hook",
            "Running post_per_runner_always hook",
            "pre: ['fail_x_a', 'fail_y_b', 'fail_y_c', 'pass_x_a', 'pass_x_b', 'pass_y_c']",
            "pre_per_runner: ['fail_x_a', 'pass_x_a', 'pass_x_b']",
            "pre_per_runner: ['fail_y_b', 'fail_y_c', 'pass_y_c']",
            "post_per_runner_always: ['fail_x_a', 'pass_x_a', 'pass_x_b']",
            "post_per_runner_always: ['fail_y_b', 'fail_y_c', 'pass_y_c']",
            "post_per_runner_complete: ['pass_x_a', 'pass_x_b']",
            "post_per_runner_complete: ['pass_y_c']",
            "post_per_runner_failed: ['fail_x_a']",
            "post_per_runner_failed: ['fail_y_b', 'fail_y_c']",
            "post_per_sample_always: ['pass_x_a']",
            "post_per_sample_always: ['pass_x_b']",
            "post_per_sample_always: ['pass_y_c']",
            "post_per_sample_always: ['fail_x_a']",
            "post_per_sample_always: ['fail_y_b']",
            "post_per_sample_always: ['fail_y_c']",
            "post_per_sample_complete: ['pass_x_a']",
            "post_per_sample_complete: ['pass_x_b']",
            "post_per_sample_complete: ['pass_y_c']",
            "post_per_sample_failed: ['fail_x_a']",
            "post_per_sample_failed: ['fail_y_b']",
            "post_per_sample_failed: ['fail_y_c']",
            "post_failed: ['fail_x_a', 'fail_y_b', 'fail_y_c']",
            "post_complete: ['pass_x_a', 'pass_x_b', 'pass_y_c']",
            "post_always: ['fail_x_a', 'fail_y_b', 'fail_y_c', 'pass_x_a', 'pass_x_b', 'pass_y_c']",
        )

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import pre_hook, Samples, stage

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

                @pre_hook(before=stage.ALL)
                def a(samples, logger, **_):
                    assert "before_all_a" in samples.executed, hook_info(samples, msg="Expected before_all_a to be executed")
                    assert "before_all_after_a" in samples.not_executed, hook_info(samples, msg="Expected before_all_after_a to not be executed")
                    samples.executed.add("a")

                @pre_hook(before=[stage.ALL, "a"])
                def before_all_a(samples, logger, **_):
                    assert not samples.executed, hook_info(samples, msg="Expected no hooks to be executed")
                    samples.executed.add("before_all_a")

                @pre_hook(before=stage.ALL, after="a")
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

                @pre_hook(after=stage.ALL, before="b")
                def after_all_before_b(samples, logger, **_):
                    assert "b" not in samples.executed, hook_info(samples, msg="Expected 'b' to not be executed")
                    samples.executed.add("after_all_before_b")

                @pre_hook(after=[stage.ALL, "b"])
                def after_all_b(samples, logger, **_):
                    assert "db" in samples.executed, hook_info(samples, msg="Expected 'b' to be executed")
                    samples.executed.add("after_all_b")

                @pre_hook(after=stage.ALL)
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
                from cellophane import pre_hook, post_hook, Samples, stage
                from cellophane.modules.deps import _internal

                ####
                # Pre hook order (Samples > Notifications > Files > Outputs)
                # Reversed to ensure hooks are reordered correctly
                ####
                @pre_hook(after=stage.ALL)
                def pre_after_all(samples, logger, **_): return samples

                @pre_hook(after=stage.FILES_FINALIZED)
                def pre_after_files_finalized(samples, logger, **_): return samples

                @pre_hook(after=stage.OUTPUT_PRESENT, before=stage.OUTPUT_FINALIZED)
                def pre_before_output_finalized(samples, logger, **_): return samples

                @pre_hook(after=stage.FILES_FINALIZED, before=stage.OUTPUT_PRESENT)
                def pre_before_output_present(samples, logger, **_): return samples

                @pre_hook(after=stage.FILES_PRESENT, before=stage.FILES_FINALIZED)
                def pre_before_files_finalized(samples, logger, **_): return samples

                @pre_hook(after=stage.NOTIFICATIONS_SENT, before=stage.FILES_PRESENT)
                def pre_before_files_present(samples, logger, **_): return samples

                @pre_hook(after=stage.NOTIFICATIONS_FINALIZED, before=stage.NOTIFICATIONS_SENT)
                def pre_before_notifications_sent(samples, logger, **_): return samples

                @pre_hook(after=stage.SAMPLES_FINALIZED, before=stage.NOTIFICATIONS_FINALIZED)
                def pre_before_notifications_finalized(samples, logger, **_): return samples

                @pre_hook(after=stage.SAMPLES_PRESENT, before=stage.SAMPLES_FINALIZED)
                def pre_before_samples_finalized(samples, logger, **_): return samples

                @pre_hook(before=stage.SAMPLES_PRESENT)
                def pre_before_samples_present(samples, logger, **_): return samples

                @pre_hook(before=stage.ALL)
                def pre_before_all(samples, logger, **_): return samples

                ####
                # Post hook order (Samples (finalized) > Outputs > Notifications)
                # Reversed to ensure hooks are reordered correctly
                ####

                @post_hook(after=stage.ALL)
                def post_after_all(samples, logger, **_): return samples

                @post_hook(after=stage.NOTIFICATIONS_SENT)
                def post_after_notifications_sent(samples, logger, **_): return samples

                @post_hook(after=stage.NOTIFICATIONS_FINALIZED, before=stage.NOTIFICATIONS_SENT)
                def post_before_notifications_sent(samples, logger, **_): return samples

                @post_hook(after=stage.OUTPUT_TRANSFERED, before=stage.NOTIFICATIONS_FINALIZED)
                def post_before_notifications_finalized(samples, logger, **_): return samples

                @post_hook(after=stage.OUTPUT_FINALIZED, before=stage.OUTPUT_TRANSFERED)
                def post_before_output_transfered(samples, logger, **_): return samples

                @post_hook(after=stage.OUTPUT_PRESENT, before=stage.OUTPUT_FINALIZED)
                def post_before_output_finalized(samples, logger, **_): return samples

                @post_hook(after=stage.SAMPLES_FINALIZED, before=stage.OUTPUT_PRESENT)
                def post_before_output_present(samples, logger, **_): return samples

                @post_hook(before=stage.SAMPLES_FINALIZED)
                def post_before_samples_finalized(samples, logger, **_): return samples

                @post_hook(before=stage.ALL)
                def post_before_all(samples, logger, **_): return samples
            """,
        },
    )
    def test_hooks_staging(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            (
                "Running pre_before_all hook\n"
                "Running pre_before_samples_present hook\n"
                "Running pre_before_samples_finalized hook\n"
                "Running pre_before_notifications_finalized hook\n"
                "Running pre_before_notifications_sent hook\n"
                "Running pre_before_files_present hook\n"
                "Running pre_before_files_finalized hook\n"
                "Running pre_after_files_finalized hook\n"
                "Running pre_before_output_present hook\n"
                "Running pre_before_output_finalized hook\n"
                "Running pre_after_all hook"
            ),
            (
                "Running post_before_all hook\n"
                "Running post_before_samples_finalized hook\n"
                "Running post_before_output_present hook\n"
                "Running post_before_output_finalized hook\n"
                "Running post_before_output_transfered hook\n"
                "Running post_before_notifications_finalized hook\n"
                "Running post_before_notifications_sent hook\n"
                "Running post_after_notifications_sent hook\n"
                "Running post_after_all hook"
            ),
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
            "Unable to import module 'a': ValueError(\"a: before=[<class 'modules.a.INVALID'>], after=[]\")"
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
            "Unable to import module 'a': ValueError(\"a: before=[], after=[<class 'modules.a.INVALID'>]\")"
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
