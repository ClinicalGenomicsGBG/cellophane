from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from copy import deepcopy
from inspect import signature
from warnings import warn

if TYPE_CHECKING:
    from cellophane.data import Sample, Samples
    from cellophane.cfg import Config
    from typing import TypeVar

    SAMPLE = TypeVar("SAMPLE", bound=Sample)
    SAMPLES = TypeVar("SAMPLES", bound=Samples)


class SAMPLES_PREDICATE(Protocol):
    def __call__(self, /, sample: SAMPLE, samples: SAMPLES, config: Config) -> bool: ...


class EXCEPTION_PREDICATE(Protocol):
    def __call__(self, /, exception: BaseException, config: Config) -> bool: ...


def select_samples(samples: SAMPLES, config: Config, predicate: SAMPLES_PREDICATE, /) -> SAMPLES | None:
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
        predicate (SAMPLES_PREDICATE): The predicate function to apply.

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
        instance.data = [sample for sample in samples if predicate(sample=sample, **kwargs)]
        return instance if instance else None
    except Exception as exc:
        warn(f"Predicate function '{name}' raised an exception: {exc!r}")
        return None
