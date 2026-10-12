"""reports 对外结构：迭代对比 diff / 审查报告 / 归档结果."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class IterationBrief(BaseModel):
    """迭代简要信息（diff 双方标识）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    title: str
    status: str


class EntryDiff(BaseModel):
    """键控实体集合差异（产物 / BOM 通用）。"""

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []


class SeverityCounts(BaseModel):
    """检查发现项计数（无检查运行时为 null）。"""

    error: int
    warning: int
    info: int


class SimSnapshot(BaseModel):
    """迭代最新仿真结论快照（无仿真作业时为 null）。"""

    verdict: str
    failures: int


class ApprovalSummary(BaseModel):
    """运行审批摘要。"""

    approved: int
    rejected: int
    pending_jobs: int


class IterationDiffOut(BaseModel):
    """迭代对比结果：产物 / BOM 集合差异 + 结论计数 + 审批摘要。"""

    iteration: IterationBrief
    baseline: IterationBrief | None = None
    note: str = ""
    artifacts: EntryDiff
    bom: EntryDiff
    findings: dict[str, SeverityCounts | None]
    sims: dict[str, SimSnapshot | None]
    approvals: dict[str, ApprovalSummary | None]


class ReportOut(BaseModel):
    """审查报告（Markdown 文本）。"""

    iteration_id: int
    generated_at: str
    markdown: str


class ArchiveReportOut(BaseModel):
    """报告归档结果：归档为 result 产物的新版本。"""

    artifact_id: int
    artifact_code: str
    version_no: int


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
