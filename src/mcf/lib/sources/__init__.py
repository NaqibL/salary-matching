"""Job source abstractions for multi-source job aggregation."""

from mcf.lib.sources.base import JobSource, NormalizedJob
from mcf.lib.sources.cag_source import CareersGovJobSource
from mcf.lib.sources.mcf_source import MCFJobSource

__all__ = ["JobSource", "NormalizedJob", "MCFJobSource", "CareersGovJobSource"]
