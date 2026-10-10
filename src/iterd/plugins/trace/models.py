"""trace 数据模型：trace_nodes / trace_links."""

from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from iterd.models import Base, TimestampMixin


class TraceNode(Base, TimestampMixin):
    """溯源节点：urn 全局唯一，格式 `urn:iterd:{type}:{uuid}`."""

    __tablename__ = "trace_nodes"

    urn: Mapped[str] = mapped_column(String(128), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    ref_table: Mapped[str] = mapped_column(String(64), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)


class TraceLink(Base, TimestampMixin):
    """溯源边：src/dst 均为 urn."""

    __tablename__ = "trace_links"
    __table_args__ = (UniqueConstraint("src_urn", "dst_urn", "link_type", name="uq_trace_link"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src_urn: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    dst_urn: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)


__all__ = ["TraceLink", "TraceNode"]
