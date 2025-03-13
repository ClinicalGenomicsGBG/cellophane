import json
import time
from contextlib import suppress
from functools import cached_property
from pathlib import Path
from random import randbytes
from typing import Any, Iterator, Sequence

from attrs import define, field
from dill import dumps
from xxhash import xxh3_64

from cellophane.cfg import Config
from cellophane.data import Output, OutputGlob, Samples
from cellophane.util import Timestamp


@define
class Checkpoint:
    """Checkpoint store to track the state of a runner.

    Args:
    ----
        workdir (Path): The working directory for the checkpoint store.
        config (Config): The configuration object.

    Attributes:
    ----------
        file (Path): The file path for the checkpoint store.
        checkpoints (dict[str, bytes]): The checkpoints.

    """

    label: str
    workdir: Path
    config: Config
    samples: Samples
    file: Path = field(init=False)
    _cache: dict[str, str] | None = field(init=False)
    _extra_paths: set[Path] = field(factory=set)

    def __attrs_post_init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs  # unused
        self.file = self.workdir / f".checkpoints.{self.label}.json"
        try:
            self._cache = json.loads(self.file.read_text())
        except Exception:  # pylint: disable=broad-except
            self._cache = None

    @cached_property
    def _paths(self) -> set[Path]:
        paths = self._extra_paths.copy()
        for sample in self.samples:
            paths |= {*sample.files}
        for output in self._outputs:
            if isinstance(output, Output):
                output_paths = {output.src}
            elif isinstance(output, OutputGlob):
                outputs = output.resolve(
                    samples=self.samples,
                    config=self.config,
                    workdir=self.workdir,
                    # Only src is considered, so using the current time works
                    # since timestamps are never included in src paths
                    timestamp=Timestamp(),
                )
                output_paths = {o.src for o in outputs}

            paths |= output_paths

        for path in paths.copy():
            if path.is_dir():
                paths.remove(path)
                paths |= {*path.rglob("*")}

        return paths

    @property
    def paths(self) -> set[Path]:
        return self._paths

    @paths.setter
    def paths(self, paths: Sequence[Path]) -> None:
        self._extra_paths = {*paths}
        with suppress(AttributeError):
            del self._paths

    @property
    def samples(self) -> Samples:
        return self._samples

    @samples.setter
    def samples(self, samples: Samples) -> None:
        self._samples = samples
        with suppress(AttributeError):
            del self._paths

    def _hash(self, *args: Any, **kwargs: Any) -> Iterator[tuple[str, str]]:
        """Generate a hash for the samples.

        The base of the hash will be calculate from the samples, and any additional
        arguments or keyword arguments passed to the function. The hash will be updated
        with the name, size, and modification time of each file in the outputs defined
        for the checkpoint in the samples object.

        Each file will be hashed individually and the name of the file and the hash will
        be yielded.

        Args:
        ----
            samples (Samples): The samples to hash.
            *args (Any): Arbitrary positional arguments to include in the hash.
            **kwargs (Any): Arbitrary keyword arguments to include in the hash.

        Yields:
        ------
            tuple[str, bytes]: The name of the file and the hash.

        """
        base = xxh3_64()
        base.update(dumps(args))
        base.update(dumps(kwargs))
        base.update(self.label.encode())

        for path in self._paths:
            hash_ = base.copy()
            try:
                hash_.update(path.name.encode())
                stat = path.stat()
                hash_.update(stat.st_size.to_bytes(8, "big"))
                hash_.update(int(stat.st_mtime).to_bytes(8, "big"))
            except OSError:
                hash_.update(randbytes(8))
            yield str(path), hash_.hexdigest()

        with suppress(AttributeError):
            del self._paths

    def hexdigest(self, *args: Any, **kwargs: Any) -> str:
        hash_ = self._hash(*args, **kwargs)
        combined = xxh3_64()
        for _, h in hash_:
            combined.update(h)
        return combined.hexdigest()

    @property
    def _outputs(self) -> set[Output | OutputGlob]:
        return {o for o in self.samples.output if o.checkpoint == self.label}

    def store(self, *args: Any, **kwargs: Any) -> None:
        """Store a checkpoint.

        Args:
        ----
            *args (Any): Arbitrary positional arguments to include in the hash.
            **kwargs (Any): Arbitrary keyword arguments to include in the hash.

        """
        self._cache = dict(self._hash(*args, **kwargs))
        self.file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file, "w", encoding="utf-8") as file:
            file.write(json.dumps(self._cache))

    def check(self, *args: Any, **kwargs: Any) -> bool:
        """Check if a checkpoint matches the stored hash.

        Args:
        ----
            tag (str): The tag for the checkpoint.
            samples (Samples): The samples to check.
            **kwargs (Any): Arbitrary keyword arguments to include in the hash.

        Returns:
        -------
            bool: True if the checkpoint matches the stored hash.

        """
        return (
            self._cache is not None
            and all(Path(s) in self._paths for s in self._cache)
            and all(str(p) in self._cache for p in self._paths)
            and all(self._cache[f] == h for f, h in self._hash(*args, **kwargs))
        )

    def add_paths(self, *paths: Path) -> None:
        """Add additional paths to the checkpoint.

        Args:
        ----
            *paths (Path): The paths to add to the checkpoint.

        """
        self._extra_paths |= {*paths}


@define
class Checkpoints:
    """Collection of checkpoints.

    Args:
    ----
        samples (Samples): The samples to get checkpoints for.
        workdir (Path): The working directory for the checkpoint store.
        config (Config): The configuration object.

    """

    samples: Samples
    workdir: Path
    config: Config
    _checkpoints: dict[str, Checkpoint] = field(factory=dict)

    def __getattr__(self, key: str) -> Checkpoint:
        if key not in self._checkpoints:
            self._checkpoints[key] = Checkpoint(
                label=key,
                workdir=self.workdir,
                config=self.config,
                samples=self.samples,
            )

        return self._checkpoints[key]

    def __getitem__(self, key: str) -> Checkpoint:
        return self.__getattr__(key)
