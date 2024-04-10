"""Sample and Samples class definitions."""

from collections import UserList
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar, Iterable, Literal, Sequence, TypeVar, overload
from uuid import UUID, uuid4

from attrs import define, field, fields_dict, has, make_class
from attrs.setters import convert, frozen
from ruamel.yaml import YAML

from .. import util
from .container import Container
from .exceptions import MergeSamplesTypeError, MergeSamplesUUIDError
from .merger import Merger
from .output import Output, OutputGlob
from .util import convert_path_list


class _BASE:
    """Dummy base class for adding mixins to the Sample and Samples classes."""

@overload
def _apply_mixins(
    cls: type["Samples"],
    base: type,
    mixins: Sequence[type["Samples"]],
) -> type["Samples"]:
    pass  # pragma: no cover


@overload
def _apply_mixins(
    cls: type["Sample"],
    base: type,
    mixins: Sequence[type["Sample"]],
) -> type["Sample"]:
    pass  # pragma: no cover


def _apply_mixins(
    cls: type, base: type, mixins: Sequence[type], name: str | None = None
) -> type:
    _name = cls.__name__
    for m in mixins:
        if getattr(m, "__slots__", None):
            raise TypeError(
                f"{m.__name__}: Mixins must not have __slots__ "
                "(use @define(slots=False) and don't set __slots__ in the class body)"
            )
        _name += f"_{m.__name__}"
        m.__bases__ = (base,)
        m.__module__ = "__main__"
        if not has(m):
            m = define(m, slots=False)

    _cls = make_class(name or _name, (), (cls, *mixins), slots=False)
    _cls.__module__ = "__main__"

    return _cls


S = TypeVar("S", bound="Sample")


@define(slots=False)
class Sample(_BASE):  # type: ignore[no-untyped-def]
    """
    Base sample class represents a sample with an ID, a list of files, a flag indicating
    if it's done, and a list of Output objects.
    Can be subclassed in a module to add additional functionality (mixin).

    Attributes:
        id (str): The ID of the sample.
        files (list[str]): The list of files associated with the sample.
        done (bool | None): The flag indicating if the sample is done. Defaults to None.
        output (list[Output]): The list of Output objects associated with the sample.

    Methods:
        with_mixins(mixins): Returns a new Sample class with the specified mixins
            applied.
    """

    id: str = field(kw_only=True)
    files: list[Path] = field(
        factory=list,
        converter=convert_path_list,
        on_setattr=convert,
    )
    processed: bool = False
    uuid: UUID = field(
        repr=False,
        factory=uuid4,
        init=False,
        on_setattr=frozen,
    )
    meta: Container = field(
        factory=Container,
        converter=Container,
        on_setattr=convert,
    )
    _fail: str | None = field(default=None, repr=False)
    merge: ClassVar[Merger] = Merger()

    def __str__(self) -> str:
        return self.id

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in fields_dict(self.__class__):
            setattr(self, key, value)
        else:
            raise KeyError(f"Sample has no attribute '{key}'")

    @merge.register("files")
    @staticmethod
    def _merge_files(this: list[Path], that: list[Path]) -> list[Path]:
        return [*dict.fromkeys((*this, *that))]

    @merge.register("meta")
    @staticmethod
    def _merge_meta(this: set[str], that: set[str]) -> Container:
        return Container(util.merge_mappings(this, that))

    @merge.register("_fail")
    @staticmethod
    def _merge_fail(this: str | None, that: str | None) -> str | None:
        return f"{this}\n{that}" if this and that else this or that

    @merge.register("processed")
    @staticmethod
    def _merge_done(this: bool | None, that: bool | None) -> bool | None:
        return this and that

    def __and__(self, other: "Sample") -> "Sample":
        if self.__class__ != other.__class__:
            raise MergeSamplesTypeError

        if self.uuid != other.uuid:
            raise MergeSamplesUUIDError

        _sample = deepcopy(self)
        for _field in (
            f for f in fields_dict(self.__class__) if f not in ["id", "uuid"]
        ):
            setattr(
                _sample,
                _field,
                self.merge(
                    _field,
                    self.__getattribute__(_field),
                    other.__getattribute__(_field),
                ),
            )
        return _sample

    def fail(self, reason: str) -> None:
        """
        Marks the sample as failed with the specified reason.
        """
        self._fail = reason

    @property
    def failed(self) -> str | Literal[False]:
        """
        Checks if the sample is failed by any runner
        """

        return self._fail or (False if self.processed else "Sample was not processed")

    @classmethod
    def with_mixins(cls, mixins: Sequence[type["Sample"]]) -> type["Sample"]:
        """
        Returns a new Sample class with the specified mixins as base classes.

        Internally called by Cellophane with the samples mixins specified
        in the loaded modules. Uses attrs.make_class to create a new class,
        so any attrs decorators in the mixins will be applied.

        Args:
            cls (type): The class to apply the mixins to.
            mixins (Iterable[type]): An iterable of mixin classes to apply.

        Returns:
            type: The new class with the mixins applied.
        """
        return _apply_mixins(cls, _BASE, mixins)


@define(slots=False, order=False, init=False)
class Samples(UserList[S]):
    """
    Base samples class represents a list of samples.
    Can be subclassed in a module to add additional functionality (mixin).

    Attributes:
        data (list[Sample]): The list of samples.

    Methods:
        from_file(path: Path): Returns a new Samples object with samples loaded from
            the specified YAML file.
        with_mixins(mixins): Returns a new Samples class with the specified mixins
            applied.
        with_sample_class(sample_class): Returns a new Samples class with the specified
            sample class.

    """

    data: list[S] = field(factory=list)
    sample_class: ClassVar[type[Sample]] = Sample
    merge: ClassVar[Merger] = Merger()
    output: set[Output | OutputGlob] = field(
        factory=set, converter=set, on_setattr=convert
    )

    def __init__(self, data: list | None = None, /, **kwargs: Any) -> None:
        self.__attrs_init__(**kwargs)  # pylint: disable=no-member
        super().__init__(data or [])

    def __getitem__(self, key: int | UUID) -> S:  # type: ignore[override]
        if isinstance(key, int):
            return super().__getitem__(key)

        if isinstance(key, UUID) and key in self:
            return next(s for s in self if s.uuid == key)

        if isinstance(key, UUID):
            raise KeyError(f"Sample with UUID {key.hex} not found")

        raise TypeError(f"Key {key} is not an int or a UUID")

    def __setitem__(self, key: int | UUID, value: S) -> None:  # type: ignore[override]
        if isinstance(key, int):
            super().__setitem__(key, value)
        elif isinstance(key, UUID) and key in self:
            self[self.index(self[key])] = value
        elif isinstance(key, UUID):
            self.append(value)
        else:
            raise TypeError(f"Key {key} is not an int or a UUID")

    def __contains__(self, item: S | UUID) -> bool:  # type: ignore[override]
        if isinstance(item, UUID):
            return any(s.uuid == item for s in self)
        else:
            return super().__contains__(item)

    @merge.register("data")
    @staticmethod
    def _merge_data(this: list[Sample], that: list[Sample]) -> list[Sample]:
        return [
            (
                (a & next(b for b in that if b.uuid == a.uuid))
                if a.uuid in [s.uuid for s in that]
                else a
            )
            for a in this
        ]

    @merge.register("output")
    @staticmethod
    def _merge_output(this: set[Output], that: set[Output]) -> set[Output]:
        return this | that

    @classmethod
    def from_file(cls, path: Path) -> "Samples":
        """Get samples from a YAML file"""
        samples = []
        yaml = YAML(typ="safe")
        for sample in yaml.load(path):
            _id = sample.pop("id")
            samples.append(
                cls.sample_class(id=str(_id), **sample)  # type: ignore[call-arg]
            )
        return cls(samples)

    @classmethod
    def with_mixins(cls, mixins: Sequence[type["Samples"]]) -> type["Samples"]:
        """
        Returns a new Samples class with the specified mixins as base classes.

        Internally called by Cellophane with the samples mixins specified
        in the loaded modules. Uses attrs.make_class to create a new class,
        so any attrs decorators in the mixins will be applied.

        Args:
            cls (type): The class to apply the mixins to.
            mixins (Iterable[type]): An iterable of mixin classes to apply.

        Returns:
            type: The new class with the mixins applied.
        """

        return _apply_mixins(cls, UserList, mixins)

    @classmethod
    def with_sample_class(cls, sample_class: type["Sample"]) -> type["Samples"]:
        """
        Returns a new Samples class with the specified sample class as the
        class to use for samples.

        Internally called by Cellophane with the samples mixins specified
        in the loaded modules.

        Args:
            cls (type): The class to apply the mixins to.
            sample_class (type): The class to use for samples.

        Returns:
            type: The new class with the sample class applied.
        """

        return type(cls.__name__, (cls,), {"sample_class": sample_class})

    def split(self, by: str | None = "uuid") -> Iterable[tuple[Any, "Samples"]]:
        """
        Splits the data into groups based on the specified attribute value.

        Args:
            by (str | None): The attribute to link the samples by.
                Defaults to None, which results in Samples objects with one
                sample each.

        Yields:
            Iterable[tuple[Any, Samples]]: An iterable of tuples containing the
                linked attribute value and a Samples object containing the
                samples with that attribute value.

        Example:
            ```python
            Samples(
                [
                    Sample(id="sample1", files=["file1_1.txt"]),
                    Sample(id="sample1", files=["file1_2.txt"]),
                    Sample(id="sample2", files=["file2.txt"]),
                ]
            )

            # Splitting by the "id" attribute (eg. to merge data from multiple runs)
            for key, samples in data.split(by="id"):
                print(key)
                print(samples)
            # "sample1"
            # Samples(
            #     Sample(id='sample1', files=['file1_1.txt']),
            #     Sample(id='sample1', files=['file1_2.txt'])
            # )
            # "sample2"
            # Samples(Sample(id='sample2', files=['file2.txt']))

            # Splitting without linking (eg. to get individual samples)
            for key, sample in data.split():
                print(sample)
            # UUID('SOME_UUID')
            # Samples(Sample(id='sample1', files=['file1_1.txt']))
            # UUID('OTHER_UUID')
            # Samples(Sample(id='sample1', files=['file1_2.txt']))
            # UUID('THIRD_UUID')
            # Samples(Sample(id='sample2', files=['file2.txt']))
            ```
        """
        if by is None:
            yield None, self
        else:
            yield from {
                sample[by]: self.__class__([li for li in self if li[by] == sample[by]])
                for sample in self
            }.items()

    @property
    def unique_ids(self) -> set[str]:
        """
        Returns a set of unique IDs from the samples in the data.

        Returns:
            set[str]: The set of unique IDs.

        Example:
            ```python
            data = [
                Sample(id="sample1", files=["file1.txt"]),
                Sample(id="sample2", files=["file2.txt"]),
                Sample(id="sample1", files=["file3.txt"]),
            ]

            unique_ids = data.unique_ids
            print(unique_ids)  # {"sample1", "sample2"}
            ```
        """
        return {s.id for s in self}

    @property
    def with_files(self) -> "Samples":
        """
        Get only samples with existing files from a Samples object.

        Returns:
            Class: A new instance of the class with only the samples with files.
        """
        return self.__class__(
            [
                sample
                for sample in self
                if sample.files and all(Path(f).exists() for f in sample.files)
            ]
        )

    @property
    def without_files(self) -> "Samples":
        """
        Get only samples without existing files from a Samples object.

        Returns:
            Class: A new instance of the class with only the samples without files.
        """
        return self.__class__(
            [
                sample
                for sample in self
                if not sample.files or any(not Path(f).exists() for f in sample.files)
            ]
        )

    @property
    def complete(self) -> "Samples":
        """
        Get only completed samples from a Samples object.

        Samples are considered as completed if all runners have completed
        successfully, and the sample is marked as done.

        Returns:
            Class: A new instance of the class with only the completed samples.
        """

        return self.__class__(
            [sample for sample in self if not sample.failed], output=self.output
        )

    @property
    def failed(self) -> "Samples":
        """
        Get only failed samples from a Samples object.

        Samples are considered as failed if one or more of the runners has not
        completed successfully, or has explicitly marked the sample as not done.

        Returns:
            Class: A new instance of the class with only the failed samples.
        """
        return self.__class__([sample for sample in self if sample.failed])

    def __str__(self) -> str:
        return "\n".join([str(s) for s in self])

    def __setstate__(self, state: dict) -> None:
        for k, v in state.items():
            self.__setattr__(k, v)

    def __reduce__(self) -> str | tuple[Any, ...]:
        return (
            self.__class__,
            (self.data,),
            {k: self.__getattribute__(k) for k in fields_dict(self.__class__)},
        )

    def __or__(self, other: "Samples") -> "Samples":
        if self.__class__ != other.__class__:
            raise MergeSamplesTypeError

        _samples = deepcopy(self)
        for sample in other:
            _samples[sample.uuid] = sample

        return _samples

    def __and__(self, other: "Samples") -> "Samples":
        if self.__class__ != other.__class__:
            raise MergeSamplesTypeError

        _samples = deepcopy(self)
        for _field in fields_dict(self.__class__):
            setattr(
                _samples,
                _field,
                self.merge(_field, getattr(self, _field), getattr(other, _field)),
            )
        return _samples