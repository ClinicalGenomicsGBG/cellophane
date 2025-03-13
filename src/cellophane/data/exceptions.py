"""Exceptions for the data module"""


class MergeSamplesTypeError(Exception):
    """Raised when trying to merge samples of different types"""

    def __init__(self, msg: str = "Cannot merge samples of different types"):
        self.msg = msg
        super().__init__(self.msg)


class MergeSamplesUUIDError(Exception):
    """Raised when trying to merge samples with different UUIDs"""

    def __init__(self, msg: str = "Cannot merge samples with different UUIDs"):
        self.msg = msg
        super().__init__(self.msg)
