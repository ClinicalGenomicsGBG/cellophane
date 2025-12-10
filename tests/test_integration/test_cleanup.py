from pytest import mark

from cellophane.testing import BaseTest, Invocation, literal


class Test_cleanup(BaseTest):
    structure = {
        "samples.yaml": """
            - id: a
              files:
              - input/a.txt
        """,
        "input/a.txt": "INPUT_A",
    }
    args = [
        "--samples_file samples.yaml",
        "--workdir out",
        "--tag DUMMY",
    ]

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner(logger, **_):
                    logger.critical("DUMMY")
            """,
        },
    )
    def test_cleanup_defaults(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("Removing out/DUMMY")
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner(workdir, logger, cleaner, **_):
                    (workdir / "a" / "b" / "c").mkdir(parents=True)
                    (workdir / "a" / "x.txt").touch()
                    (workdir / "a" / "b" / "y.txt").touch()
                    (workdir / "a" / "b" / "c" / "z.txt").touch()
                    (workdir / "a" / "d" / "e" / "f").mkdir(parents=True)
                    (workdir / "a" / "d" / "e" / "k.txt").touch()
                    (workdir / "foo").mkdir(parents=True)
                    (workdir / "foo" / "bar.txt").touch()

                    cleaner.unregister(workdir / "a" / "b" / "c" / "z.txt")
                    cleaner.unregister("foo/bar.txt")
            """,
        },
    )
    def test_cleanup_unregister(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Removing out/DUMMY/runner/a/b/y.txt",
            "Removing out/DUMMY/runner/a/x.txt",
            "Removing out/DUMMY/runner/a/d",
        )
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def a(workdir, cleaner, **_):
                    cleaner.register("/tmp/NON_ROOT")
                    cleaner.register("/tmp/ALSO_NON_ROOT", ignore_outside_root=True)
            """,
        }
    )
    def test_cleanup_deferred_non_root(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Deferred cleaner does not support registering paths outside the root directory",
            "NON_ROOT outside out/DUMMY",
            "Removing out/DUMMY",
        )
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner, pre_hook

                @runner()
                def a(**_):
                    ...

                @pre_hook()
                def h(cleaner,workdir, **_):
                    cleaner.register("/tmp/NON_ROOT")
                    cleaner.unregister("/tmp/NON_ROOT")
                    abs_parent = workdir.parent.absolute()
                    (abs_parent / "EXISTS").touch()
                    cleaner.register(abs_parent / "EXISTS", ignore_outside_root=True)
                    cleaner.register(abs_parent / "DOES_NOT_EXIST", ignore_outside_root=True)
            """,
        },
    )
    def test_cleanup_non_root(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "NON_ROOT outside out/DUMMY",
            "Cleaning up 3 files and 1 directory",
            "Removing 2 paths outside out/DUMMY",
            "out/DOES_NOT_EXIST does not exist",
            "Removing out/DUMMY",
            "Removing path outside out/DUMMY",
        )
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner(cleaner, **_):
                    cleaner.clean()
            """,
        },
    )
    def test_cleanup_deferred_clean(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("Deferred cleaner does not support cleaning")
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner

                @runner()
                def runner(cleaner, **_):
                    ...
            """,
        },
        mocks={
            "cellophane.cleanup.cleanup.rmtree": {"side_effect": Exception("DUMMY")}
        },
    )
    def test_cleanup_removal_exception(self, invocation: Invocation) -> None:
        assert invocation.logs == literal("out/DUMMY: Exception('DUMMY')")
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "modules/a.py": """
                from cellophane import runner
                from cellophane.cleanup import DeferredCall

                @runner()
                def runner(cleaner, workdir, **_):
                    cleaner.calls.append(DeferredCall("DUMMY", workdir / "DUMMY"))
            """,
        },
    )
    def test_cleanup_deferred_invalid_call(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "Unhandled exception when merging cleaners: ValueError('Invalid deferred action: DUMMY')"
        )
        assert invocation.exit_code == 0
