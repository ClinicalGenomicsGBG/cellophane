"""Exceptions for the data module"""

class MergeSamplesError(Exception):
    """General exception for errors when merging samples"""

    def __init__(self, msg: str = "Error when merging samples"):
        self.msg = msg
        super().__init__(self.msg)

class MergeSamplesTypeError(MergeSamplesError):
    """Raised when trying to merge samples of different types"""

    def __init__(self, msg: str = "Cannot merge samples of different types"):
        self.msg = msg
        super().__init__(self.msg)


class MergeSamplesUUIDError(MergeSamplesError):
    """Raised when trying to merge samples with different UUIDs"""

    def __init__(self, msg: str = "Cannot merge samples with different UUIDs"):
        self.msg = msg
        super().__init__(self.msg)
