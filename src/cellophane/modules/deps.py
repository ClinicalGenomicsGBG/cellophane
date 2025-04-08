
from enum import Flag, auto


class _internal(Flag):
    """Enum for hook dependencies."""
    # Internal flags, not to be used directly
    BEFORE_ALL = auto()
    AFTER_ALL = auto()
    PRE = auto()
    POST = auto()

    # Flag for running before/after all hooks
    ALL = auto()
    # Samples
    SAMPLES_PRESENT = auto()
    SAMPLES_FINALIZED = auto()
    # Files
    FILES_PRESENT = auto()
    FILES_FINALIZED = auto()
    # Outputs
    OUTPUT_PRESENT = auto()
    OUTPUT_FINALIZED = auto()
    OUTPUT_TRANSFERED = auto()
    # Notifications
    NOTIFICATIONS_FINALIZED = auto()
    NOTIFICATIONS_SENT = auto()

    @classmethod
    def order(cls) -> dict["DEPENDENCY", set["DEPENDENCY"]]:
        return {
            # Pre hook order (Samples > Notifications > Files > Outputs)
            cls.PRE | cls.SAMPLES_PRESENT: {cls.PRE | cls.BEFORE_ALL},
            cls.PRE | cls.SAMPLES_FINALIZED: {cls.PRE | cls.SAMPLES_PRESENT},
            cls.PRE | cls.NOTIFICATIONS_FINALIZED: {cls.PRE | cls.SAMPLES_FINALIZED},
            cls.PRE | cls.NOTIFICATIONS_SENT: {cls.PRE | cls.NOTIFICATIONS_FINALIZED},
            cls.PRE | cls.FILES_PRESENT: {cls.PRE | cls.NOTIFICATIONS_SENT},
            cls.PRE | cls.FILES_FINALIZED: {cls.PRE | cls.FILES_PRESENT},
            cls.PRE | cls.OUTPUT_PRESENT: {cls.PRE | cls.FILES_FINALIZED},
            cls.PRE | cls.OUTPUT_FINALIZED: {cls.PRE | cls.OUTPUT_PRESENT},
            cls.PRE | cls.AFTER_ALL: {cls.PRE | cls.OUTPUT_FINALIZED},
            # Post hook order (Samples (finalized) > Outputs > Notifications)
            cls.POST | cls.SAMPLES_FINALIZED: {cls.POST | cls.BEFORE_ALL},
            cls.POST | cls.OUTPUT_PRESENT: {cls.POST | cls.SAMPLES_FINALIZED},
            cls.POST | cls.OUTPUT_FINALIZED: {cls.POST | cls.OUTPUT_PRESENT},
            cls.POST | cls.OUTPUT_TRANSFERED: {cls.POST | cls.OUTPUT_FINALIZED},
            cls.POST | cls.NOTIFICATIONS_FINALIZED: {cls.POST | cls.OUTPUT_TRANSFERED},
            cls.POST | cls.NOTIFICATIONS_SENT: {cls.POST | cls.NOTIFICATIONS_FINALIZED},
            cls.POST | cls.AFTER_ALL: {cls.POST | cls.NOTIFICATIONS_SENT},
        }

    def __or__(self, other: "_internal") -> "_internal":
        """Override the | operator to combine flags."""
        if not {self, other} & {_internal.PRE, _internal.POST}:
            raise ValueError("Can only combine flags with PRE or POST")

        if {self, other} == {_internal.PRE, _internal.POST}:
            raise ValueError("Cannot combine PRE and POST flags")

        if {self, other} in (
            {_internal.PRE, _internal.OUTPUT_TRANSFERED},
        ):
            raise ValueError("Pre-hooks cannot depend on OUTPUT_TRANSFERED stage")

        if {self, other} in (
            {_internal.POST, _internal.SAMPLES_PRESENT},
            {_internal.POST, _internal.FILES_PRESENT},
            {_internal.POST, _internal.FILES_FINALIZED},
        ):
            raise ValueError(f"Post-hooks cannot depend on SAMPLES_PRESENT or FILES_* stages: {self!r}")

        return super().__or__(other)

    def __repr__(self) -> str:
        """Override the __repr__ method to return the name of the flag."""
        return self._name_  # type: ignore[return-value]

DEPENDENCY = str | _internal

class stage:
    ALL = _internal.ALL
    SAMPLES_PRESENT = _internal.SAMPLES_PRESENT
    SAMPLES_FINALIZED = _internal.SAMPLES_FINALIZED
    FILES_PRESENT = _internal.FILES_PRESENT
    FILES_FINALIZED = _internal.FILES_FINALIZED
    OUTPUT_PRESENT = _internal.OUTPUT_PRESENT
    OUTPUT_FINALIZED = _internal.OUTPUT_FINALIZED
    OUTPUT_TRANSFERED = _internal.OUTPUT_TRANSFERED
    NOTIFICATIONS_FINALIZED = _internal.NOTIFICATIONS_FINALIZED
    NOTIFICATIONS_SENT = _internal.NOTIFICATIONS_SENT