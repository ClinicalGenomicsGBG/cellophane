from time import gmtime, localtime, strftime, struct_time, time

from attrs import define, field


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