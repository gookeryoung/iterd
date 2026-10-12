"""reports 插件：迭代对比 diff 与审查报告（生成 / 归档），复用既有插件数据不落新表。"""

from __future__ import annotations

from .schemas import (
    ApprovalSummary,
    ArchiveReportOut,
    EntryDiff,
    IterationBrief,
    IterationDiffOut,
    ReportOut,
    SeverityCounts,
    SimSnapshot,
)

__all__ = [
    "ApprovalSummary",
    "ArchiveReportOut",
    "EntryDiff",
    "IterationBrief",
    "IterationDiffOut",
    "ReportOut",
    "SeverityCounts",
    "SimSnapshot",
]
