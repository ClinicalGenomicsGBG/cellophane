from cellophane.testing import BaseTest, Invocation, literal
from pytest import mark


class Test_module_load(BaseTest):
    args = ["--workdir out"]

    structure = {
        "modules/runner.py": """
            from cellophane import runner

            @runner()
            def file_runner_a(samples, **_):
                ...

            @runner()
            def file_runner_b(samples, **_):
                ...

        """,
        "modules/hooks.py": """
            from cellophane import pre_hook, post_hook

            @pre_hook()
            def file_pre_hook_a(**_):
                ...

            @pre_hook()
            def file_pre_hook_b(**_):
                ...

            @post_hook()
            def file_post_hook_a(**_):
                ...

            @post_hook()
            def file_post_hook_b(**_):
                ...
        """,
        "modules/mixins.py": """
            from cellophane import Sample, Samples

            class file_Sample_a(Sample):
                ...

            class file_Sample_b(Sample):
                ...

            class file_Samples_a(Samples):
                ...

            class file_Samples_b(Samples):
                ...
        """,
        "modules/executors.py": """
            from cellophane import Executor

            class file_Executor_a(Executor, name="file_executor"):
                ...

            class file_Executor_b(Executor, name="file_executor"):
                ...
        """,
        "modules/dir/__init__.py": """
            from cellophane import pre_hook, runner, Executor, Sample, Samples

            @pre_hook()
            def dir_pre_hook_a(**_):
                ...

            @pre_hook()
            def dir_pre_hook_b(**_):
                ...

            @runner()
            def dir_runner_a(samples, **_):
                ...

            @runner()
            def dir_runner_b(samples, **_):
                ...

            class dir_Sample_a(Sample):
                ...

            class dir_Sample_b(Sample):
                ...

            class dir_Samples_a(Samples):
                ...

            class dir_Samples_b(Samples):
                ...

            class dir_Executor_a(Executor, name="dir_executor"):
                ...

            class dir_Executor_b(Executor, name="dir_executor"):
                ...
        """,
    }

    def test_module_load(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Found 6 hooks",
            "Found 4 runners",
            "Found 4 sample mixins",
            "Found 4 samples mixins",
            "Found 6 executors",
        )

    @mark.override(structure={"modules/a.py": "INVALID"})
    def test_invalid_module(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unable to import module 'a': NameError(\"name 'INVALID' is not defined\")"
        )
        assert invocation.exit_code == 1

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import pre_hook

                @pre_hook(after=["pre_hook_a"])
                def pre_hook_a(**_):
                    ...

                @pre_hook(after=["pre_hook_b"])
                def pre_hook_b(**_):
                    ...
            """,
        }
    )
    def test_bad_hook_order(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("Unable to resolve hook dependencies")
        assert invocation.exit_code == 1

    @mark.override(
        structure={
            "modules/a.py": """
                import logging
                logging.root.addHandler(logging.StreamHandler())
                logging.critical("SHOULD BE SUPPRESSED")
            """,
        }
    )
    def test_module_add_log_handler(self, invocation: Invocation) -> None:
        assert "SHOULD BE SUPPRESSED" not in invocation.logs
        assert invocation.exit_code == 0
