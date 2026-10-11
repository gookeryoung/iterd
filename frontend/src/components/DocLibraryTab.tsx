/** 项目工作区 - 文档库 Tab：类别维度筛选 + 图样树/文档列表双视图 + 审查状态徽标与未通过明细。 */

import { useMemo, useState } from 'react';
import { Drawer, Space, Switch, Table, Tag, Tree, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { DataNode } from 'antd/es/tree';
import { useQuery } from '@tanstack/react-query';
import {
  fetchArtifacts,
  fetchProjectLinks,
  fetchProjectReviewStatus,
} from '../api/artifacts';
import { fetchIterations } from '../api/projects';
import type { Artifact, ArtifactCategory, ArtifactReviewStatus, ReviewFinding } from '../types';
import { ARTIFACT_CATEGORY_LABELS } from '../types';
import { CategoryTag, ReviewStatusTag, SeverityTag } from './StatusTags';
import { formatDateTime } from '../utils/format';

type CategoryFilter = 'all' | ArtifactCategory;

/** 文档库 Tab 属性。 */
interface DocLibraryTabProps {
  projectId: number;
}

/** 图样树节点构建中间结构。 */
interface TreeBuildResult {
  treeData: DataNode[];
  /** 无任何 part_of 关联的孤立图样 id（归入「未挂载」分组）。 */
  orphanIds: Set<number>;
}

/** 递归构建子树（环安全：祖先集合截断；多父重复挂载并标记）。 */
function buildChildren(
  parentId: number | null,
  artifacts: Artifact[],
  childrenOf: Map<number, number[]>,
  statusMap: Map<number, ArtifactReviewStatus>,
  multiParentIds: Set<number>,
  ancestors: Set<number>,
  keptIds: Set<number> | null,
): DataNode[] {
  if (parentId === null) {
    return [];
  }
  const childIds = childrenOf.get(parentId) ?? [];
  return childIds
    .filter((id) => !ancestors.has(id))
    .filter((id) => keptIds === null || keptIds.has(id))
    .map((id) => {
      const artifact = artifacts.find((a) => a.id === id);
      if (!artifact) {
        return { key: `node-${id}`, title: `产物 #${id}` };
      }
      const status = statusMap.get(id);
      const childAncestors = new Set(ancestors);
      childAncestors.add(id);
      const children = buildChildren(
        id,
        artifacts,
        childrenOf,
        statusMap,
        multiParentIds,
        childAncestors,
        keptIds,
      );
      return {
        key: `node-${parentId}-${id}`,
        title: (
          <Space size={4}>
            <Typography.Text strong style={{ fontSize: 13 }}>
              {artifact.code}
            </Typography.Text>
            <Typography.Text style={{ fontSize: 13 }}>{artifact.name}</Typography.Text>
            {multiParentIds.has(id) && <Tag color="purple">多父</Tag>}
            {status && <ReviewStatusTag status={status.status} />}
          </Space>
        ),
        children: children.length > 0 ? children : undefined,
      };
    });
}

/** 由 part_of 边 + 图样产物构建树数据（孤立图样归入 orphanIds）。 */
function buildTreeData(
  artifacts: Artifact[],
  links: { id: number; src_artifact_id: number; dst_artifact_id: number }[],
  statusMap: Map<number, ArtifactReviewStatus>,
  keptIds: Set<number> | null,
): TreeBuildResult {
  const drawingIds = new Set(artifacts.filter((a) => a.category === 'drawing').map((a) => a.id));
  const childrenOf = new Map<number, number[]>();
  const hasParent = new Set<number>();
  const parentCount = new Map<number, number>();
  for (const link of links) {
    if (!drawingIds.has(link.src_artifact_id) || !drawingIds.has(link.dst_artifact_id)) {
      continue;
    }
    const siblings = childrenOf.get(link.dst_artifact_id) ?? [];
    siblings.push(link.src_artifact_id);
    childrenOf.set(link.dst_artifact_id, siblings);
    hasParent.add(link.src_artifact_id);
    parentCount.set(link.src_artifact_id, (parentCount.get(link.src_artifact_id) ?? 0) + 1);
  }
  const multiParentIds = new Set(
    [...parentCount.entries()].filter(([, count]) => count > 1).map(([id]) => id),
  );
  const roots = [...drawingIds].filter((id) => !hasParent.has(id));
  const orphanIds = new Set(roots.filter((id) => !childrenOf.has(id)));

  const treeData: DataNode[] = [];
  for (const rootId of roots) {
    if (orphanIds.has(rootId) || (keptIds !== null && !keptIds.has(rootId))) {
      continue;
    }
    const artifact = artifacts.find((a) => a.id === rootId);
    if (!artifact) {
      continue;
    }
    const status = statusMap.get(rootId);
    treeData.push({
      key: `node-root-${rootId}`,
      title: (
        <Space size={4}>
          <Typography.Text strong style={{ fontSize: 13 }}>
            {artifact.code}
          </Typography.Text>
          <Typography.Text style={{ fontSize: 13 }}>{artifact.name}</Typography.Text>
          {multiParentIds.has(rootId) && <Tag color="purple">多父</Tag>}
          {status && <ReviewStatusTag status={status.status} />}
        </Space>
      ),
      children: buildChildren(
        rootId,
        artifacts,
        childrenOf,
        statusMap,
        multiParentIds,
        new Set([rootId]),
        keptIds,
      ),
    });
  }
  return { treeData, orphanIds };
}

/** 计算仅看未通过时的保留集合（失败节点 + 其全部祖先）。 */
function computeKeptIds(
  artifacts: Artifact[],
  links: { id: number; src_artifact_id: number; dst_artifact_id: number }[],
  statusMap: Map<number, ArtifactReviewStatus>,
): Set<number> {
  const failedIds = new Set(
    artifacts.filter((a) => statusMap.get(a.id)?.status === 'failed').map((a) => a.id),
  );
  const parentOf = new Map<number, number[]>();
  for (const link of links) {
    const parents = parentOf.get(link.src_artifact_id) ?? [];
    parents.push(link.dst_artifact_id);
    parentOf.set(link.src_artifact_id, parents);
  }
  const kept = new Set(failedIds);
  const stack = [...failedIds];
  while (stack.length > 0) {
    const id = stack.pop() as number;
    for (const parent of parentOf.get(id) ?? []) {
      if (!kept.has(parent)) {
        kept.add(parent);
        stack.push(parent);
      }
    }
  }
  return kept;
}

export default function DocLibraryTab({ projectId }: DocLibraryTabProps) {
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [findingsTarget, setFindingsTarget] = useState<ArtifactReviewStatus | null>(null);

  const artifactsQuery = useQuery({
    queryKey: ['artifacts', 'project', projectId],
    queryFn: () => fetchArtifacts({ project_id: projectId }),
  });
  const reviewQuery = useQuery({
    queryKey: ['project-review-status', projectId],
    queryFn: () => fetchProjectReviewStatus(projectId),
  });
  const linksQuery = useQuery({
    queryKey: ['project-links', projectId],
    queryFn: () => fetchProjectLinks(projectId),
  });
  const iterationsQuery = useQuery({
    queryKey: ['iterations', projectId],
    queryFn: () => fetchIterations(projectId),
  });

  const artifacts = artifactsQuery.data ?? [];
  const statusList = reviewQuery.data ?? [];
  const links = linksQuery.data ?? [];
  const statusMap = useMemo(
    () => new Map(statusList.map((item) => [item.artifact_id, item])),
    [statusList],
  );
  const iterationLabel = useMemo(() => {
    const map = new Map<number, string>();
    for (const it of iterationsQuery.data ?? []) {
      map.set(it.id, `#${it.number} ${it.title}`);
    }
    return map;
  }, [iterationsQuery.data]);

  const visibleArtifacts = useMemo(() => {
    let list = artifacts;
    if (category !== 'all') {
      list = list.filter((a) => a.category === category);
    }
    if (onlyFailed) {
      list = list.filter((a) => statusMap.get(a.id)?.status === 'failed');
    }
    return list;
  }, [artifacts, category, onlyFailed, statusMap]);

  const isTreeMode = category === 'drawing';
  const keptIds = useMemo(
    () => (onlyFailed ? computeKeptIds(artifacts, links, statusMap) : null),
    [onlyFailed, artifacts, links, statusMap],
  );
  const treeBuild = useMemo(
    () => (isTreeMode ? buildTreeData(artifacts, links, statusMap, keptIds) : null),
    [isTreeMode, artifacts, links, statusMap, keptIds],
  );

  const orphanNodes: DataNode[] = useMemo(() => {
    if (!treeBuild || treeBuild.orphanIds.size === 0) {
      return [];
    }
    return [...treeBuild.orphanIds]
      .filter((id) => keptIds === null || keptIds.has(id))
      .map((id) => {
        const artifact = artifacts.find((a) => a.id === id);
        const status = statusMap.get(id);
        return {
          key: `orphan-${id}`,
          title: (
            <Space size={4}>
              <Typography.Text strong style={{ fontSize: 13 }}>
                {artifact?.code ?? `#${id}`}
              </Typography.Text>
              <Typography.Text style={{ fontSize: 13 }}>{artifact?.name ?? ''}</Typography.Text>
              {status && <ReviewStatusTag status={status.status} />}
            </Space>
          ),
        };
      });
  }, [treeBuild, artifacts, statusMap, keptIds]);

  const listColumns: ColumnsType<Artifact> = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 140 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 110,
      render: (value: ArtifactCategory) => <CategoryTag category={value} />,
    },
    {
      title: '所属迭代',
      dataIndex: 'iteration_id',
      key: 'iteration_id',
      width: 200,
      render: (value: number) => iterationLabel.get(value) ?? `#${value}`,
    },
    {
      title: '审查状态',
      key: 'review',
      width: 120,
      render: (_: unknown, record: Artifact) => {
        const status = statusMap.get(record.id);
        return status ? <ReviewStatusTag status={status.status} /> : <Tag>加载中</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: Artifact) => {
        const status = statusMap.get(record.id);
        if (!status) {
          return null;
        }
        return (
          <Typography.Link onClick={() => setFindingsTarget(status)}>
            审查明细
          </Typography.Link>
        );
      },
    },
  ];

  const findingColumns: ColumnsType<ReviewFinding> = [
    {
      title: '规则',
      key: 'rule',
      width: 200,
      render: (_: unknown, record: ReviewFinding) => `${record.rule_code} ${record.rule_name}`,
    },
    {
      title: '严重度',
      dataIndex: 'severity',
      key: 'severity',
      width: 90,
      render: (value: ReviewFinding['severity']) => <SeverityTag severity={value} />,
    },
    { title: '位置', dataIndex: 'location', key: 'location', width: 140 },
    { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true },
    {
      title: '版本',
      dataIndex: 'version_no',
      key: 'version_no',
      width: 80,
      render: (value: number) => `v${value}`,
    },
    {
      title: '检查运行',
      dataIndex: 'check_run_id',
      key: 'check_run_id',
      width: 100,
      render: (value: number) => `#${value}`,
    },
  ];

  const categoryOptions: { label: string; value: CategoryFilter }[] = [
    { label: '全部', value: 'all' },
    ...(Object.entries(ARTIFACT_CATEGORY_LABELS) as [ArtifactCategory, string][]).map(
      ([value, label]) => ({ label, value }),
    ),
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Space.Compact>
          {categoryOptions.map((option) => (
            <Tag.CheckableTag
              key={option.value}
              checked={category === option.value}
              onChange={() => setCategory(option.value)}
              style={{ fontSize: 13 }}
            >
              {option.label}
            </Tag.CheckableTag>
          ))}
        </Space.Compact>
        <Space size={8} style={{ marginLeft: 12 }}>
          <Switch checked={onlyFailed} onChange={setOnlyFailed} />
          <Typography.Text type={onlyFailed ? 'danger' : 'secondary'}>仅看未通过</Typography.Text>
        </Space>
      </Space>

      {isTreeMode ? (
        <div>
          {treeBuild && treeBuild.treeData.length === 0 && treeBuild.orphanIds.size === 0 && (
            <Typography.Text type="secondary">暂无图样类产物</Typography.Text>
          )}
          {treeBuild && treeBuild.treeData.length > 0 && (
            <Tree treeData={treeBuild.treeData} defaultExpandAll blockNode selectable={false} />
          )}
          {orphanNodes.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Typography.Text type="secondary">未挂载（无 part_of 关联）</Typography.Text>
              <Tree treeData={orphanNodes} selectable={false} />
            </div>
          )}
        </div>
      ) : (
        <Table<Artifact>
          rowKey="id"
          columns={listColumns}
          dataSource={visibleArtifacts}
          loading={artifactsQuery.isPending || reviewQuery.isPending}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无产物' }}
        />
      )}

      <Drawer
        title={`审查明细${findingsTarget ? ` - ${findingsTarget.code} ${findingsTarget.name}` : ''}`}
        width={880}
        open={findingsTarget !== null}
        onClose={() => setFindingsTarget(null)}
      >
        {findingsTarget && (
          <div>
            <Space size={8} style={{ marginBottom: 16 }}>
              <ReviewStatusTag status={findingsTarget.status} />
              {findingsTarget.last_checked_at && (
                <Typography.Text type="secondary">
                  最近检查：{formatDateTime(findingsTarget.last_checked_at)}（运行 #
                  {findingsTarget.check_run_id}）
                </Typography.Text>
              )}
            </Space>
            <Table<ReviewFinding>
              rowKey="id"
              columns={findingColumns}
              dataSource={findingsTarget.findings}
              pagination={false}
              size="small"
              locale={{
                emptyText:
                  findingsTarget.status === 'failed'
                    ? '检查执行失败，无明细数据'
                    : '该产物无未通过发现项',
              }}
            />
          </div>
        )}
      </Drawer>
    </div>
  );
}
