import logging
from pathlib import Path

from cellophane.src import logs


class Test_logs:
    @staticmethod
    def test_logs(tmp_path: Path):
        console_handler = logs.setup_logging()
        console_handler.setLevel(logging.CRITICAL)
        logger = logging.LoggerAdapter(logging.getLogger(), {"label": "DUMMY"})

        _path = tmp_path / "test.log"
        logs.add_file_handler(logger, _path)

        logger.info("TEST")
        assert _path.exists()
        assert any(
            isinstance(_handler, logging.FileHandler)
            and _handler.baseFilename == str(_path)
            for _handler in logger.logger.handlers
        )
        assert "TEST" in _path.read_text()
