from hashlib import sha256
from pathlib import Path
from typing import Any

from attrs import define, field
from cloudpickle import dumps

from cellophane.src.cfg import Config
from cellophane.src.data import Output, OutputGlob, Samples


@define
class Checkpoint:
    """
    Checkpoint store to track the state of a runner.

    Args:
        workdir (Path): The working directory for the checkpoint store.
        config (Config): The configuration object.

    Attributes:
        file (Path): The file path for the checkpoint store.
        checkpoints (dict[str, bytes]): The checkpoints.
    """

    label: str
    workdir: Path
    config: Config
    samples: Samples
    file: Path = field(init=False)
    _cache: str | None = field(init=False)

    def __attrs_post_init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs  # unused
        self.file = self.workdir / f".checkpoints.{self.label}.sha256"
        try:
            self._cache = self.file.read_text()
        except Exception:  # pylint: disable=broad-except
            self._cache = None

    def _hash(self, *args: Any, **kwargs: Any) -> str:
        """
        Generate a hash for the samples.

        Args:
            samples (Samples): The samples to hash.
            *args (Any): Arbitrary positional arguments to include in the hash.
            **kwargs (Any): Arbitrary keyword arguments to include in the hash.

        Returns:
            bytes: The computed sha256 hash.
        """
        sha = sha256(dumps(self.config))
        sha.update(dumps(args))
        sha.update(dumps(kwargs))
        paths = set()
        for sample in self.samples:
            sha.update(sample.id.encode())
            paths |= {*sample.files}
        for output in self._outputs:
            if isinstance(output, Output):
                paths |= {output.src}
            elif isinstance(output, OutputGlob):
                outputs, _ = output.resolve(
                    samples=self.samples,
                    config=self.config,
                    workdir=self.workdir,
                )
                paths |= {o.src for o in outputs}
        for path in paths:
            stat = path.stat()
            sha.update(str(stat.st_size).encode())
            sha.update(str(stat.st_mtime).encode())
        return sha.hexdigest()

    @property
    def _outputs(self) -> set[Output | OutputGlob]:
        return {o for o in self.samples.output if o.checkpoint == self.label}

    def store(self, **kwargs: Any) -> None:
        """
        Store a checkpoint.

        Args:
            tag (str): The tag for the checkpoint.
            samples (Samples): The samples to store.
            **kwargs (Any): Arbitrary keyword arguments to include in the hash.
        """
        self._cache = self._hash(**kwargs)
        with open(self.file, "w", encoding="utf-8") as file:
            file.write(self._cache)

    def check(self, **kwargs: Any) -> bool:
        """
        Check if a checkpoint matches the stored hash.

        Args:
            tag (str): The tag for the checkpoint.
            samples (Samples): The samples to check.
            **kwargs (Any): Arbitrary keyword arguments to include in the hash.

        Returns:
            bool: True if the checkpoint matches the stored hash.
        """
        return self._hash(**kwargs) == self._cache


@define
class Checkpoints:
    """
    Collection of checkpoints.

    Args:
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
        return self.__getattribute__(key)
