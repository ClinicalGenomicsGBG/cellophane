"""Sample and Samples class definitions."""

from __future__ import annotations

from collections import UserList
from contextlib import suppress
from copy import deepcopy
from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast, overload
from uuid import UUID, uuid4
from warnings import warn

from attrs import NOTHING, define, field, fields, fields_dict, make_class
from attrs.setters import convert, frozen
from ruamel.yaml import YAML

from .container import Container
from .exceptions import MergeSamplesTypeError, MergeSamplesUUIDError
from .merger import Merger
from .util import convert_path_list

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, Iterable, Literal, Sequence

    from cellophane.data import Output, OutputGlob

SAMPLE = TypeVar("SAMPLE", bound="Sample")
SAMPLES = TypeVar("SAMPLES", bound="Samples")
SAMPLE_OR_SAMPLES = TypeVar("SAMPLE_OR_SAMPLES", "Sample", "Samples")


class SplitFunctionError(Exception): ...


def _apply_mixins(
    cls: type[SAMPLE_OR_SAMPLES],
    mixins: Sequence[type[SAMPLE_OR_SAMPLES]],
    **kwargs: Any,
) -> type[SAMPLE_OR_SAMPLES]:
    name_ = cls.__name__
    if not mixins:
        return cls

    mixins_ = []
    for mixin in mixins:
        if getattr(mixin, "__slots__", None):
            raise TypeError(
                f"{mixin.__name__}: Mixins must not have __slots__ "
                "(use @define(slots=False) and don't set __slots__ in the class body)",
            )
        name_ += f"_{mixin.__name__}"
        if "__attrs_attrs__" not in mixin.__dict__:
            mixin = define(mixin, slots=False)
        if cls not in cast(type, mixin).__bases__:
            cast(type, mixin).__bases__ = (cls,)

        mixins_.append(mixin)

    cls_ = cast(type[SAMPLE_OR_SAMPLES], make_class(name_, (), (*mixins_,), slots=False))
    cls_._mixins = (*mixins_,)
    for k, v in kwargs.items():
        setattr(cls_, k, v)
    return cls_


def _reconstruct(
    cls: type[SAMPLE_OR_SAMPLES],
    mixins: Sequence[type[SAMPLE_OR_SAMPLES]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: dict[str, Any],
    cls_kwargs: dict[str, Any] | None = None,
) -> SAMPLE_OR_SAMPLES:
    cls_ = _apply_mixins(cls, mixins, **(cls_kwargs or {}))
    instance = cls_(*args, **kwargs)
    cast(Sample | Samples, instance).__setstate__(state)
    return instance


@define(slots=False)
class Sample:  # type: ignore[no-untyped-def]
    """Base sample class represents a sample with an ID, a list of files, a flag indicating
    if it's done, and a list of Output objects.
    Can be subclassed in a module to add additional functionality (mixin).

    Attributes
    ----------
        id (str): The ID of the sample.
        files (list[str]): The list of files associated with the sample.
        done (bool | None): The flag indicating if the sample is done. Defaults to None.
        output (list[Output]): The list of Output objects associated with the sample.

    Methods
    -------
        with_mixins(mixins): Returns a new Sample class with the specified mixins
            applied.

    """

    id: str = field(
        converter=str,
        on_setattr=convert,
        kw_only=True,
    )
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
    _mixins: ClassVar[tuple[type[Sample], ...]] = ()

    def __str__(self) -> str:
        return self.id

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key in fields_dict(self.__class__):
            setattr(self, key, value)
        else:
            raise KeyError(f"Sample has no attribute '{key}'")

    def __getstate__(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in fields_dict(self.__class__)}

    def __setstate__(self, state: dict[str, Any]) -> None:
        for k, v in state.items():
            object.__setattr__(self, k, v)

    def __reduce__(self) -> str | tuple[Any, ...]:
        state = self.__getstate__()
        args = ()
        kwargs = {
            name: state.pop(name)  # nofmt
            for name, attribute in fields_dict(self.__class__).items()
            if attribute.kw_only
        }
        return (_reconstruct, (Sample, self._mixins, args, kwargs, state))

    def __and__(self, other: "Sample") -> "Sample":
        if self.uuid != other.uuid:
            raise MergeSamplesUUIDError("Cannot merge samples with different UUIDs")

        _sample = deepcopy(self)
        for _field in (f for f in fields_dict(self.__class__) if f not in ["id", "uuid"]):
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

    @merge.register("files")
    @staticmethod
    def _merge_files(this: list[Path], that: list[Path]) -> list[Path]:
        # This is a hack to remove duplicates while preserving order
        # the keys of dict.fromkeys() is essentially an ordered set
        return [*dict.fromkeys((*this, *that))]

    @merge.register("meta")
    @staticmethod
    def _merge_meta(this: Container, that: Container) -> Container:
        return this | that

    @merge.register("_fail")
    @staticmethod
    def _merge_fail(this: str | None, that: str | None) -> str | None:
        return f"{this}\n{that}" if this and that else this or that

    @merge.register("processed")
    @staticmethod
    def _merge_done(this: bool | None, that: bool | None) -> bool | None:
        return this and that

    def fail(self, reason: str) -> None:
        """Marks the sample as failed with the specified reason."""
        self._fail = reason

    @property
    def failed(self) -> str | Literal[False]:
        """Checks if the sample is failed by any runner"""
        return self._fail or False

    @classmethod
    def with_mixins(cls, mixins: Sequence[type[SAMPLE]]) -> type[SAMPLE]:
        """Returns a new Sample class with the specified mixins as base classes.

        Internally called by Cellophane with the samples mixins specified
        in the loaded modules. Uses attrs.make_class to create a new class,
        so any attrs decorators in the mixins will be applied.

        Args:
        ----
            cls (type[SAMPLE]): The class to apply the mixins to.
            mixins (Sequence[type[SAMPLE]]): A sequence of mixin classes to apply.

        Returns:
        -------
            type[SAMPLE]: The new class with the mixins applied.

        """
        return cast(type[SAMPLE], _apply_mixins(cls, mixins))


class _SampleClassDescriptor:
    @overload
    def __get__(self, instance: None, owner: type[Samples[SAMPLE]]) -> type[SAMPLE]: ...
    @overload
    def __get__(self, instance: Samples[SAMPLE], owner: Any = None) -> type[SAMPLE]: ...
    def __get__(self, instance: Any, owner: Any = None) -> Any:
        cls = owner if instance is None else type(instance)
        return cls._sample_class


@define(slots=False, order=False, init=False)
class Samples(UserList[SAMPLE]):
    """Base samples class represents a list of samples.
    Can be subclassed in a module to add additional functionality (mixin).

    Attributes
    ----------
        data (list[SAMPLE]): The list of samples.

    Methods
    -------
        from_file(path: Path): Returns a new Samples object with samples loaded from
            the specified YAML file.
        with_mixins(mixins): Returns a new Samples class with the specified mixins
            applied.
        with_sample_class(sample_class): Returns a new Samples class with the specified
            sample class.

    """

    _mixins: ClassVar[tuple[type[Samples], ...]] = ()
    _sample_class: ClassVar[type[Sample]] = Sample
    sample_class: ClassVar[_SampleClassDescriptor] = _SampleClassDescriptor()
    merge: ClassVar[Merger] = Merger()
    data: list[SAMPLE] = field(factory=list)
    output: set[Output | OutputGlob] = field(factory=set, converter=set, on_setattr=convert)

    def __init__(self, data: list | None = None, /, **kwargs: Any) -> None:
        self.__attrs_init__(**kwargs)  # ty: ignore[unresolved-attribute]
        super().__init__(data or [])

    def __getitem__(self, key: int | UUID) -> SAMPLE:  # ty: ignore[invalid-method-override]
        if isinstance(key, int):
            return super().__getitem__(key)

        if isinstance(key, UUID) and key in self:
            return next(s for s in self if s.uuid == key)

        if isinstance(key, UUID):
            raise KeyError(f"Sample with UUID {key.hex!r} not found")

        raise TypeError(f"Key {key!r} is not an int or a UUID")

    def __setitem__(self, key: int | UUID, value: SAMPLE) -> None:  # ty: ignore[invalid-method-override]
        if isinstance(key, int):
            super().__setitem__(key, value)
        elif isinstance(key, UUID) and key in self:
            self[self.index(self[key])] = value
        elif isinstance(key, UUID):
            self.append(value)
        else:
            raise TypeError(f"Key {key!r} is not an int or a UUID")

    def __contains__(self, item: SAMPLE | UUID) -> bool:  # ty: ignore[invalid-method-override]
        if isinstance(item, UUID):
            return any(s.uuid == item for s in self)
        else:
            return super().__contains__(item)

    def __str__(self) -> str:
        return "\n".join([str(s) for s in self])

    def __getstate__(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in fields_dict(self.__class__)}

    def __setstate__(self, state: dict[str, Any]) -> None:
        for k, v in state.items():
            object.__setattr__(self, k, v)

    def __reduce__(self) -> str | tuple[Any, ...]:
        state = self.__getstate__()
        args = ()
        kwargs = {
            name: state.pop(name)  # nofmt
            for name, attribute in fields_dict(self.__class__).items()
            if attribute.kw_only
        }
        cls_kwargs = {"_sample_class": self.sample_class}
        return (_reconstruct, (Samples, self._mixins, args, kwargs, state, cls_kwargs))

    def __or__(self, other: Samples) -> Samples:
        """Returns a Samples object with samples from both self and other, without merging attributes

        If a sample is in both 'self' and 'other', the sample from 'other' is prefered.
        """
        samples = deepcopy(self)
        samples |= other
        return samples

    def __ior__(self, other: Samples) -> Samples:
        if self.__class__.__name__ != other.__class__.__name__:
            raise MergeSamplesTypeError(f"Cannot merge {self.__class__} with {other.__class__}")
        for sample in other:
            self[sample.uuid] = sample

        return self

    def __and__(self, other: Samples) -> Samples:
        """Returns a Samples object with samples from both self and other, merging attributes."""
        samples = deepcopy(self)
        samples &= other
        return samples

    def __iand__(self, other: Samples) -> Samples:
        if self.__class__.__name__ != other.__class__.__name__:
            raise MergeSamplesTypeError(f"Cannot merge {self.__class__} with {other.__class__}")
        for field_ in fields_dict(self.__class__):
            self_ = getattr(self, field_)
            other_ = getattr(other, field_)
            setattr(self, field_, self.merge(field_, self_, other_))
        return self

    def __xor__(self, other: Samples) -> Samples:
        """Return a Samples object with samples from both self and other, without merging attributes.

        Also update all fields in 'self' with those from 'other' (except for the 'data' field).
        """
        samples = deepcopy(self)
        samples ^= other
        return samples

    def __ixor__(self, other: Samples) -> Samples:
        if self.__class__.__name__ != other.__class__.__name__:
            raise MergeSamplesTypeError(f"Cannot merge {self.__class__} with {other.__class__}")
        self |= other
        for field_ in fields_dict(self.__class__):
            if field_ == "data":
                continue
            other_ = getattr(other, field_)
            setattr(self, field_, other_)
        return self

    @merge.register("data")
    @staticmethod
    def _merge_data(this: list[SAMPLE], that: list[SAMPLE]) -> list[SAMPLE]:
        data: list[SAMPLE] = []
        for uuid in {s.uuid for s in (*this, *that)}:
            this_, that_ = None, None
            with suppress(StopIteration):
                this_ = next(s for s in this if s.uuid == uuid)
            with suppress(StopIteration):
                that_ = next(s for s in that if s.uuid == uuid)
            data.append(this_ & that_ if this_ and that_ else this_ or that_)  # ty: ignore[invalid-argument-type]
            # arg-type can be ignored because uuid is guaranteed
            # to be in at least one of the lists

        return data

    @merge.register("output")
    @staticmethod
    def _merge_output(this: set[Output], that: set[Output]) -> set[Output]:
        return this | that

    @classmethod
    def from_file(cls, path: Path) -> Samples:
        """Get samples from a YAML file"""
        samples = []
        yaml = YAML(typ="safe")

        try:
            for sample in yaml.load(path):
                (samples.append(cls.sample_class(**sample)),)  # type: ignore[call-arg]
            return cls(samples)
        except TypeError as exc:
            missing_fields = [
                repr(f.name)
                for f in fields(cls.sample_class)
                if f.name not in sample
                and f.init is True
                and f.default is NOTHING
            ]
            if missing_fields:
                raise TypeError(
                    "Missing required field(s) "
                    f"{', '.join(missing_fields)} "
                    "for at least one sample"
                ) from exc
            else:
                raise exc

    @classmethod
    def with_mixins(cls, mixins: Sequence[type[SAMPLES]]) -> type[SAMPLES]:
        """Returns a new Samples class with the specified mixins as base classes.

        Internally called by Cellophane with the samples mixins specified
        in the loaded modules. Uses attrs.make_class to create a new class,
        so any attrs decorators in the mixins will be applied.

        Args:
        ----
            cls (type[SAMPLES]): The class to apply the mixins to.
            mixins (Iterable[type[SAMPLES]]): An iterable of mixin classes to apply.

        Returns:
        -------
            type: The new class with the mixins applied.

        """
        return cast(type[SAMPLES], _apply_mixins(cls, mixins, _sample_class=cls.sample_class))

    @classmethod
    def with_sample_class(cls, sample_class: type[SAMPLE]) -> type[SAMPLES[SAMPLE]]:
        """Returns a new Samples class with the specified sample class as the
        class to use for samples.

        Internally called by Cellophane with the samples mixins specified
        in the loaded modules.

        Args:
        ----
            cls (type[SAMPLES]): The class to apply the mixins to.
            sample_class (type[SAMPLE]): The class to use for samples.

        Returns:
        -------
            type[SAMPLES]: The new class with the sample class applied.

        """
        return type(cls.__name__, (cls,), {"_sample_class": sample_class})

    def split(self, by: str | Callable | None = "uuid", **kwargs) -> Iterable[tuple[Any, Samples[SAMPLE]]]:
        """Splits the data into groups based on the specified attribute value.

        Args:
        ----
            by (str | Callable | None): The attribute to link the samples by, or a callable
                that takes a sample and returns the value to link by. Defaults to "uuid",
                which results in Samples objects with one sample each.

        Yields:
        ------
            Iterable[tuple[Any, Samples[S]]]: An iterable of tuples containing the
                linked attribute value and a Samples object containing the
                samples with that attribute value.

        Example:
        -------
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
            return [(None, self)]
        elif callable(by):

            def _by(sample: SAMPLE, **kwargs) -> Any:
                sig = signature(by)
                kwargs["sample"] = sample
                kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
                try:
                    result = by(**kwargs)  # ty: ignore[call-top-callable]
                except Exception as exc:
                    raise SplitFunctionError(
                        f"Error calling 'by' callable {by!r} with sample "  # nofmt
                        f"{sample!r} and kwargs {kwargs!r}: {exc}"
                    ) from exc
                return result

        elif isinstance(by, str):

            def _by(sample: SAMPLE, **kwargs) -> Any:
                del kwargs  # unused
                return getattr(sample, by)
        else:
            raise TypeError("Argument 'by' must be a string or a callable that returns a grouping value")

        grouped_samples: dict[Any, Samples[SAMPLE]] = {}
        for sample in self:
            try:
                group_var = _by(sample=sample, **kwargs)
            except AttributeError:
                group_var = None
            except SplitFunctionError as exc:
                warn(str(exc))
                group_var = None
            except Exception as exc:
                warn(f"Error getting group for sample {sample!r}: {exc}")
                group_var = None
            try:
                group = grouped_samples[group_var]
            except KeyError:
                group = grouped_samples[group_var] = self.__class__()
            group.append(sample)

        return list(grouped_samples.items())

    @property
    def unique_ids(self) -> set[str]:
        """Returns a set of unique IDs from the samples in the data.

        Returns:
        -------
            set[str]: The set of unique IDs.

        Example:
        -------
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
    def with_files(self) -> Samples[SAMPLE]:
        """Get only samples with existing files from a Samples object.

        Returns
        -------
            Class: A new instance of the class with only the samples with files.

        """
        instance = deepcopy(self)
        instance.data = [sample for sample in self if sample.files and all(Path(f).exists() for f in sample.files)]

        return instance

    @property
    def without_files(self) -> Samples[SAMPLE]:
        """Get only samples without existing files from a Samples object.

        Returns
        -------
            Class: A new instance of the class with only the samples without files.

        """
        instance = deepcopy(self)
        instance.data = [
            sample  # nofmt
            for sample in self
            if not sample.files
            or any(not Path(f).exists() for f in sample.files)
        ]

        return instance

    @property
    def complete(self) -> Samples[SAMPLE]:
        """Get only completed samples from a Samples object.

        Samples are considered as completed if all runners have completed
        successfully, and the sample is marked as done.

        Returns
        -------
            Class: A new instance of the class with only the completed samples.

        """
        instance = deepcopy(self)
        instance.data = [sample for sample in self if sample.processed and not sample.failed]

        return instance

    @property
    def unprocessed(self) -> Samples[SAMPLE]:
        """Get only unprocessed samples from a Samples object.

        Samples are considered as unprocessed if none of the runners have processed the sample,
        and the sample is not marked as done.

        Returns
        -------
            Class: A new instance of the class with only the unprocessed samples.

        """
        instance = deepcopy(self)
        instance.data = [sample for sample in self if not sample.failed and not sample.processed]

        return instance

    @property
    def failed(self) -> Samples[SAMPLE]:
        """Get only failed samples from a Samples object.

        Samples are considered as failed if one or more of the runners has not
        completed successfully, or has explicitly marked the sample as not done.

        Returns
        -------
            Class: A new instance of the class with only the failed samples.

        """
        instance = deepcopy(self)
        instance.data = [sample for sample in self if sample.failed]

        return instance
