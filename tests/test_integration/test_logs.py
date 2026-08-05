from cellophane.testing import BaseTest, Invocation, literal
from pytest import mark

class Test_logs(BaseTest):
    args = ["--workdir out"]

    @mark.override(
        structure={
            "modules/a.py": """
                from cellophane import pre_hook
                from warnings import warn

                @pre_hook()
                def test_warning(samples, logger, **_):
                    warn("USER WARNING")
                    warn("DEPRECATION WARNING", DeprecationWarning)
            """,
        }
    )
    def test_module_handle_warnings(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "USER WARNING",
            "DEPRECATION WARNING",
        )
