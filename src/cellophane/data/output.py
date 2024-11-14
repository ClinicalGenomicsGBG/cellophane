"""Outut classes for copying files to another directory."""

import time
from glob import glob
from pathlib import Path
from typing import Iterable
from warnings import warn

from attrs import define, field
from attrs.setters import convert

from .container import Container


@define
class Output:
    """Output file to be copied to the another directory.
    """

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

    def __hash__(self) -> int:
        return hash((self.src, self.dst))


@define
class OutputGlob:  # type: ignore[no-untyped-def]
    """Output glob find files to be copied to the another directory.
    """

    src: str = field(
        converter=str,
        on_setattr=convert,
    )
    dst_dir: str | None = field(  # type: ignore[var-annotated]
        default=None,
        kw_only=True,
        converter=lambda v: v if v is None else str(v),
        on_setattr=convert,
    )
    dst_name: str | None = field(  # type: ignore[var-annotated]
        default=None,
        kw_only=True,
        converter=lambda v: v if v is None else str(v),
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

    def __hash__(self) -> int:
        return hash((self.src, self.dst_dir, self.dst_name))

    def resolve(
        self,
        samples: Iterable,
        workdir: Path,
        config: Container,
        timestamp: time.struct_time,
    ) -> set[Output]:
        """Resolve the glob pattern to a list of files to be copied.

        Args:
        ----
            samples (Samples): The samples being processed.
            workdir (Path): The working directory
                with tag and the value of the split_by attribute (if any) appended.
            config (Container): The configuration object.
            logger (LoggerAdapter): The logger.

        Returns:
        -------
            set[Output]: The list of files to be copied.

        """
        outputs = set()

        for sample in samples:
            meta = {
                "samples": samples,
                "config": config,
                "workdir": workdir,
                "sample": sample,
            }

            match self.src.format(**meta):
                case p if Path(p).is_absolute():
                    pattern = p
                case p if Path(p).is_relative_to(workdir):
                    pattern = p
                case p:
                    pattern = str(workdir / p)

            if not (matches := [Path(m) for m in glob(pattern)]) and not self.optional:
                warn(f"No files matched pattern '{pattern}'")

            for m in matches:
                if self.dst_dir is None:
                    dst_dir = config.resultdir
                else:
                    _dst_dir = self.dst_dir.format(**meta)
                    _dst_dir = time.strftime(_dst_dir, timestamp)

                    if Path(_dst_dir).is_absolute():
                        dst_dir = Path(_dst_dir)
                    else:
                        dst_dir = config.resultdir / _dst_dir


                if self.dst_name is None:
                    dst_name = m.name
                elif len(matches) > 1:
                    warn(
                        f"Destination name {self.dst_name} will be ignored "
                        f"as '{self.src}' matches multiple files",
                    )
                    dst_name = m.name
                else:
                    dst_name = self.dst_name.format(**meta)
                    dst_name = time.strftime(dst_name, timestamp)

                dst = Path(dst_dir) / dst_name

                outputs.add(
                    Output(
                        src=m,
                        dst=dst,
                        optional=self.optional,
                        checkpoint=self.checkpoint.format(**meta),
                    ),
                )

        return outputs
