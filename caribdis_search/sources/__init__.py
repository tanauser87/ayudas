"""Adaptadores de fuentes oficiales."""

from .bdns import BDNSSource
from .generic import GenericPageSource
from .junta_procedures import JuntaProceduresSource

__all__ = ["BDNSSource", "GenericPageSource", "JuntaProceduresSource"]
