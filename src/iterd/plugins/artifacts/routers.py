"""artifacts 路由：上传 / 下载 / 版本 / 元数据 / 关联 / 软删."""

from __future__ import annotations

import io

from fastapi import APIRouter, File, Form, Response, UploadFile

from iterd.api.deps import CurrentUser, SessionDep
from iterd.core.errors import not_found
from iterd.core.storage import get_storage
from iterd.plugins.artifacts import schemas, services
from iterd.plugins.projects import rbac
from iterd.plugins.projects import services as project_services

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


@router.get("/artifacts", response_model=list[schemas.ArtifactOut])
async def list_artifacts(
    user: CurrentUser, session: SessionDep, iteration_id: int | None = None, project_id: int | None = None
) -> list[schemas.ArtifactOut]:
    """产物列表（viewer+；iteration_id/project_id 至少给一个）。"""
    if iteration_id is None and project_id is None:
        raise not_found("请指定 iteration_id 或 project_id")
    scope_project = project_id
    if iteration_id is not None:
        iteration = await project_services.get_iteration(session, iteration_id)
        scope_project = iteration.project_id
    assert scope_project is not None
    await rbac.require_project_role(
        session, scope_project, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    artifacts = await services.list_artifacts(session, iteration_id=iteration_id, project_id=project_id)
    return [schemas.ArtifactOut.model_validate(a) for a in artifacts]


@router.post("/artifacts", response_model=schemas.ArtifactOut, status_code=201)
async def create_artifact(
    body: schemas.ArtifactIn, user: CurrentUser, session: SessionDep, iteration_id: int
) -> schemas.ArtifactOut:
    """创建产物（designer+）。"""
    iteration = await project_services.get_iteration(session, iteration_id)
    await rbac.require_project_role(session, iteration.project_id, user.id, "designer", is_superuser=user.is_superuser)
    artifact = await services.create_artifact(
        session,
        actor_id=user.id,
        project_id=iteration.project_id,
        iteration_id=iteration_id,
        **body.model_dump(exclude={"metadata"}),
    )
    await session.commit()
    return schemas.ArtifactOut.model_validate(artifact)


@router.post("/artifacts/{artifact_id}/versions", response_model=schemas.ArtifactVersionOut, status_code=201)
async def upload_version(  # noqa: PLR0913, PLR0917 - FastAPI 表单参数
    artifact_id: int,
    user: CurrentUser,
    session: SessionDep,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI 表单依赖
    note: str = Form(""),
    metadata: str = Form(""),
) -> schemas.ArtifactVersionOut:
    """上传新版本（designer+）；同内容自动去重."""
    import json

    artifact = await services.get_artifact(session, artifact_id)
    await rbac.require_project_role(session, artifact.project_id, user.id, "designer", is_superuser=user.is_superuser)
    metadata_dict = json.loads(metadata) if metadata else None
    version = await services.upload_version(
        session,
        actor_id=user.id,
        artifact=artifact,
        filename=file.filename or "unnamed",
        content_type=file.content_type or "",
        stream=io.BytesIO(await file.read()),
        metadata=metadata_dict,
        note=note,
    )
    await session.commit()
    return schemas.ArtifactVersionOut.model_validate(version)


@router.get("/artifacts/{artifact_id}/versions", response_model=list[schemas.ArtifactVersionOut])
async def list_versions(artifact_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.ArtifactVersionOut]:
    """版本历史（viewer+）。"""
    artifact = await services.get_artifact(session, artifact_id)
    await rbac.require_project_role(
        session, artifact.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    versions = await services.list_versions(session, artifact_id)
    return [schemas.ArtifactVersionOut.model_validate(v) for v in versions]


@router.get("/versions/{version_id}/download")
async def download_version(version_id: int, user: CurrentUser, session: SessionDep) -> Response:
    """下载版本内容（viewer+）。"""
    version = await services.get_version(session, version_id)
    artifact = await services.get_artifact(session, version.artifact_id)
    await rbac.require_project_role(
        session, artifact.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    data = get_storage().open(version.storage_key).read()
    return Response(
        content=data,
        media_type=version.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{version.filename}"'},
    )


@router.get("/artifacts/{artifact_id}", response_model=schemas.ArtifactOut)
async def get_artifact(artifact_id: int, user: CurrentUser, session: SessionDep) -> schemas.ArtifactOut:
    """产物详情（viewer+；软删后 404）。"""
    artifact = await services.get_artifact(session, artifact_id)
    await rbac.require_project_role(
        session, artifact.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    return schemas.ArtifactOut.model_validate(artifact)


@router.patch("/artifacts/{artifact_id}", response_model=schemas.ArtifactOut)
async def update_artifact(
    artifact_id: int, body: schemas.ArtifactUpdate, user: CurrentUser, session: SessionDep
) -> schemas.ArtifactOut:
    """更新产物名称/描述/元数据（designer+）。"""
    artifact = await services.get_artifact(session, artifact_id)
    await rbac.require_project_role(session, artifact.project_id, user.id, "designer", is_superuser=user.is_superuser)
    updated = await services.update_metadata(
        session, actor_id=user.id, artifact=artifact, fields=body.model_dump(exclude_unset=True)
    )
    await session.commit()
    return schemas.ArtifactOut.model_validate(updated)


@router.delete("/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(artifact_id: int, user: CurrentUser, session: SessionDep) -> None:
    """软删产物（reviewer+）；历史版本保留。"""
    artifact = await services.get_artifact(session, artifact_id)
    await rbac.require_project_role(session, artifact.project_id, user.id, "reviewer", is_superuser=user.is_superuser)
    await services.soft_delete_artifact(session, actor_id=user.id, artifact=artifact)
    await session.commit()


@router.get("/artifacts/{artifact_id}/links", response_model=list[schemas.ArtifactLinkOut])
async def list_links(artifact_id: int, user: CurrentUser, session: SessionDep) -> list[schemas.ArtifactLinkOut]:
    """产物关联列表（viewer+）。"""
    artifact = await services.get_artifact(session, artifact_id)
    await rbac.require_project_role(
        session, artifact.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    links = await services.list_links(session, artifact_id)
    return [schemas.ArtifactLinkOut.model_validate(link) for link in links]


@router.post("/artifacts/{artifact_id}/links", response_model=schemas.ArtifactLinkOut, status_code=201)
async def create_link(
    artifact_id: int, body: schemas.ArtifactLinkIn, user: CurrentUser, session: SessionDep
) -> schemas.ArtifactLinkOut:
    """创建产物关联（designer+）。"""
    artifact = await services.get_artifact(session, artifact_id)
    await rbac.require_project_role(session, artifact.project_id, user.id, "designer", is_superuser=user.is_superuser)
    link = await services.create_link(
        session,
        actor_id=user.id,
        src_artifact_id=artifact_id,
        dst_artifact_id=body.dst_artifact_id,
        link_type=body.link_type,
    )
    await session.commit()
    return schemas.ArtifactLinkOut.model_validate(link)


@router.get("/versions/{version_id}", response_model=schemas.ArtifactVersionOut)
async def get_version(version_id: int, user: CurrentUser, session: SessionDep) -> schemas.ArtifactVersionOut:
    """版本详情（viewer+）。"""
    version = await services.get_version(session, version_id)
    artifact = await services.get_artifact(session, version.artifact_id)
    await rbac.require_project_role(
        session, artifact.project_id, user.id, "viewer", is_superuser=user.is_superuser, include_ancestor=True
    )
    return schemas.ArtifactVersionOut.model_validate(version)
