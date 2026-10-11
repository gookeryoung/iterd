/** 迭代详情页（P0 核心）：迭代信息 + 产物 / 规则检查 / 基线 Tabs。 */

import { Button, Descriptions, Spin, Tabs, Typography } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { fetchIteration } from '../api/projects';
import { IterationStatusTag } from '../components/StatusTags';
import ArtifactTab from '../components/ArtifactTab';
import CheckTab from '../components/CheckTab';
import SimTab from '../components/SimTab';
import BaselineTab from '../components/BaselineTab';

export default function IterationDetailPage() {
  const params = useParams();
  const iterationId = Number(params.id);

  const iterationQuery = useQuery({
    queryKey: ['iteration', iterationId],
    queryFn: () => fetchIteration(iterationId),
    enabled: Number.isFinite(iterationId),
  });

  if (iterationQuery.isPending) {
    return (
      <div style={{ textAlign: 'center', padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (iterationQuery.isError || !iterationQuery.data) {
    return <Typography.Text type="danger">迭代加载失败</Typography.Text>;
  }

  const iteration = iterationQuery.data;

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Link to={`/projects/${iteration.project_id}`}>
          <Button type="link" icon={<ArrowLeftOutlined />} style={{ paddingLeft: 0 }}>
            返回项目
          </Button>
        </Link>
      </div>

      <Typography.Title level={4} style={{ marginTop: 0 }}>
        {`迭代 ${iteration.number}：${iteration.title}`} <IterationStatusTag status={iteration.status} />
      </Typography.Title>

      <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="目标">
          {iteration.objective || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="计划周期">
          {iteration.start_date ?? '-'} 至 {iteration.end_date ?? '-'}
        </Descriptions.Item>
      </Descriptions>

      <Tabs
        defaultActiveKey="artifacts"
        items={[
          {
            key: 'artifacts',
            label: '产物',
            children: <ArtifactTab iterationId={iterationId} />,
          },
          {
            key: 'checks',
            label: '规则检查',
            children: (
              <CheckTab iterationId={iterationId} projectId={iteration.project_id} />
            ),
          },
          {
            key: 'simulation',
            label: '仿真验证',
            children: (
              <SimTab iterationId={iterationId} projectId={iteration.project_id} />
            ),
          },
          {
            key: 'baselines',
            label: '基线',
            children: (
              <BaselineTab iterationId={iterationId} iterationStatus={iteration.status} />
            ),
          },
        ]}
      />
    </div>
  );
}
