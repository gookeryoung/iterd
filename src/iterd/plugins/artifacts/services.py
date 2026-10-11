"""artifacts 服务层：产物 / 版本上传（内容寻址）/ 关联."""

from __future__ import annotations

from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.core.errors import IterdError, not_found
from iterd.core.storage import get_storage
from iterd.plugins.artifacts.models import LINK_TYPES, Artifact, ArtifactLink, ArtifactVersion
from iterd.plugins.notify import audit
from iterd.plugins.trace import ensure_link, register


async def get_artifact(session: AsyncSession, artifact_id: int) -> Artifact:
    """取产物，不存在或已软删抛 404."""
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None or artifact.deleted_at is not None:
        raise not_found(f"产物不存在: {artifact_id}")
    return artifact


async def list_artifacts(
    session: AsyncSession, *, iteration_id: int | None = None, project_id: int | None = None
) -> list[Artifact]:
    """产物列表（排除软删）。"""
    stmt = select(Artifact).where(Artifact.deleted_at.is_(None)).order_by(Artifact.id)
    if iteration_id is not None:
        stmt = stmt.where(Artifact.iteration_id == iteration_id)
    if project_id is not None:
        stmt = stmt.where(Artifact.project_id == project_id)
    return list((await session.execute(stmt)).scalars())


async def create_artifact(session: AsyncSession, *, actor_id: int, **fields: object) -> Artifact:
    """创建产物（项目内 code 唯一）。"""
    dup = (
        await session.execute(
            select(Artifact.id).where(
                Artifact.project_id == fields["project_id"],
                Artifact.code == fields["code"],
                Artifact.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise IterdError(f"产物编码已存在: {fields['code']}", code="ITERD-DUPLICATE_CODE")
    artifact = Artifact(**fields)  # type: ignore[arg-type]
    session.add(artifact)
    await session.flush()
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="artifact.create",
        resource_type="artifact",
        resource_id=artifact.id,
        after={"code": artifact.code},
    )
    return artifact


async def upload_version(  # noqa: PLR0913 - 上传参数
    session: AsyncSession,
    *,
    actor_id: int,
    artifact: Artifact,
    filename: str,
    content_type: str,
    stream: BinaryIO,
    metadata: dict[str, object] | None = None,
    note: str = "",
) -> ArtifactVersion:
    """上传新版本：内容寻址去重，version_no 递增，更新 current_version_id."""
    obj = get_storage().put(filename, stream)
    last_no = (
        await session.execute(
            select(func.max(ArtifactVersion.version_no)).where(ArtifactVersion.artifact_id == artifact.id)
        )
    ).scalar_one()
    version = ArtifactVersion(
        artifact_id=artifact.id,
        version_no=(last_no or 0) + 1,
        filename=filename,
        content_type=content_type,
        size=obj.size,
        sha256=obj.sha256,
        storage_key=obj.sha256,
        metadata_json=metadata,
        uploaded_by=actor_id,
        note=note,
    )
    session.add(version)
    await session.flush()
    artifact.current_version_id = version.id
    urn = await register(
        session,
        node_type="artifact_version",
        ref_table="artifact_versions",
        ref_id=version.id,
        display_name=f"{artifact.code} v{version.version_no}",
    )
    await _link_iteration(session, artifact, urn)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="artifact.upload",
        resource_type="artifact",
        resource_id=artifact.id,
        after={"version_no": version.version_no, "sha256": obj.sha256, "urn": urn},
    )
    return version


async def _link_iteration(session: AsyncSession, artifact: Artifact, version_urn: str) -> None:
    from iterd.plugins.trace.models import TraceNode

    iteration_urn = (
        await session.execute(
            select(TraceNode.urn).where(
                TraceNode.ref_table == "iterations", TraceNode.ref_id == str(artifact.iteration_id)
            )
        )
    ).scalar_one_or_none()
    if iteration_urn is not None:
        await ensure_link(session, src=iteration_urn, dst=version_urn, link_type="contains")


# 在线预览：P0 基础版仅支持图片 / PDF / 文本类（含 Markdown），其余类型返回 415
PREVIEW_MAX_SIZE = 20 * 1024 * 1024
PREVIEW_MIME_PREFIXES = ("image/", "text/")
PREVIEW_EXACT_MIMES = ("application/pdf", "application/json", "application/xml")
PREVIEW_TEXT_EXTENSIONS = (".md", ".markdown", ".txt", ".csv", ".log", ".json", ".xml", ".yaml", ".yml")


async def resolve_preview(version: ArtifactVersion) -> tuple[str, str]:
    """判定版本可否在线预览，返回 (预览类型, 响应 content_type)。

    预览类型：image / pdf / text；不可预览抛 415，过大抛 413。
    """
    if version.size > PREVIEW_MAX_SIZE:
        raise IterdError("文件过大，不支持在线预览（上限 20MB）", code="ITERD-PREVIEW_UNSUPPORTED", status_code=413)
    filename = version.filename.lower()
    content_type = (version.content_type or "").split(";")[0].strip().lower()
    if content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
        return "image", content_type or "image/*"
    if content_type == "application/pdf" or filename.endswith(".pdf"):
        return "pdf", "application/pdf"
    if content_type.startswith("text/") or filename.endswith(PREVIEW_TEXT_EXTENSIONS):
        if filename.endswith((".md", ".markdown")):
            return "text", "text/markdown; charset=utf-8"
        return "text", "text/plain; charset=utf-8"
    if content_type in PREVIEW_EXACT_MIMES:
        return "text", "text/plain; charset=utf-8"
    raise IterdError(
        f"该类型不支持在线预览: {version.content_type or version.filename}",
        code="ITERD-PREVIEW_UNSUPPORTED",
        status_code=415,
    )


async def get_version(session: AsyncSession, version_id: int) -> ArtifactVersion:
    """取版本记录，不存在抛 404."""
    version = await session.get(ArtifactVersion, version_id)
    if version is None:
        raise not_found(f"版本不存在: {version_id}")
    return version


async def list_versions(session: AsyncSession, artifact_id: int) -> list[ArtifactVersion]:
    """版本历史（递增序）。"""
    return list(
        (
            await session.execute(
                select(ArtifactVersion)
                .where(ArtifactVersion.artifact_id == artifact_id)
                .order_by(ArtifactVersion.version_no)
            )
        ).scalars()
    )


async def soft_delete_artifact(session: AsyncSession, *, actor_id: int, artifact: Artifact) -> None:
    """软删产物：历史版本与存储对象保留。"""
    from datetime import UTC, datetime

    artifact.deleted_at = datetime.now(UTC)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="artifact.delete",
        resource_type="artifact",
        resource_id=artifact.id,
        before={"code": artifact.code},
    )


async def update_metadata(
    session: AsyncSession, *, actor_id: int, artifact: Artifact, fields: dict[str, object]
) -> Artifact:
    """更新产物名称/描述/元数据（当前版本元数据一并回填，人工值优先）。"""
    before = {"name": artifact.name, "description": artifact.description}
    if "name" in fields and fields["name"] is not None:
        artifact.name = str(fields["name"])  # type: ignore[arg-type]
    if "description" in fields and fields["description"] is not None:
        artifact.description = str(fields["description"])  # type: ignore[arg-type]
    if "category" in fields and fields["category"] is not None:
        artifact.category = str(fields["category"])  # type: ignore[arg-type]
    if "metadata" in fields and fields["metadata"] is not None and artifact.current_version_id is not None:
        version = await session.get(ArtifactVersion, artifact.current_version_id)
        if version is not None:
            version.metadata_json = fields["metadata"]  # type: ignore[assignment]
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="artifact.update",
        resource_type="artifact",
        resource_id=artifact.id,
        before=before,
        after={k: str(v) for k, v in fields.items()},
    )
    return artifact


async def create_link(
    session: AsyncSession, *, actor_id: int, src_artifact_id: int, dst_artifact_id: int, link_type: str
) -> ArtifactLink:
    """创建产物关联，同步 trace derives_from 语义映射."""
    if link_type not in LINK_TYPES:
        raise IterdError(f"不支持的关联类型: {link_type}")
    src = await get_artifact(session, src_artifact_id)
    dst = await get_artifact(session, dst_artifact_id)
    if src.id == dst.id:
        raise IterdError("产物不能与自身建立关联", code="ITERD-INVALID_STATE")
    dup = (
        await session.execute(
            select(ArtifactLink.id).where(
                ArtifactLink.src_artifact_id == src_artifact_id,
                ArtifactLink.dst_artifact_id == dst_artifact_id,
                ArtifactLink.link_type == link_type,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise IterdError("关联已存在", code="ITERD-DUPLICATE_CODE")
    link = ArtifactLink(src_artifact_id=src_artifact_id, dst_artifact_id=dst_artifact_id, link_type=link_type)
    session.add(link)
    await session.flush()
    await _trace_link_artifacts(session, link)
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="artifact.link",
        resource_type="artifact",
        resource_id=src_artifact_id,
        after={"dst": dst_artifact_id, "link_type": link_type},
    )
    return link


async def _trace_link_artifacts(session: AsyncSession, link: ArtifactLink) -> None:
    """产物关联同步到溯源图：当前版本节点间建立 derived_from 边."""
    src_urn = await _current_version_urn(session, link.src_artifact_id)
    dst_urn = await _current_version_urn(session, link.dst_artifact_id)
    if src_urn and dst_urn:
        await ensure_link(session, src=src_urn, dst=dst_urn, link_type="derived_from")


async def _current_version_urn(session: AsyncSession, artifact_id: int) -> str | None:
    from iterd.plugins.trace.models import TraceNode

    artifact = await session.get(Artifact, artifact_id)
    if artifact is None or artifact.current_version_id is None:
        return None
    return (
        await session.execute(
            select(TraceNode.urn).where(
                TraceNode.ref_table == "artifact_versions", TraceNode.ref_id == str(artifact.current_version_id)
            )
        )
    ).scalar_one_or_none()


async def delete_link(session: AsyncSession, *, actor_id: int, artifact_id: int, link_id: int) -> None:
    """删除产物关联（仅限以本产物为端点之一的关联），同步审计。"""
    link = await session.get(ArtifactLink, link_id)
    if link is None or artifact_id not in (link.src_artifact_id, link.dst_artifact_id):
        raise not_found(f"关联不存在: {link_id}")
    await session.delete(link)
    await session.flush()
    await audit(
        session,
        actor_id=actor_id,
        actor_name="",
        action="artifact.unlink",
        resource_type="artifact",
        resource_id=artifact_id,
        before={"link_id": link_id, "link_type": link.link_type},
    )


async def get_artifact_labels(session: AsyncSession, artifact_ids: list[int]) -> dict[int, tuple[str, str]]:
    """批量取产物编码与名称（关联列表展示用）。"""
    if not artifact_ids:
        return {}
    rows = (
        await session.execute(
            select(Artifact.id, Artifact.code, Artifact.name).where(Artifact.id.in_(set(artifact_ids)))
        )
    ).all()
    return {int(row[0]): (str(row[1]), str(row[2])) for row in rows}


async def list_links(session: AsyncSession, artifact_id: int) -> list[ArtifactLink]:
    """产物关联列表（双向）。"""
    return list(
        (
            await session.execute(
                select(ArtifactLink).where(
                    (ArtifactLink.src_artifact_id == artifact_id) | (ArtifactLink.dst_artifact_id == artifact_id)
                )
            )
        ).scalars()
    )
