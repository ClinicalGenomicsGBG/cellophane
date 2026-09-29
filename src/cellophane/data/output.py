"""Outut classes for copying files to another directory."""
from __future__ import annotations

from collections.abc import Iterable
from copy import copy
from glob import glob
from pathlib import Path
from typing import TYPE_CHECKING
from warnings import warn

from attrs import define, field
from attrs.setters import convert
from cellophane.data import Container

if TYPE_CHECKING:
    from collections.abc import Iterator
    from collections.abc import Set as AbstractSet
    from typing import Any

    from cellophane.cfg import Config
    from cellophane.util import Timestamp


@define
class Output:
    """Output file to be copied to the another directory."""

    src: Path = field(
        kw_only=True,
        converter=Path,
        on_setattr=convert,
    )
    dst: Path = field(
        kw_only=True,
        converter=Path,
        on_setattr=convert,
    )
    checkpoint: str = field(
        default="main",
        kw_only=True,
        converter=str,
        on_setattr=convert,
    )
    optional: bool = field(
        default=False,
        kw_only=True,
        converter=bool,
        on_setattr=convert,
    )
    metadata: Container = field(
        kw_only=True,
        factory=Container,
        converter=Container,
        on_setattr=convert,
    )

    def __hash__(self) -> int:
        return hash((self.src, self.dst))


@define
class OutputGlob:
    """Output glob find files to be copied to the another directory."""

    src: str = field(
        converter=str,
        on_setattr=convert,
    )
    dst_dir: str | None = field(
        default=None,
        kw_only=True,
        converter=lambda v: v if v is None else str(v),
        on_setattr=convert,
    )
    dst_name: str | None = field(
        default=None,
        kw_only=True,
        converter=lambda v: v if v is None else str(v),
        on_setattr=convert,
    )
    workdir: Path | None = field(
        default=None,
        kw_only=True,
        converter=lambda v: v if v is None else Path(v),
        on_setattr=convert,
    )
    config: Config | None = field(
        default=None,
        kw_only=True,
        on_setattr=convert,
    )
    timestamp: Timestamp | None = field(
        default=None,
        kw_only=True,
        on_setattr=convert,
    )
    checkpoint: str = field(
        default="main",
        kw_only=True,
        converter=str,
        on_setattr=convert,
    )
    optional: bool = field(
        default=False,
        kw_only=True,
        converter=bool,
        on_setattr=convert,
    )
    metadata: dict = field(
        kw_only=True,
        factory=dict,
        converter=dict,
        on_setattr=convert,
    )
    _resolved: set[Output] | None = field(
        init=False,
        kw_only=True,
        default=None,
        converter=lambda v: v if v is None else set(v),
        on_setattr=convert,
    )

    def __hash__(self) -> int:
        return hash((self.src, self.dst_dir, self.dst_name))

    def clear_cache(self) -> None:
        self._resolved = None

    def resolve(
        self,
        samples: Iterable,
        cache: bool = True,
    ) -> set[Output]:
        """Resolve the glob pattern to a list of files to be copied.

        Args:
        ----
            samples (Iterable): The samples being processed.
            _warnings (bool): Whether to display warnings.

        Returns:
        -------
            set[Output]: The list of files to be copied.

        """
        if not cache:
            self.clear_cache()
        elif self._resolved is not None:
            return self._resolved

        self._resolved = set()

        if self.workdir is None:
            raise ValueError("OutputGlob without workdir cannot be resolved")
        if self.config is None:
            raise ValueError("OutputGlob without config cannot be resolved")
        if self.timestamp is None:
            raise ValueError("OutputGlob without timestamp cannot be resolved")


        for sample in samples:
            meta = {
                "samples": samples,
                "config": self.config,
                "workdir": self.workdir,
                "sample": sample,
                "timestamp": self.timestamp,
            }

            match self.src.format(**meta):
                case p if Path(p).is_absolute():
                    pattern = p
                case p if Path(p).is_relative_to(self.workdir):
                    pattern = p
                case p:
                    pattern = str(self.workdir / p)

            matches = [Path(m) for m in glob(pattern)]
            if not matches and not self.optional:
                warn(f"No files matched pattern '{pattern}'")

            for m in matches:
                match self.dst_dir:
                    case str(d) if Path(d).is_absolute():
                        dst_dir = Path(d.format(**meta))
                    case str(d):
                        dst_dir = self.config.resultdir / d.format(**meta)
                    case _:
                        dst_dir = self.config.resultdir

                match self.dst_name:
                    case None:
                        dst_name = m.name
                    case _ if len(matches) > 1:
                        dst_name = m.name
                        warn(
                            f"Destination name {self.dst_name} will be ignored "
                            f"as '{self.src}' matches multiple files"
                        )
                    case str() as n:
                        dst_name = n.format(**meta)

                dst = Path(dst_dir) / dst_name

                self._resolved.add(
                    Output(
                        src=m,
                        dst=dst,
                        optional=self.optional,
                        checkpoint=self.checkpoint.format(**meta),
                        metadata=self.metadata,
                    ),
                )

        return self._resolved


class ResolvedOutputs(set[Output | OutputGlob]):
    """A set of outputs and output globs whose globs are resolved on read.

    Args:
        owner: The owner of this set of outputs.
        items: An iterable of outputs and output globs to initialize the set with.
    """

    def __init__(self, owner: Any, items: Iterable[Output | OutputGlob] = ()) -> None:
        self._owner = owner
        super().__init__(items)

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (None,), {"owner": self._owner, "items": self.raw})

    def __setstate__(self, state: dict[str, Any]) -> None:
        self._owner = state["owner"]
        self.update(state["items"])

    @staticmethod
    def _convert(value: Any, instance: Any) -> ResolvedOutputs:
        if isinstance(value, ResolvedOutputs):
            if value._owner is instance:
                return value
            value = value.raw
        elif isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            raise TypeError(f"Cannot convert {value!r} to ResolvedOutputs")
        return ResolvedOutputs(instance, value)

    def _resolve(self) -> set[Output]:
        resolved: set[Output] = set()
        for item in self._iter_raw():
            if isinstance(item, OutputGlob):
                resolved |= item.resolve(self._owner)
            else:
                resolved.add(item)
        return resolved

    def _iter_raw(self) -> Iterator[Output | OutputGlob]:
        return super().__iter__()

    def _wrap(self, result: Any) -> ResolvedOutputs:
        if result is NotImplemented:  # set's operators return it for non-set operands
            return NotImplemented  # type: ignore[no-any-return]
        return type(self)(self._owner, result)

    @property
    def raw(self) -> set[Output | OutputGlob]:
        return set(self._iter_raw())

    def fill(self, workdir: Path, config: Config, timestamp: Timestamp) -> None:
        items: list[Output | OutputGlob] = []
        for item in self._iter_raw():
            if not isinstance(item, OutputGlob):
                items.append(item)
                continue
            glob = copy(item)
            if glob.workdir is None:
                glob.workdir = workdir
            if glob.config is None:
                glob.config = config
            if glob.timestamp is None:
                glob.timestamp = timestamp
            items.append(glob)
        self.clear()
        self.update(items)

    def clear_cache(self) -> None:
        for item in self._iter_raw():
            if isinstance(item, OutputGlob):
                item.clear_cache()

    def __iter__(self) -> Iterator[Output]:
        return iter(self._resolve())

    def __len__(self) -> int:
        return len(self._resolve())

    def __bool__(self) -> bool:
        globs: list[OutputGlob] = []
        for item in self._iter_raw():
            if not isinstance(item, OutputGlob):
                return True
            globs.append(item)
        return any(glob.resolve(self._owner) for glob in globs)

    def __contains__(self, elem: object) -> bool:
        if not isinstance(elem, OutputGlob) and super().__contains__(elem):
            return True
        return elem in self._resolve()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.raw!r})"

    def union(self, *others: Iterable[Output | OutputGlob]) -> ResolvedOutputs:
        return self._wrap(super().union(*others))

    def intersection(self, *others: Iterable[Any]) -> ResolvedOutputs:
        return self._wrap(super().intersection(*others))

    def difference(self, *others: Iterable[Any]) -> ResolvedOutputs:
        return self._wrap(super().difference(*others))

    def symmetric_difference(self, other: Iterable[Output | OutputGlob]) -> ResolvedOutputs:
        return self._wrap(super().symmetric_difference(other))

    def copy(self) -> ResolvedOutputs:
        return self._wrap(super().copy())

    def __or__(self, other: AbstractSet[Output | OutputGlob]) -> ResolvedOutputs:
        return self._wrap(super().__or__(other))

    def __and__(self, other: AbstractSet[Any]) -> ResolvedOutputs:
        return self._wrap(super().__and__(other))

    def __sub__(self, other: AbstractSet[Any]) -> ResolvedOutputs:
        return self._wrap(super().__sub__(other))

    def __xor__(self, other: AbstractSet[Output | OutputGlob]) -> ResolvedOutputs:
        return self._wrap(super().__xor__(other))

    def __rsub__(self, other: AbstractSet[Output | OutputGlob]) -> ResolvedOutputs:
        if not isinstance(other, set):
            return NotImplemented
        return self._wrap(other.difference(self))

    __ror__ = __or__
    __rand__ = __and__
    __rxor__ = __xor__

