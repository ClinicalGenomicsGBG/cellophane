from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from copy import deepcopy

if TYPE_CHECKING:
    from cellophane.data import Sample, Samples
    from cellophane.cfg import Config
    from typing import TypeVar

    SAMPLE = TypeVar("SAMPLE", bound=Sample)
    SAMPLES = TypeVar("SAMPLES", bound=Samples)

class SAMPLES_PREDICATE(Protocol):
    def __call__(self, sample: SAMPLE, /, samples: SAMPLES, config: Config) -> bool: ...

class EXCEPTION_PREDICATE(Protocol):
    def __call__(self, exception: BaseException, config: Config) -> bool: ...

def select_samples(samples: SAMPLES, config: Config, predicate: SAMPLES_PREDICATE) -> SAMPLES:
    """Selects samples based on a predicate function.

    Args:
    ----
        samples (SAMPLES): The samples to be filtered.
        config (Config): The configuration object.
        predicate (PREDICATE): A predicate function that takes a sample, the samples, and the config,
            and returns True if the sample should be included in the result.

    Returns:
    -------
        SAMPLES: A new Samples object containing the selected samples.
    """
    instance = deepcopy(samples)
    instance.data = [
        sample
        for sample in samples
        if predicate(sample, samples=samples, config=config)
    ]

    return instance
