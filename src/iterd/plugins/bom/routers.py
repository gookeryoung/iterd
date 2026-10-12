"""bom 路由：清单查询与 CSV 导入."""

from __future__ import annotations

from fastapi import APIRouter, Query, UploadFile
from pydantic import BaseModel, ConfigDict

from iterd.api.deps import CurrentUser, SessionDep
from iterd.core.errors import IterdError, permission_denied
from iterd.plugins.bom import services
from iterd.plugins.bom.models import BomItem
from iterd.plugins.projects import rbac
from iterd.plugins.projects import services as project_services

router = APIRouter(prefix="/api/v1", tags=["bom"])


class BomItemOut(BaseModel):
    """BOM 行对外结构."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    iteration_id: int
    part_code: str
    part_name: str
    material: str
    spec: str
    quantity: int
    unit_weight: float | None
    note: str


class BomImportOut(BaseModel):
    """BOM 导入结果."""

    created: int
    updated: int
    total: int


async def _require_read(session: SessionDep, user: CurrentUser, project_id: int) -> None:
    """BOM 读取权限：项目 viewer+。"""
    await rbac.require_project_role(
        session, project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )


@router.get("/bom", response_model=list[BomItemOut])
async def list_bom(
    _user: CurrentUser,
    session: SessionDep,
    project_id: int | None = None,
    iteration_id: int | None = None,
) -> list[BomItemOut]:
    """BOM 行列表（按项目 / 迭代过滤；项目级 viewer+ 可见）。"""
    resolved_project = project_id
    if resolved_project is None and iteration_id is not None:
        iteration = await project_services.get_iteration(session, iteration_id)
        resolved_project = iteration.project_id
    if resolved_project is not None:
        await _require_read(session, _user, resolved_project)
    elif project_id is None and iteration_id is None:
        raise permission_denied("请指定 project_id 或 iteration_id")
    items = await services.list_bom(session, project_id=project_id, iteration_id=iteration_id)
    return [BomItemOut.model_validate(item) for item in items]


@router.post("/bom/import", response_model=BomImportOut, status_code=201)
async def import_bom(
    file: UploadFile,
    user: CurrentUser,
    session: SessionDep,
    project_id: int = Query(...),
    iteration_id: int = Query(...),
) -> BomImportOut:
    """CSV 导入 BOM（designer+；按零件编码幂等 upsert）."""
    iteration = await project_services.get_iteration(session, iteration_id)
    if iteration.project_id != project_id:
        raise IterdError(f"迭代 {iteration_id} 不属于项目 {project_id}", code="ITERD-NOT_FOUND", status_code=404)
    await rbac.require_project_role(
        session, project_id, user.id, "designer", is_superuser=user.is_superuser, include_ancestor=True
    )
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IterdError("BOM CSV 编码应为 UTF-8", code="ITERD-BOM_CSV_INVALID", status_code=422) from exc
    rows = services.parse_bom_csv(text)
    result = await services.import_bom(
        session, project_id=project_id, iteration_id=iteration_id, rows=rows, actor_id=user.id
    )
    await session.commit()
    return BomImportOut(**result)


__all__ = ["BomItem", "router"]
