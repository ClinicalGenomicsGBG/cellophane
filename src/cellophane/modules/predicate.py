from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from inspect import signature
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, TypeVar, cast
from warnings import warn

if TYPE_CHECKING:
    from cellophane.cfg import Config
    from cellophane.data import Sample, Samples

SAMPLE = TypeVar("SAMPLE", bound="Sample")
SAMPLES = TypeVar("SAMPLES", bound="Samples[Any]")


class _KW_NONE(Protocol):
    def __call__(self) -> bool: ...


class _KW_SAMPLE(Protocol[SAMPLE]):
    def __call__(self, *, sample: SAMPLE) -> bool: ...


class _KW_SAMPLES(Protocol[SAMPLES]):
    def __call__(self, *, samples: SAMPLES) -> bool: ...


class _KW_CONFIG(Protocol):
    def __call__(self, *, config: Config) -> bool: ...


class _KW_SAMPLE_SAMPLES(Protocol[SAMPLE, SAMPLES]):
    def __call__(self, *, sample: SAMPLE, samples: SAMPLES) -> bool: ...


class _KW_SAMPLE_CONFIG(Protocol[SAMPLE]):
    def __call__(self, *, sample: SAMPLE, config: Config) -> bool: ...


class _KW_SAMPLES_CONFIG(Protocol[SAMPLES]):
    def __call__(self, *, samples: SAMPLES, config: Config) -> bool: ...


class _KW_SAMPLE_SAMPLES_CONFIG(Protocol[SAMPLE, SAMPLES]):
    def __call__(self, *, sample: SAMPLE, samples: SAMPLES, config: Config) -> bool: ...


class _KW_EXCEPTION(Protocol):
    def __call__(self, *, exception: BaseException) -> bool: ...


class _KW_EXCEPTION_CONFIG(Protocol):
    def __call__(self, *, exception: BaseException, config: Config) -> bool: ...


SAMPLE_PREDICATE: TypeAlias = (
    _KW_NONE
    | _KW_SAMPLE[SAMPLE]
    | _KW_SAMPLES[SAMPLES]
    | _KW_CONFIG
    | _KW_SAMPLE_SAMPLES[SAMPLE, SAMPLES]
    | _KW_SAMPLE_CONFIG[SAMPLE]
    | _KW_SAMPLES_CONFIG[SAMPLES]
    | _KW_SAMPLE_SAMPLES_CONFIG[SAMPLE, SAMPLES]
)

EXCEPTION_PREDICATE: TypeAlias = _KW_NONE | _KW_EXCEPTION | _KW_EXCEPTION_CONFIG | _KW_CONFIG


def select_samples(samples: SAMPLES, config: Config, predicate: SAMPLE_PREDICATE, /) -> SAMPLES | None:
    """
    Select samples from a collection based on a predicate function.

    The predicate can accept zero or more of the 'sample', 'samples', and 'config' keyword arguments.
    This function may return an empty collection, if 'samples' is empty but the predicate returns True.

    This function will return None if the predicate takes a 'sample' keyword argument and no samples
    satisfy the predicate, the predicate does not take a 'sample' keyword argument and the predicate
    returns False, or if the predicate raises an exception.

    Args:
        samples (SAMPLES): The collection of samples to filter.
        config (Config): The configuration object.
        predicate (SAMPLE_PREDICATE): The predicate function to apply.

    Returns:
        SAMPLES | None: The filtered collection of samples, or None if no samples match.
    """
    sig = signature(predicate)
    kwargs = {}
    name = getattr(predicate, "__qualname__", getattr(predicate, "__name__", repr(predicate)))

    if "config" in sig.parameters:
        kwargs["config"] = config
    if "samples" in sig.parameters:
        kwargs["samples"] = samples
    try:
        if "sample" not in sig.parameters:
            return samples if predicate(**kwargs) else None
        instance = deepcopy(samples)
        predicate = cast(Callable[..., bool], predicate)
        instance.data = [sample for sample in samples if predicate(sample=sample, **kwargs)]
        return instance if instance else None
    except Exception as exc:
        warn(f"Predicate function '{name}' raised an exception: {exc!r}")
        return None


def select_exception(exception: BaseException, config: Config, predicate: EXCEPTION_PREDICATE, /) -> bool:
    """
    Evaluate an exception against a predicate function.

    The predicate can accept zero or more of the 'exception' and 'config' keyword arguments.

    Args:
        exception (BaseException): The exception to evaluate.
        config (Config): The configuration object.
        predicate (EXCEPTION_PREDICATE): The predicate function to apply.

    Returns:
        bool: True if the exception satisfies the predicate, False otherwise.
    """
    sig = signature(predicate)
    kwargs = {}
    name = getattr(predicate, "__qualname__", getattr(predicate, "__name__", repr(predicate)))

    if "config" in sig.parameters:
        kwargs["config"] = config
    if "exception" in sig.parameters:
        kwargs["exception"] = exception
    try:
        return predicate(**kwargs)
    except Exception as exc:
        warn(f"Predicate function '{name}' raised an exception: {exc!r}")
        return False
