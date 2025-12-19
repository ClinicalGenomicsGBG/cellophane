from __future__ import annotations

from time import gmtime, localtime, strftime, time
from typing import TYPE_CHECKING

from attrs import define, field

if TYPE_CHECKING:
    from time import struct_time

@define(frozen=True)
class Timestamp:
    time: float = field(factory=time)

    @property
    def gmtime(self) -> struct_time:
        return gmtime(self.time)

    @property
    def localtime(self) -> struct_time:
        return localtime(self.time)


    def __getitem__(self, key: str) -> str:
        return strftime(key, self.localtime)

    def __str__(self) -> str:
        return self['%y%m%d-%H%M%S']

    def __float__(self) -> float:
        return self.time

    def __int__(self) -> int:
        return int(self.time)

    def __sub__(self, other: int | float) -> float:
        if not isinstance(other, (int, float)):
            raise NotImplementedError

        return self.time - other

    def __rsub__(self, other: int | float) -> float:
        if not isinstance(other, (int, float)):
            raise NotImplementedError

        return other - self.time