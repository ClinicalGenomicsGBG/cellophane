"""Configuration object based on a schema."""
from __future__ import annotations

from attrs import define
from cellophane.data import Container

@define(init=False, slots=False)
class Config(Container): ...