from enum import Flag, auto
from functools import cache
from cellophane.data import Container
from typing import Optional

class _flag(Flag):
    """Enum for hook dependencies."""

    # Internal flags, not to be used directly
    BEFORE = auto()
    AFTER = auto()
    PRE = auto()
    POST = auto()
    ACTION = auto()

    # Flags for hook actions
    ADDS_SAMPLES = auto()
    REMOVES_SAMPLES = auto()
    MODIFIES_SAMPLES = auto()
    ADDS_FILES = auto()
    REMOVES_FILES = auto()
    MODIFIES_FILES = auto()
    ADDS_OUTPUTS = auto()
    REMOVES_OUTPUTS = auto()
    MODIFIES_OUTPUTS = auto()
    TRANSFERS_OUTPUTS = auto()
    MODIFIES_NOTIFICATIONS = auto()
    SENDS_NOTIFICATIONS = auto()

    # Flag for hook staging
    ALL = auto()
    SAMPLES_INIT = auto()
    FILES_INIT = auto()
    OUTPUT_INIT = auto()
    OUTPUT_TRANSFERED = auto()
    NOTIFICATIONS_INIT = auto()
    NOTIFICATIONS_SENT = auto()

    @classmethod
    def order(cls) -> dict["_flag", Optional["_flag"]]:
        return {
            # Pre-hook order
            cls.PRE | cls.BEFORE | cls.ALL: None,
            # Samples
            cls.PRE | cls.BEFORE | cls.SAMPLES_INIT: cls.PRE | cls.BEFORE | cls.ALL,
            cls.PRE | cls.ACTION | cls.ADDS_SAMPLES: cls.PRE | cls.BEFORE | cls.SAMPLES_INIT,
            cls.PRE | cls.ACTION | cls.REMOVES_SAMPLES: cls.PRE | cls.ACTION | cls.ADDS_SAMPLES,
            cls.PRE | cls.ACTION | cls.MODIFIES_SAMPLES: cls.PRE | cls.ACTION | cls.REMOVES_SAMPLES,
            cls.PRE | cls.AFTER | cls.SAMPLES_INIT: cls.PRE | cls.ACTION | cls.MODIFIES_SAMPLES,
            # Notifications init
            cls.PRE | cls.BEFORE | cls.NOTIFICATIONS_INIT: cls.PRE | cls.AFTER | cls.SAMPLES_INIT,
            cls.PRE | cls.ACTION | cls.MODIFIES_NOTIFICATIONS: cls.PRE | cls.BEFORE | cls.NOTIFICATIONS_INIT,
            cls.PRE | cls.AFTER | cls.NOTIFICATIONS_INIT: cls.PRE | cls.ACTION | cls.MODIFIES_NOTIFICATIONS,
            # Notifications send
            cls.PRE | cls.BEFORE | cls.NOTIFICATIONS_SENT: cls.PRE | cls.AFTER | cls.NOTIFICATIONS_INIT,
            cls.PRE | cls.ACTION | cls.SENDS_NOTIFICATIONS: cls.PRE | cls.BEFORE | cls.NOTIFICATIONS_SENT,
            cls.PRE | cls.AFTER | cls.NOTIFICATIONS_SENT: cls.PRE | cls.ACTION | cls.SENDS_NOTIFICATIONS,
            # Files
            cls.PRE | cls.BEFORE | cls.FILES_INIT: cls.PRE | cls.AFTER | cls.NOTIFICATIONS_SENT,
            cls.PRE | cls.ACTION | cls.ADDS_FILES: cls.PRE | cls.BEFORE | cls.FILES_INIT,
            cls.PRE | cls.ACTION | cls.REMOVES_FILES: cls.PRE | cls.ACTION | cls.ADDS_FILES,
            cls.PRE | cls.ACTION | cls.MODIFIES_FILES: cls.PRE | cls.ACTION | cls.REMOVES_FILES,
            cls.PRE | cls.AFTER | cls.FILES_INIT: cls.PRE | cls.ACTION | cls.MODIFIES_FILES,
            # Outputs
            cls.PRE | cls.BEFORE | cls.OUTPUT_INIT: cls.PRE | cls.AFTER | cls.FILES_INIT,
            cls.PRE | cls.ACTION | cls.ADDS_OUTPUTS: cls.PRE | cls.BEFORE | cls.OUTPUT_INIT,
            cls.PRE | cls.ACTION | cls.REMOVES_OUTPUTS: cls.PRE | cls.ACTION | cls.ADDS_OUTPUTS,
            cls.PRE | cls.ACTION | cls.MODIFIES_OUTPUTS: cls.PRE | cls.ACTION | cls.REMOVES_OUTPUTS,
            cls.PRE | cls.AFTER | cls.OUTPUT_INIT: cls.PRE | cls.ACTION | cls.MODIFIES_OUTPUTS,
            # After All
            cls.PRE | cls.AFTER | cls.ALL: cls.PRE | cls.AFTER | cls.OUTPUT_INIT,

            # Post-hook order
            cls.POST | cls.BEFORE | cls.ALL: None,
            # Output init
            cls.POST | cls.BEFORE | cls.OUTPUT_INIT: cls.POST | cls.BEFORE | cls.ALL,
            cls.POST | cls.ACTION | cls.ADDS_OUTPUTS: cls.POST | cls.BEFORE | cls.OUTPUT_INIT,
            cls.POST | cls.ACTION | cls.REMOVES_OUTPUTS: cls.POST | cls.ACTION | cls.ADDS_OUTPUTS,
            cls.POST | cls.ACTION | cls.MODIFIES_OUTPUTS: cls.POST | cls.ACTION | cls.REMOVES_OUTPUTS,
            cls.POST | cls.AFTER | cls.OUTPUT_INIT: cls.POST | cls.ACTION | cls.MODIFIES_OUTPUTS,
            # Output transfer
            cls.POST | cls.BEFORE | cls.OUTPUT_TRANSFERED: cls.POST | cls.AFTER | cls.OUTPUT_INIT,
            cls.POST | cls.ACTION | cls.TRANSFERS_OUTPUTS: cls.POST | cls.BEFORE | cls.OUTPUT_TRANSFERED,
            cls.POST | cls.AFTER | cls.OUTPUT_TRANSFERED: cls.POST | cls.ACTION | cls.TRANSFERS_OUTPUTS,
            # Notifications init
            cls.POST | cls.BEFORE | cls.NOTIFICATIONS_INIT: cls.POST | cls.AFTER | cls.OUTPUT_TRANSFERED,
            cls.POST | cls.ACTION | cls.MODIFIES_NOTIFICATIONS: cls.POST | cls.BEFORE | cls.NOTIFICATIONS_INIT,
            cls.POST | cls.AFTER | cls.NOTIFICATIONS_INIT: cls.POST | cls.ACTION | cls.MODIFIES_NOTIFICATIONS,
            # Notifications send
            cls.POST | cls.BEFORE | cls.NOTIFICATIONS_SENT: cls.POST | cls.AFTER | cls.NOTIFICATIONS_INIT,
            cls.POST | cls.ACTION | cls.SENDS_NOTIFICATIONS: cls.POST | cls.BEFORE | cls.NOTIFICATIONS_SENT,
            cls.POST | cls.AFTER | cls.NOTIFICATIONS_SENT: cls.POST | cls.ACTION | cls.SENDS_NOTIFICATIONS,
            # After All
            cls.POST | cls.AFTER | cls.ALL: cls.POST | cls.AFTER | cls.NOTIFICATIONS_SENT,
        }

    @classmethod
    def inverse_order(cls) -> dict["_flag", "_flag"]:
        return {v: k for k, v in cls.order().items() if v is not None}

    @classmethod
    def graph(cls) -> dict["_flag", set["_flag"]]:
        return {k: {v} for k, v in cls.order().items() if v is not None}

    def next(self, exclude_actions: bool = True) -> "_flag":
        """Return the next flags in the order."""
        cls = self.__class__
        _phase = cls.PRE & self or cls.POST & self
        _next = self.inverse_order().get(self) or _phase | cls.AFTER | cls.ALL
        while cls.ACTION in _next and exclude_actions:
            _next = self.inverse_order().get(_next) or _phase | cls.AFTER | cls.ALL
        return _next

    def previous(self: "_flag", exclude_actions: bool = True) -> "_flag":
        """Return the previous flags in the order."""
        cls = self.__class__
        _phase = cls.PRE & self or cls.POST & self
        _previous = self.order().get(self) or _phase | cls.BEFORE | cls.ALL
        while cls.ACTION in _previous and exclude_actions:
            _previous = self.order().get(_previous) or _phase | cls.BEFORE | cls.ALL
        return _previous

    @cache
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, _flag):
            return NotImplemented
        if {self, other} - {*self.order()}:
            raise ValueError(f"Cannot determine the order of {self} and {other}")

        return [*self.order()].index(self) < [*self.order()].index(other)

    @cache
    def __gt__(self, other: object) -> bool:
        if not isinstance(other, _flag):
            return NotImplemented
        if {self, other} - {*self.order()}:
            raise ValueError(f"Cannot determine the order of {self} and {other}")
        return [*self.order()].index(self) > [*self.order()].index(other)


    def __repr__(self) -> str:
        """Override the __repr__ method to return the name of the flag."""
        return self._name_  # type: ignore[return-value]


DEPENDENCY = str | _flag

stage: Container = Container(
    ALL=_flag.ALL,
    SAMPLES_INIT=_flag.SAMPLES_INIT,
    FILES_INIT=_flag.FILES_INIT,
    OUTPUT_INIT=_flag.OUTPUT_INIT,
    OUTPUT_TRANSFERED=_flag.OUTPUT_TRANSFERED,
    NOTIFICATIONS_INIT=_flag.NOTIFICATIONS_INIT,
    NOTIFICATIONS_SENT=_flag.NOTIFICATIONS_SENT,
)

action = Container(
    ADDS_SAMPLES=_flag.ADDS_SAMPLES,
    REMOVES_SAMPLES=_flag.REMOVES_SAMPLES,
    MODIFIES_SAMPLES=_flag.MODIFIES_SAMPLES,
    ADDS_FILES=_flag.ADDS_FILES,
    REMOVES_FILES=_flag.REMOVES_FILES,
    MODIFIES_FILES=_flag.MODIFIES_FILES,
    ADDS_OUTPUTS=_flag.ADDS_OUTPUTS,
    REMOVES_OUTPUTS=_flag.REMOVES_OUTPUTS,
    MODIFIES_OUTPUTS=_flag.MODIFIES_OUTPUTS,
    TRANSFERS_OUTPUTS=_flag.TRANSFERS_OUTPUTS,
    MODIFIES_NOTIFICATIONS=_flag.MODIFIES_NOTIFICATIONS,
    SENDS_NOTIFICATIONS=_flag.SENDS_NOTIFICATIONS,
)


# hook_x before="NOTIFICATIONS_SENT"
