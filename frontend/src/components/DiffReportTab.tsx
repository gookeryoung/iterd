/** 迭代对比与审查报告 Tab：基线 diff 展示 + 报告生成 / 下载 / 归档。 */

import { useMemo, useState } from 'react';
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Empty,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DownloadOutlined, FileAddOutlined, FileTextOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { fetchIterations, fetchMyRole } from '../api/projects';
import { archiveIterationReport, fetchIterationDiff, fetchIterationReport } from '../api/reports';
import { extractErrorMessage } from '../api/client';
import type { ApprovalSummary, EntryDiff, FieldChange, SeverityCounts, SimSnapshot } from '../types';

interface EntryRow {
  key: string;
  name: string;
}

const entryColumns: ColumnsType<EntryRow> = [
  { title: '键', dataIndex: 'key', key: 'key', width: 140 },
  { title: '名称', dataIndex: 'name', key: 'entry-name' },
];

const changeColumns: ColumnsType<FieldChange & { rowKey: string }> = [
  { title: '键', dataIndex: 'code', key: 'code', width: 120, render: (_v, r) => r.code ?? r.part_code ?? '-' },
  { title: '字段', dataIndex: 'field', key: 'field', width: 180 },
  { title: '基线值', dataIndex: 'base', key: 'base', render: (v: unknown) => String(v ?? '-') },
  { title: '当前值', dataIndex: 'current', key: 'current', render: (v: unknown) => String(v ?? '-') },
];

function entryKey(item: Record<string, unknown>): string {
  return String(item.code ?? item.part_code ?? '-');
}

function entryName(item: Record<string, unknown>): string {
  return String(item.name ?? item.part_name ?? '-');
}

function EntryRowsTable({ rows, mark }: { rows: Record<string, unknown>[]; mark?: string }) {
  const data: EntryRow[] = rows.map((item) => ({
    key: entryKey(item),
    name: mark ? `${entryName(item)}（${mark}）` : entryName(item),
  }));
  return (
    <Table<EntryRow>
      size="small"
      columns={entryColumns}
      dataSource={data}
      rowKey="key"
      pagination={false}
      style={{ marginBottom: 8 }}
    />
  );
}

function DiffSection({ title, diff, keyLabel }: { title: string; diff: EntryDiff; keyLabel: string }) {
  return (
    <Card size="small" title={title} style={{ marginBottom: 12 }}>
      <Descriptions size="small" column={3} style={{ marginBottom: 8 }}>
        <Descriptions.Item label="新增">{diff.added.length}</Descriptions.Item>
        <Descriptions.Item label="移除">{diff.removed.length}</Descriptions.Item>
        <Descriptions.Item label="字段变更">{diff.changed.length}</Descriptions.Item>
      </Descriptions>
      {diff.added.length > 0 && <EntryRowsTable rows={diff.added} />}
      {diff.removed.length > 0 && <EntryRowsTable rows={diff.removed} mark="基线存在，当前已移除" />}
      {diff.changed.length > 0 && (
        <Table<FieldChange & { rowKey: string }>
          size="small"
          columns={changeColumns}
          dataSource={diff.changed.map((c, i) => ({ ...c, rowKey: `${i}-${c.field}` }))}
          rowKey="rowKey"
          pagination={false}
        />
      )}
      {diff.added.length + diff.removed.length + diff.changed.length === 0 && (
        <Typography.Text type="secondary">无差异（{keyLabel}集合一致）</Typography.Text>
      )}
    </Card>
  );
}

/** 结论与审批对比段。 */
function ConclusionSection({
  findings,
  sims,
  approvals,
}: {
  findings: { baseline: SeverityCounts | null; current: SeverityCounts | null };
  sims: { baseline: SimSnapshot | null; current: SimSnapshot | null };
  approvals: { baseline: ApprovalSummary | null; current: ApprovalSummary | null };
}) {
  const counts = (c: SeverityCounts | null) =>
    c ? `error ${c.error} / warning ${c.warning} / info ${c.info}` : '（无检查运行）';
  const simText = (s: SimSnapshot | null) =>
    s ? `${s.verdict === 'pass' ? '通过' : '超阈'}（${s.failures} 项超阈）` : '（无仿真）';
  const approvalText = (a: ApprovalSummary | null) =>
    a ? `通过 ${a.approved} / 驳回 ${a.rejected} / 待签作业 ${a.pending_jobs}` : '（无审查运行）';
  return (
    <Card size="small" title="结论与审批对比" style={{ marginBottom: 12 }}>
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="检查发现项">
          基线 {counts(findings.baseline)}；当前 {counts(findings.current)}
        </Descriptions.Item>
        <Descriptions.Item label="仿真结论">
          基线 {simText(sims.baseline)}；当前 {simText(sims.current)}
        </Descriptions.Item>
        <Descriptions.Item label="审批摘要">
          基线 {approvalText(approvals.baseline)}；当前 {approvalText(approvals.current)}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}

export default function DiffReportTab({ iterationId, projectId }: { iterationId: number; projectId: number }) {
  const { message } = AntApp.useApp();
  const [baselineId, setBaselineId] = useState<number | undefined>(undefined);
  const [report, setReport] = useState<{ generatedAt: string; markdown: string } | null>(null);

  const iterationsQuery = useQuery({
    queryKey: ['iterations', projectId],
    queryFn: () => fetchIterations(projectId),
  });
  const myRoleQuery = useQuery({
    queryKey: ['project-role', projectId],
    queryFn: () => fetchMyRole(projectId),
    retry: false,
  });

  const diffQuery = useQuery({
    queryKey: ['iteration-diff', iterationId, baselineId ?? 'auto'],
    queryFn: () => fetchIterationDiff(iterationId, baselineId),
  });

  const generateMutation = useMutation({
    mutationFn: () => fetchIterationReport(iterationId),
    onSuccess: (data) => setReport({ generatedAt: data.generated_at, markdown: data.markdown }),
    onError: (error: unknown) => message.error(extractErrorMessage(error)),
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveIterationReport(iterationId),
    onSuccess: (result) => message.success(`报告已归档为产物 ${result.artifact_code} v${result.version_no}`),
    onError: (error: unknown) => message.error(extractErrorMessage(error)),
  });

  const baselineOptions = useMemo(
    () =>
      (iterationsQuery.data ?? [])
        .filter((it) => it.id !== iterationId)
        .map((it) => ({ label: `迭代 ${it.number}：${it.title}`, value: it.id })),
    [iterationsQuery.data, iterationId],
  );

  const downloadReport = () => {
    if (!report) return;
    const blob = new Blob([report.markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `审查报告-迭代${diffQuery.data?.iteration.number ?? iterationId}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const canArchive = myRoleQuery.data?.can_design ?? false;

  return (
    <div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Typography.Text>对比基线：</Typography.Text>
        <Select
          style={{ width: 280 }}
          placeholder="自动选取前序已关闭迭代"
          allowClear
          value={baselineId}
          onChange={(value) => setBaselineId(value)}
          options={baselineOptions}
          loading={iterationsQuery.isPending}
        />
        {diffQuery.data?.baseline && (
          <Tag color="blue">
            基线：迭代 {diffQuery.data.baseline.number} {diffQuery.data.baseline.title}
          </Tag>
        )}
      </Space>

      {diffQuery.data?.note && (
        <Alert type="info" showIcon message={diffQuery.data.note} style={{ marginBottom: 12 }} />
      )}
      {diffQuery.isError && (
        <Alert type="error" showIcon message={extractErrorMessage(diffQuery.error)} style={{ marginBottom: 12 }} />
      )}

      {diffQuery.data && (
        <>
          <DiffSection title="产物集合差异" diff={diffQuery.data.artifacts} keyLabel="产物编码" />
          <DiffSection title="BOM 差异" diff={diffQuery.data.bom} keyLabel="零件编码" />
          <ConclusionSection
            findings={diffQuery.data.findings}
            sims={diffQuery.data.sims}
            approvals={diffQuery.data.approvals}
          />
        </>
      )}

      <Card
        size="small"
        title="审查报告"
        extra={
          <Space>
            <Button
              icon={<FileTextOutlined />}
              loading={generateMutation.isPending}
              onClick={() => generateMutation.mutate()}
            >
              生成报告
            </Button>
            {report && (
              <Button icon={<DownloadOutlined />} onClick={downloadReport}>
                下载 Markdown
              </Button>
            )}
            {canArchive && (
              <Button
                type="primary"
                icon={<FileAddOutlined />}
                loading={archiveMutation.isPending}
                onClick={() => archiveMutation.mutate()}
              >
                归档为产物
              </Button>
            )}
          </Space>
        }
      >
        {report ? (
          <>
            <Typography.Text type="secondary">生成时间：{report.generatedAt}</Typography.Text>
            <pre
              style={{
                marginTop: 8,
                maxHeight: 420,
                overflow: 'auto',
                fontSize: 12,
                background: '#f6f8fa',
                padding: 12,
                borderRadius: 6,
              }}
            >
              {report.markdown}
            </pre>
          </>
        ) : (
          <Empty
            description="点击「生成报告」按迭代聚合检查汇总 / 发现明细 / 仿真判定 / 审批记录"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )}
      </Card>
    </div>
  );
}
