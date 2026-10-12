"""bom 服务层：CSV 解析 / 导入（幂等 upsert）/ 查询."""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import IterdError
from iterd.plugins.bom.models import BomItem

# BOM CSV 必需列（其余列可选：材料/规格/数量/单件重量kg/备注/序号）
REQUIRED_COLUMNS = ("零件编码", "零件名称")


def parse_bom_csv(text: str) -> list[dict[str, str]]:
    """解析 BOM CSV 文本为行字典列表（utf-8-sig 已由调用方解码；表头校验）."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise IterdError("BOM CSV 为空", code="ITERD-BOM_CSV_INVALID", status_code=422)
    missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise IterdError(f"BOM CSV 缺少必需列: {'、'.join(missing)}", code="ITERD-BOM_CSV_INVALID", status_code=422)
    return [dict(row) for row in reader if any((v or "").strip() for v in row.values())]


def _parse_quantity(value: str) -> int:
    """数量列转正整数（缺省 1，非法值报错）。"""
    text = (value or "").strip()
    if not text:
        return 1
    try:
        number = int(float(text))
    except ValueError as exc:
        raise IterdError(f"BOM 数量非法: {text!r}", code="ITERD-BOM_CSV_INVALID", status_code=422) from exc
    if number <= 0:
        raise IterdError(f"BOM 数量必须为正数: {text!r}", code="ITERD-BOM_CSV_INVALID", status_code=422)
    return number


def _parse_unit_weight(value: str) -> float | None:
    """单件重量列转数值（缺省 None，非法值报错）。"""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise IterdError(f"BOM 单件重量非法: {text!r}", code="ITERD-BOM_CSV_INVALID", status_code=422) from exc


async def import_bom(
    session: AsyncSession,
    *,
    project_id: int,
    iteration_id: int,
    rows: list[dict[str, str]],
    actor_id: int,
) -> dict[str, int]:
    """按（迭代, 零件编码）幂等 upsert 导入 BOM 行，返回新建/更新计数.

    同一零件编码重复导入时更新其余字段而非报错，支持清单修订后重传。
    """
    existing = {
        item.part_code: item
        for item in (await session.execute(select(BomItem).where(BomItem.iteration_id == iteration_id))).scalars()
    }
    created = updated = 0
    for row in rows:
        part_code = (row.get("零件编码") or "").strip()
        part_name = (row.get("零件名称") or "").strip()
        if not part_code or not part_name:
            raise IterdError("BOM 行缺少零件编码或零件名称", code="ITERD-BOM_CSV_INVALID", status_code=422)
        fields = {
            "part_name": part_name,
            "material": (row.get("材料") or "").strip(),
            "spec": (row.get("规格") or "").strip(),
            "quantity": _parse_quantity(row.get("数量", "")),
            "unit_weight": _parse_unit_weight(row.get("单件重量kg", "")),
            "note": (row.get("备注") or "").strip(),
        }
        item = existing.get(part_code)
        if item is None:
            session.add(BomItem(project_id=project_id, iteration_id=iteration_id, part_code=part_code, **fields))
            created += 1
        else:
            for key, value in fields.items():
                setattr(item, key, value)
            updated += 1
    from iterd.plugins.notify import audit

    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="bom.import",
        resource_type="bom",
        resource_id=str(iteration_id),
        after={"created": created, "updated": updated, "total": created + updated},
    )
    return {"created": created, "updated": updated, "total": created + updated}


async def list_bom(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    iteration_id: int | None = None,
) -> list[BomItem]:
    """BOM 行列表（按项目 / 迭代过滤，行序号升序）。"""
    stmt = select(BomItem).order_by(BomItem.id)
    if project_id is not None:
        stmt = stmt.where(BomItem.project_id == project_id)
    if iteration_id is not None:
        stmt = stmt.where(BomItem.iteration_id == iteration_id)
    return list((await session.execute(stmt)).scalars())


async def bom_item_refs(session: AsyncSession, iteration_id: int) -> list[dict[str, Any]]:
    """迭代 BOM 行的检查器输入引用（按载入顺序）。"""
    return [
        {
            "part_code": item.part_code,
            "part_name": item.part_name,
            "material": item.material,
            "spec": item.spec,
            "quantity": item.quantity,
            "unit_weight": item.unit_weight,
            "note": item.note,
        }
        for item in await list_bom(session, iteration_id=iteration_id)
    ]


__all__ = ["REQUIRED_COLUMNS", "bom_item_refs", "import_bom", "list_bom", "parse_bom_csv"]
