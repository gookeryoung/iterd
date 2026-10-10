/** 项目详情页：项目信息 + 迭代 / 成员 Tabs。 */

import { Descriptions, Spin, Tabs, Typography } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { fetchProject } from '../api/projects';
import { formatDateTime } from '../utils/format';
import IterationsTab from '../components/IterationsTab';
import MembersTab from '../components/MembersTab';

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = Number(params.id);

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => fetchProject(projectId),
    enabled: Number.isFinite(projectId),
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
        defaultActiveKey="iterations"
        items={[
          {
            key: 'iterations',
            label: '迭代',
            children: <IterationsTab projectId={projectId} />,
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
