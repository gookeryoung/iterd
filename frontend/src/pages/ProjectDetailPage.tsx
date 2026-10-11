/** 项目详情页：项目信息 + 迭代 / 成员 Tabs。 */

import { Descriptions, Spin, Tabs, Tag, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { fetchMyRole, fetchProject } from '../api/projects';
import { ROLE_LABELS } from '../types';
import { formatDateTime } from '../utils/format';
import IterationsTab from '../components/IterationsTab';
import MembersTab from '../components/MembersTab';
import DocLibraryTab from '../components/DocLibraryTab';
import ProjectRunsTab from '../components/ProjectRunsTab';

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = Number(params.id);

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => fetchProject(projectId),
    enabled: Number.isFinite(projectId),
  });

  const myRoleQuery = useQuery({
    queryKey: ['project-role', projectId],
    queryFn: () => fetchMyRole(projectId),
    enabled: Number.isFinite(projectId),
    retry: false,
  });

  if (projectQuery.isPending) {
    return (
      <div style={{ textAlign: 'center', padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (projectQuery.isError || !projectQuery.data) {
    return <Typography.Text type="danger">项目加载失败</Typography.Text>;
  }

  const project = projectQuery.data;

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        {project.name}
        {myRoleQuery.data?.role && (
          <Tag color="blue" style={{ marginLeft: 12, fontSize: 13, fontWeight: 400 }}>
            我的角色：{myRoleQuery.data.is_superuser ? '超级管理员' : ROLE_LABELS[myRoleQuery.data.role]}
          </Tag>
        )}
      </Typography.Title>
      <Descriptions size="small" column={3} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="编码">{project.code}</Descriptions.Item>
        <Descriptions.Item label="状态">{project.status}</Descriptions.Item>
        <Descriptions.Item label="创建时间">{formatDateTime(project.created_at)}</Descriptions.Item>
        {project.description && (
          <Descriptions.Item label="描述" span={3}>
            {project.description}
          </Descriptions.Item>
        )}
      </Descriptions>

      <Tabs
        defaultActiveKey="library"
        items={[
          {
            key: 'library',
            label: '文档库',
            children: <DocLibraryTab projectId={projectId} />,
          },
          {
            key: 'iterations',
            label: '迭代',
            children: <IterationsTab projectId={projectId} />,
          },
          {
            key: 'reviews',
            label: '审查',
            children: <ProjectRunsTab projectId={projectId} />,
          },
          {
            key: 'members',
            label: '成员',
            children: <MembersTab projectId={projectId} />,
          },
        ]}
      />
    </div>
  );
}
