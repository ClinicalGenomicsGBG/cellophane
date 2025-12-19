"""Shim to allow importing from cellophane.src"""

from pathlib import Path
from warnings import warn

warn(
    "Importing from cellophane.src will be deprecated in a future version of cellophane. "
    "References to 'cellophane.src' should be replaced with 'cellophane'",
    category=PendingDeprecationWarning,
)

__path__ = [str(Path(__file__).parent)]
