import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union


class PathDict(dict):
    def __init__(self, arg: Optional[Union[Mapping, Iterable]] = None, **kwargs: Any):
        if isinstance(arg, Mapping):
            return self.__class__.__init__(self, **arg, **kwargs)
        elif isinstance(arg, Iterable):
            return self.__class__.__init__(self, **dict(arg), **kwargs)

        super().__init__()
        self.update(kwargs)

    def __setitem__(self, key: str, value: Any) -> None:
        _value = PathDict(value) if isinstance(value, Mapping) else value
        _key = key.strip("/")
        if "/" in _key:
            parent, child = _key.rsplit("/", 1)
            self[parent] = {child: _value}
        elif _key in self and isinstance(self[_key], Mapping):
            self[_key].update(_value)
        else:
            super().__setitem__(_key, _value)

    def __getitem__(self, key: str) -> Any:
        _key = key.strip("/")
        if "/" in _key:
            parent, child = _key.rsplit("/", 1)
            return self[parent][child]
        return super().__getitem__(_key)

    def update(self, other: dict | Iterable[tuple[Any, Any]], /, **kwargs: Any) -> None:  # type: ignore[override]
        for key, value in (dict(other) | kwargs).items():
            self[key] = value


class regex:
    patterns: list[re.Pattern]

    def __init__(
        self,
        *patterns: str | tuple[str, int] | re.Pattern,
        flags: int = 0,
    ):
        self.patterns = []
        for pattern in patterns:
            match pattern:
                case str(p):
                    self.patterns.append(re.compile(p, flags))
                case (str(p), int(f_)):
                    self.patterns.append(re.compile(p, flags | f_))
                case (str(p),):
                    self.patterns.append(re.compile(p, flags))
                case re.Pattern:
                    self.patterns.append(pattern)
                case _:
                    raise ValueError(f"Invalid pattern {pattern}")

    def __contains__(self, other: Union[str, bytes]) -> bool:
        return self == other

    def __eq__(self, other: Union[str, Path, Iterable]) -> bool:  # type: ignore[override]
        if isinstance(other, Path):
            if not other.is_file():
                raise ValueError("Path must be a file")
            return other.read_text() == self
        elif isinstance(other, Iterable) and not isinstance(other, str):
            return self == "\n".join(other)
        elif not isinstance(other, str):
            return self == repr(other)

        return all(pattern.search(other) is not None for pattern in self.patterns)

    def __ne__(self, other: Union[str, Path]) -> bool:  # type: ignore[override]
        if isinstance(other, Path):
            if not other.is_file():
                raise ValueError("Path must be a file")
            return other.read_text() != self
        elif isinstance(other, Iterable) and not isinstance(other, str):
            return self != "\n".join(other)
        elif not isinstance(other, str):
            return self != repr(other)

        return any(pattern.search(other) is None for pattern in self.patterns)


class literal(regex):
    def __init__(self, *patterns: str | tuple[str, int], flags: int = 0):
        escaped_patterns: list[str | tuple[str, int]] = []
        for pattern in patterns:
            match pattern:
                case str(p):
                    escaped_patterns.append(re.escape(p))
                case (str(p), int(f_)):
                    escaped_patterns.append((re.escape(p), f_))
                case (str(p),):
                    escaped_patterns.append(re.escape(p))
                case _:
                    raise ValueError(f"Invalid pattern {pattern}")
        super().__init__(*escaped_patterns, flags=flags)
