"""BOM 数据模型：物料清单行（项目 / 迭代维度的零件台账）."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from iterd.models import Base, TimestampMixin


class BomItem(Base, TimestampMixin):
    """BOM 行：迭代内唯一零件编码，数量与单件重量供一致性检查使用."""

    __tablename__ = "bom_items"
    __table_args__ = (UniqueConstraint("iteration_id", "part_code", name="uq_bom_item_part"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("iterations.id"), index=True, nullable=False)
    part_code: Mapped[str] = mapped_column(String(64), nullable=False)
    part_name: Mapped[str] = mapped_column(String(128), nullable=False)
    material: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    spec: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(String(512), default="", nullable=False)


__all__ = ["BomItem"]
