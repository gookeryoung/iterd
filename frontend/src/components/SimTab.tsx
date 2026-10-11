/** 迭代详情 - 仿真验证 Tab：模板选择 / 发起作业 / WS 进度 / 作业列表 / 结果阈值判定。 */

import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd';
import { CaretRightOutlined, PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import {
  createSimJob,
  createSimTemplate,
  fetchSimJobs,
  fetchSimResult,
  fetchSimTemplates,
  fetchSolvers,
} from '../api/simulation';
import { fetchArtifacts } from '../api/artifacts';
import { extractErrorMessage } from '../api/client';
import { useTaskStream } from '../hooks/useTaskStream';
import {
  SIM_JOB_STATUS_LABELS,
  type SimJob,
  type SimJobStatus,
  type SimResult,
  type SimResultDetail,
  type SimTemplate,
  type SolverInfo,
} from '../types';
import { formatDateTime } from '../utils/format';

/** 作业状态标签颜色。 */
const SIM_JOB_STATUS_COLORS: Record<SimJobStatus, string> = {
  pending: 'default',
  running: 'processing',
  succeeded: 'success',
  failed: 'error',
};

/** 仿真 Tab 属性。 */
interface SimTabProps {
  iterationId: number;
  projectId: number;
}

/** 新建模板表单值。 */
interface TemplateFormValues {
  code: string;
  name: string;
  solver_type: string;
  thresholds: string;
  description: string;
}

export default function SimTab({ iterationId, projectId }: SimTabProps) {
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [templateId, setTemplateId] = useState<number | undefined>(undefined);
  const [versionId, setVersionId] = useState<number | undefined>(undefined);
  const [resultJob, setResultJob] = useState<SimJob | null>(null);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [form] = Form.useForm<TemplateFormValues>();

  const templatesQuery = useQuery({
    queryKey: ['sim-templates', projectId],
    queryFn: () => fetchSimTemplates(projectId),
  });

  const solversQuery = useQuery({
    queryKey: ['solvers'],
    queryFn: fetchSolvers,
  });

  const artifactsQuery = useQuery({
    queryKey: ['artifacts', 'iteration', iterationId],
    queryFn: () => fetchArtifacts({ iteration_id: iterationId }),
  });

  const jobsQuery = useQuery({
    queryKey: ['sim-jobs', iterationId],
    queryFn: () => fetchSimJobs(iterationId),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      return jobs.some((j) => j.status === 'pending' || j.status === 'running') ? 2000 : false;
    },
  });

  const resultQuery = useQuery({
    queryKey: ['sim-result', resultJob?.id],
    queryFn: () => fetchSimResult(resultJob?.id as number),
    enabled: resultJob !== null && resultJob.status === 'succeeded',
  });

  const jobs = useMemo(() => jobsQuery.data ?? [], [jobsQuery.data]);
  const latestJob = jobs.length > 0 ? jobs[jobs.length - 1] : undefined;
  const busy = latestJob !== undefined && (latestJob.status === 'pending' || latestJob.status === 'running');
  const { state: streamState, connected } = useTaskStream(busy ? (latestJob?.task_id ?? null) : null);

  // 默认选中第一个模板
  useEffect(() => {
    if (templateId === undefined && templatesQuery.data && templatesQuery.data.length > 0) {
      setTemplateId(templatesQuery.data[0].id);
    }
  }, [templatesQuery.data, templateId]);

  const startMutation = useMutation({
    mutationFn: () =>
      createSimJob(iterationId, {
        template_id: templateId as number,
        artifact_version_id: versionId ?? null,
      }),
    onSuccess: (job) => {
      message.success(`仿真作业已发起（作业 #${job.id}）`);
      void queryClient.invalidateQueries({ queryKey: ['sim-jobs', iterationId] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const createTemplateMutation = useMutation({
    mutationFn: (values: TemplateFormValues) => {
      const raw = values.thresholds?.trim();
      let thresholds: Record<string, unknown> | null = null;
      if (raw) {
        try {
          thresholds = JSON.parse(raw) as Record<string, unknown>;
        } catch {
          throw new Error('验收阈值必须是合法 JSON，例如 {"max_stress":{"max":100}}');
        }
      }
      return createSimTemplate({
        code: values.code,
        name: values.name,
        solver_type: values.solver_type,
        project_id: projectId,
        thresholds,
        description: values.description,
      });
    },
    onSuccess: (template: SimTemplate) => {
      message.success(`模板 ${template.code} 已创建`);
      setTemplateModalOpen(false);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['sim-templates', projectId] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const handleStart = () => {
    if (!templateId) {
      message.warning('请先选择仿真模板');
      return;
    }
    startMutation.mutate();
  };

  const selectedTemplate = (templatesQuery.data ?? []).find((t) => t.id === templateId);
  const solverInfo: SolverInfo | undefined = (solversQuery.data ?? []).find(
    (s) => s.solver_type === selectedTemplate?.solver_type,
  );

  const versionOptions = (artifactsQuery.data ?? [])
    .filter((a) => a.current_version_id !== null)
    .map((a) => ({
      value: a.current_version_id as number,
      label: `${a.code} ${a.name}`,
    }));

  const jobColumns: ColumnsType<SimJob> = [
    { title: '作业 ID', dataIndex: 'id', key: 'id', width: 90 },
    {
      title: '模板',
      key: 'template',
      width: 180,
      render: (_: unknown, record: SimJob) => (
        <span>
          <Typography.Text code>{record.solver_type}</Typography.Text> {record.template_name}
        </span>
      ),
    },
    {
      title: '被验证产物',
      key: 'artifact',
      width: 160,
      render: (_: unknown, record: SimJob) =>
        record.artifact_code ? `${record.artifact_code}（v${record.version_no ?? '-'}）` : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: SimJobStatus) => (
        <Tag color={SIM_JOB_STATUS_COLORS[status]}>{SIM_JOB_STATUS_LABELS[status]}</Tag>
      ),
    },
    {
      title: '结论',
      key: 'verdict',
      width: 110,
      render: (_: unknown, record: SimJob) => {
        if (record.status === 'failed') {
          return <Typography.Text type="danger">执行失败</Typography.Text>;
        }
        if (!record.summary) {
          return '-';
        }
        return record.summary.verdict === 'pass' ? (
          <Tag color="green">通过（{record.summary.metrics} 项指标）</Tag>
        ) : (
          <Tag color="red">不通过（{record.summary.failures} 项超阈）</Tag>
        );
      },
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 150,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '结束时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 150,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: SimJob) => (
        <Button
          type="link"
          size="small"
          disabled={record.status !== 'succeeded'}
          onClick={() => setResultJob(record)}
        >
          查看结果
        </Button>
      ),
    },
  ];

  const detailColumns: ColumnsType<SimResultDetail> = [
    { title: '指标', key: 'label', render: (_: unknown, record: SimResultDetail) => `${record.label}（${record.key}）` },
    {
      title: '值',
      key: 'value',
      width: 140,
      render: (_: unknown, record: SimResultDetail) => `${record.value}${record.unit ? ` ${record.unit}` : ''}`,
    },
    { title: '下限 min', key: 'min', width: 100, render: (_: unknown, r: SimResultDetail) => (r.min === null ? '-' : r.min) },
    { title: '上限 max', key: 'max', width: 100, render: (_: unknown, r: SimResultDetail) => (r.max === null ? '-' : r.max) },
    {
      title: '判定',
      key: 'passed',
      width: 90,
      render: (_: unknown, record: SimResultDetail) =>
        record.passed ? <Tag color="green">通过</Tag> : <Tag color="red">超阈</Tag>,
    },
  ];

  const result: SimResult | undefined = resultQuery.data;
  const streamPercent = streamState?.progress?.percent ?? null;

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select<number>
          style={{ width: 240 }}
          placeholder="选择仿真模板"
          value={templateId}
          onChange={setTemplateId}
          loading={templatesQuery.isPending}
          options={(templatesQuery.data ?? []).map((t) => ({
            value: t.id,
            label: t.project_id === null ? `${t.name}（全局）` : `${t.code} ${t.name}`,
          }))}
        />
        <Select<number>
          style={{ width: 240 }}
          allowClear
          placeholder="绑定产物版本（可选）"
          value={versionId}
          onChange={(value) => setVersionId(value)}
          loading={artifactsQuery.isPending}
          options={versionOptions}
        />
        <Button
          type="primary"
          icon={<CaretRightOutlined />}
          loading={startMutation.isPending}
          onClick={handleStart}
        >
          发起仿真
        </Button>
        <Button icon={<PlusOutlined />} onClick={() => setTemplateModalOpen(true)}>
          新建模板
        </Button>
      </Space>

      {selectedTemplate && (
        <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="求解器">{selectedTemplate.solver_type}</Descriptions.Item>
          <Descriptions.Item label="验收阈值">
            {selectedTemplate.thresholds ? (
              <Typography.Text code>{JSON.stringify(selectedTemplate.thresholds)}</Typography.Text>
            ) : (
              '未设置（全部指标仅记录不判定）'
            )}
          </Descriptions.Item>
          {solverInfo && (
            <Descriptions.Item label="求解器说明" span={2}>
              {solverInfo.description}
            </Descriptions.Item>
          )}
        </Descriptions>
      )}

      {busy && latestJob && (
        <div style={{ padding: '8px 0 16px' }}>
          <Space>
            <Spin size="small" />
            <Typography.Text>
              正在求解（作业 #{latestJob.id}
              {connected ? '，实时推送已连接' : ''}）
            </Typography.Text>
          </Space>
          {streamPercent !== null ? (
            <Progress
              percent={streamPercent}
              status="active"
              style={{ marginTop: 8 }}
              format={() => streamState?.progress?.stage ?? ''}
            />
          ) : (
            <Progress percent={60} status="active" showInfo={false} style={{ marginTop: 8 }} />
          )}
        </div>
      )}

      {latestJob && latestJob.status === 'failed' && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message={`作业 #${latestJob.id} 求解失败`}
          description={latestJob.error ?? '请检查模板参数或求解器输入后重试。'}
        />
      )}

      <Table<SimJob>
        rowKey="id"
        columns={jobColumns}
        dataSource={jobs}
        loading={jobsQuery.isPending}
        pagination={false}
        size="small"
        locale={{ emptyText: '暂无仿真作业' }}
      />

      {/* 结果 Drawer */}
      <Drawer
        title={
          <Space>
            <span>仿真结果</span>
            {resultJob && <Typography.Text type="secondary">作业 #{resultJob.id}</Typography.Text>}
          </Space>
        }
        width={820}
        open={resultJob !== null}
        onClose={() => setResultJob(null)}
      >
        {resultQuery.isPending && (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        )}
        {result && (
          <div>
            <Space style={{ marginBottom: 12 }}>
              <Typography.Text strong>结论：</Typography.Text>
              {result.verdict === 'pass' ? (
                <Tag color="green">通过</Tag>
              ) : (
                <Tag color="red">不通过（{result.failures} 项超阈）</Tag>
              )}
            </Space>
            <Table<SimResultDetail>
              rowKey="key"
              columns={detailColumns}
              dataSource={result.detail ?? []}
              pagination={false}
              size="small"
              locale={{ emptyText: '无指标明细' }}
            />
          </div>
        )}
      </Drawer>

      {/* 新建模板 Modal */}
      <Modal
        title="新建仿真模板"
        open={templateModalOpen}
        onCancel={() => setTemplateModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createTemplateMutation.isPending}
        destroyOnHidden
      >
        <Form<TemplateFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => createTemplateMutation.mutate(values)}
          initialValues={{ solver_type: 'beam_static', thresholds: '', description: '' }}
        >
          <Form.Item name="code" label="模板编码" rules={[{ required: true, message: '请输入模板编码' }]}>
            <Input placeholder="BEAM-CHECK" />
          </Form.Item>
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="梁强度校核" />
          </Form.Item>
          <Form.Item name="solver_type" label="求解器" rules={[{ required: true, message: '请选择求解器' }]}>
            <Select
              loading={solversQuery.isPending}
              options={(solversQuery.data ?? []).map((s) => ({ value: s.solver_type, label: s.solver_type }))}
            />
          </Form.Item>
          <Form.Item
            name="thresholds"
            label="验收阈值（JSON，min/max）"
            extra={'示例：{"max_stress":{"max":100},"safety_factor":{"min":1.5}}'}
          >
            <Input.TextArea rows={3} placeholder='{"max_stress":{"max":100}}' />
          </Form.Item>
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
