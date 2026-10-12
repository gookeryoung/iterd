"""trace 服务：注册与关联（与业务写操作同事务）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from iterd.models.base import new_uid
from iterd.plugins.trace.models import TraceLink, TraceNode

NODE_TYPES = (
    "project",
    "iteration",
    "artifact_version",
    "rule_item",
    "submission",
    "check_finding",
    "sim_template",
    "sim_job",
    "sim_result",
)

# 递归方向 -> (边条件模板, 下一跳列)；w 为递归工作表别名
_DIRECTIONS = {
    "up": ("l.dst_urn = w.urn", "l.src_urn"),
    "down": ("l.src_urn = w.urn", "l.dst_urn"),
}

# 递归 CTE 公共片段：从根出发展开可达 URN 集合
_WALK_CTE = """
WITH RECURSIVE walk(urn) AS (
    SELECT :root
    UNION
    SELECT {next_col} FROM trace_links l JOIN walk w ON {join_cond}
)
"""


def build_urn(node_type: str) -> str:
    """生成新 URN：`urn:iterd:{type}:{uuid}`."""
    return f"urn:iterd:{node_type}:{new_uid()}"


async def register(  # noqa: PLR0913 - 溯源节点字段
    session: AsyncSession,
    *,
    node_type: str,
    ref_table: str,
    ref_id: int | str,
    display_name: str,
    urn: str | None = None,
) -> str:
    """注册溯源节点（同事务，不 commit）；urn 可由调用方传入以便业务表冗余存储."""
    urn = urn or build_urn(node_type)
    session.add(
        TraceNode(urn=urn, node_type=node_type, display_name=display_name, ref_table=ref_table, ref_id=str(ref_id))
    )
    return urn


async def ensure_link(session: AsyncSession, *, src: str, dst: str, link_type: str) -> None:
    """建立关联（幂等：重复关联忽略）。"""
    exists = (
        await session.execute(
            select(TraceLink.id).where(
                TraceLink.src_urn == src, TraceLink.dst_urn == dst, TraceLink.link_type == link_type
            )
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(TraceLink(src_urn=src, dst_urn=dst, link_type=link_type))


async def delete_node(session: AsyncSession, urn: str) -> None:
    """删除节点及其关联边（业务级联时调用）。"""
    await session.execute(delete(TraceLink).where(TraceLink.src_urn == urn))
    await session.execute(delete(TraceLink).where(TraceLink.dst_urn == urn))
    await session.execute(delete(TraceNode).where(TraceNode.urn == urn))


async def trace_graph(
    session: AsyncSession, *, urn: str, direction: str = "both", depth: int = 5
) -> dict[str, list[dict[str, Any]]]:
    """递归 CTE 追溯查询：给定节点向上/向下/双向展开，返回节点与边（去重防环）."""
    if direction == "both":
        down = await trace_graph(session, urn=urn, direction="down", depth=depth)
        up = await trace_graph(session, urn=urn, direction="up", depth=depth)
        nodes = {n["urn"]: n for n in down["nodes"] + up["nodes"]}
        edges = {f"{e['src']}|{e['dst']}|{e['type']}": e for e in down["edges"] + up["edges"]}
        return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    join_cond, next_col = _DIRECTIONS[direction]
    nodes_sql = text(_WALK_CTE.format(next_col=next_col, join_cond=join_cond) + """
        SELECT DISTINCT n.urn, n.node_type, n.display_name FROM walk
        JOIN trace_nodes n ON n.urn = walk.urn
    """)
    rows = (await session.execute(nodes_sql, {"root": urn})).all()
    nodes = [{"urn": r[0], "node_type": r[1], "display_name": r[2]} for r in rows]
    # 边查询同样限定在 walk 可达集合内，避免全表边加载（大规模数据下的性能瓶颈）
    edges_sql = text(_WALK_CTE.format(next_col=next_col, join_cond=join_cond) + """
        SELECT DISTINCT l.src_urn, l.dst_urn, l.link_type FROM trace_links l
        JOIN walk a ON a.urn = l.src_urn
        JOIN walk b ON b.urn = l.dst_urn
    """)
    edge_rows = (await session.execute(edges_sql, {"root": urn})).all()
    edges = [{"src": e[0], "dst": e[1], "type": e[2]} for e in edge_rows]
    return {"nodes": nodes, "edges": edges}
