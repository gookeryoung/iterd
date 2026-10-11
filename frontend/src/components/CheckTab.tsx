/** 迭代详情 - 规则检查 Tab：绑定规则集 / 发起检查 / WS 进度 / 运行列表 / 发现项报告。 */

import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Drawer,
  Progress,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd';
import { CaretRightOutlined, LinkOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import {
  bindRuleSet,
  createCheckRun,
  fetchCheckRun,
  fetchCheckRuns,
  fetchFindings,
  fetchRuleSetBinding,
  fetchRuleSets,
  SEVERITY_OPTIONS,
} from '../api/rules';
import { extractErrorMessage } from '../api/client';
import { useTaskStream } from '../hooks/useTaskStream';
import {
  SEVERITY_LABELS,
  type CheckRun,
  type CheckRunStatus,
  type Finding,
  type Severity,
} from '../types';
import { SeverityTag } from './StatusTags';
import { formatDateTime } from '../utils/format';

/** 检查运行状态标签颜色与文案。 */
function runStatusRender(status: CheckRunStatus): { color: string; label: string } {
  switch (status) {
    case 'pending':
      return { color: 'default', label: '排队中' };
    case 'running':
      return { color: 'processing', label: '执行中' };
    case 'succeeded':
      return { color: 'success', label: '已完成' };
    case 'failed':
      return { color: 'error', label: '失败' };
    default:
      return { color: 'default', label: status };
  }
}

/** 检查 Tab 属性。 */
interface CheckTabProps {
  iterationId: number;
  projectId: number;
}

export default function CheckTab({ iterationId, projectId }: CheckTabProps) {
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [ruleSetId, setRuleSetId] = useState<number | undefined>(undefined);
  const [findingsRun, setFindingsRun] = useState<CheckRun | null>(null);
  const [severityFilter, setSeverityFilter] = useState<Severity | undefined>(undefined);

  const ruleSetsQuery = useQuery({
    queryKey: ['rule-sets', projectId],
    queryFn: () => fetchRuleSets(projectId),
  });

  const bindingQuery = useQuery({
    queryKey: ['rule-set-binding', iterationId],
    queryFn: () => fetchRuleSetBinding(iterationId),
  });

  const checkRunsQuery = useQuery({
    queryKey: ['check-runs', iterationId],
    queryFn: () => fetchCheckRuns(iterationId),
    // 存在未终态运行时每 2 秒轮询列表
    refetchInterval: (query) => {
      const runs = query.state.data ?? [];
      return runs.some((r) => r.status === 'pending' || r.status === 'running') ? 2000 : false;
    },
  });

  // 最新一次运行：优先取用户刚发起的，否则取列表最后一条（后端按 id 升序）
  const runs = useMemo(() => checkRunsQuery.data ?? [], [checkRunsQuery.data]);
  const latestRunId = runs.length > 0 ? runs[runs.length - 1].id : null;

  const latestRunQuery = useQuery({
    queryKey: ['check-run', latestRunId],
    queryFn: () => fetchCheckRun(latestRunId as number),
    enabled: latestRunId !== null,
    // 未终态时每 1.5 秒轮询详情（WS 可用时以 WS 推送为主）
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'succeeded' || status === 'failed' ? false : 1500;
    },
  });

  const findingsQuery = useQuery({
    queryKey: ['findings', findingsRun?.id, severityFilter],
    queryFn: () => fetchFindings(findingsRun?.id as number, { severity: severityFilter }),
    enabled: findingsRun !== null && findingsRun.status === 'succeeded',
  });

  // 未绑定规则集时默认选中已绑定项
  useEffect(() => {
    if (ruleSetId === undefined && bindingQuery.data?.rule_set_id) {
      setRuleSetId(bindingQuery.data.rule_set_id);
    }
  }, [bindingQuery.data, ruleSetId]);

  const latestRun = latestRunQuery.data;
  const busy = latestRun !== undefined && (latestRun.status === 'pending' || latestRun.status === 'running');
  const { state: streamState, connected } = useTaskStream(busy ? (latestRun?.task_id ?? null) : null);

  const startMutation = useMutation({
    mutationFn: (id: number) => createCheckRun(iterationId, id),
    onSuccess: (run) => {
      message.success(`检查已发起（运行 #${run.id}）`);
      void queryClient.invalidateQueries({ queryKey: ['check-runs', iterationId] });
      void queryClient.invalidateQueries({ queryKey: ['check-run', run.id] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const bindMutation = useMutation({
    mutationFn: (id: number) => bindRuleSet(id, iterationId),
    onSuccess: () => {
      message.success('规则集已绑定到当前迭代');
      void queryClient.invalidateQueries({ queryKey: ['rule-set-binding', iterationId] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const handleStart = () => {
    if (!ruleSetId) {
      message.warning('请先选择规则集');
      return;
    }
    startMutation.mutate(ruleSetId);
  };

  const ruleSetNameMap = new Map((ruleSetsQuery.data ?? []).map((rs) => [rs.id, rs.name]));
  const boundRuleSetId = bindingQuery.data?.rule_set_id ?? null;

  const runColumns: ColumnsType<CheckRun> = [
    { title: '运行 ID', dataIndex: 'id', key: 'id', width: 90 },
    {
      title: '规则集',
      dataIndex: 'rule_set_id',
      key: 'rule_set_id',
      render: (id: number) => ruleSetNameMap.get(id) ?? `规则集 #${id}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: CheckRunStatus) => {
        const { color, label } = runStatusRender(status);
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: '汇总',
      key: 'summary',
      width: 260,
      render: (_: unknown, record: CheckRun) => {
        if (record.summary) {
          return (
            <Space size={4}>
              <Tag color="red">错误 {record.summary.error ?? 0}</Tag>
              <Tag color="orange">警告 {record.summary.warning ?? 0}</Tag>
              <Tag color="blue">提示 {record.summary.info ?? 0}</Tag>
            </Space>
          );
        }
        return '-';
      },
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 160,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '结束时间',
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 160,
      render: (value: string | null) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: CheckRun) => (
        <Button
          type="link"
          size="small"
          disabled={record.status !== 'succeeded' && record.status !== 'failed'}
          onClick={() => setFindingsRun(record)}
        >
          查看发现
        </Button>
      ),
    },
  ];

  const findingColumns: ColumnsType<Finding> = [
    {
      title: '严重级别',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: Severity) => <SeverityTag severity={severity} />,
    },
    {
      title: '规则',
      key: 'rule',
      width: 180,
      render: (_: unknown, record: Finding) => (
        <span>
          <Typography.Text code>{record.rule_code}</Typography.Text> {record.rule_name}
        </span>
      ),
    },
    {
      title: '产物',
      key: 'artifact',
      width: 200,
      render: (_: unknown, record: Finding) => `${record.artifact_code} ${record.artifact_name}（v${record.version_no}）`,
    },
    { title: '位置', dataIndex: 'location', key: 'location', width: 200, ellipsis: true },
    { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true },
  ];

  const streamPercent = streamState?.progress?.percent ?? null;

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select<number>
          style={{ width: 280 }}
          placeholder="选择规则集"
          value={ruleSetId}
          onChange={setRuleSetId}
          loading={ruleSetsQuery.isPending}
          options={(ruleSetsQuery.data ?? []).map((rs) => ({
            value: rs.id,
            label: rs.project_id === null ? `${rs.name}（全局）` : rs.name,
          }))}
        />
        <Button
          type="primary"
          icon={<CaretRightOutlined />}
          loading={startMutation.isPending}
          onClick={handleStart}
        >
          发起检查
        </Button>
        <Button
          icon={<LinkOutlined />}
          disabled={!ruleSetId || ruleSetId === boundRuleSetId}
          loading={bindMutation.isPending}
          onClick={() => ruleSetId && bindMutation.mutate(ruleSetId)}
        >
          绑定到本迭代
        </Button>
        {boundRuleSetId && (
          <Typography.Text type="secondary">
            已绑定：{ruleSetNameMap.get(boundRuleSetId) ?? `规则集 #${boundRuleSetId}`}
          </Typography.Text>
        )}
      </Space>

      {/* 最新一次运行的进度 / 汇总 */}
      {latestRun === undefined && latestRunId !== null && (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin />
        </div>
      )}
      {latestRun && busy && (
        <div style={{ padding: '16px 0' }}>
          <Space>
            <Spin size="small" />
            <Typography.Text>
              检查执行中（运行 #{latestRun.id}
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
          {streamState?.logs && streamState.logs.length > 0 && (
            <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
              最新日志：{streamState.logs[streamState.logs.length - 1].message}
            </Typography.Paragraph>
          )}
        </div>
      )}
      {latestRun && latestRun.status === 'succeeded' && latestRun.summary && (
        <Alert
          type={latestRun.summary.error > 0 ? 'error' : latestRun.summary.warning > 0 ? 'warning' : 'success'}
          showIcon
          style={{ marginBottom: 16 }}
          message={`运行 #${latestRun.id} 检查完成`}
          description={
            <Space size={8} wrap>
              <Tag color="red">错误 {latestRun.summary.error}</Tag>
              <Tag color="orange">警告 {latestRun.summary.warning}</Tag>
              <Tag color="blue">提示 {latestRun.summary.info}</Tag>
              <Tag>检查产物 {latestRun.summary.artifacts}</Tag>
              <Tag>执行规则 {latestRun.summary.rules}</Tag>
            </Space>
          }
        />
      )}
      {latestRun && latestRun.status === 'failed' && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message={`运行 #${latestRun.id} 检查失败`}
          description={latestRun.task_id ? '请查看任务详情或稍后重试（最多重试 3 次）。' : '请稍后重试。'}
        />
      )}

      <Table<CheckRun>
        rowKey="id"
        columns={runColumns}
        dataSource={runs}
        loading={checkRunsQuery.isPending}
        pagination={false}
        size="small"
        locale={{ emptyText: '暂无检查运行' }}
      />

      {/* 发现项 Drawer */}
      <Drawer
        title={
          <Space>
            <span>发现项</span>
            {findingsRun && <Typography.Text type="secondary">运行 #{findingsRun.id}</Typography.Text>}
          </Space>
        }
        width={900}
        open={findingsRun !== null}
        onClose={() => {
          setFindingsRun(null);
          setSeverityFilter(undefined);
        }}
      >
        <Space style={{ marginBottom: 12 }}>
          <Typography.Text>按严重级别筛选：</Typography.Text>
          <Select<Severity | undefined>
            style={{ width: 160 }}
            allowClear
            placeholder="全部"
            value={severityFilter}
            onChange={(value) => setSeverityFilter(value)}
            options={SEVERITY_OPTIONS}
          />
        </Space>
        <Table<Finding>
          rowKey="id"
          columns={findingColumns}
          dataSource={findingsQuery.data ?? []}
          loading={findingsQuery.isPending}
          pagination={{ pageSize: 20, hideOnSinglePage: true }}
          size="small"
          locale={{ emptyText: findingsRun?.status === 'succeeded' ? '无发现项' : '检查完成后可查看发现项' }}
          footer={() => (
            <Typography.Text type="secondary">
              共 {findingsQuery.data?.length ?? 0} 条{severityFilter ? `（${SEVERITY_LABELS[severityFilter]}）` : ''}
            </Typography.Text>
          )}
        />
      </Drawer>
    </div>
  );
}
