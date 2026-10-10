/** 迭代详情 - 基线 Tab：基线列表 / 建立基线（planned 禁用）/ 查看快照。 */

import { useState } from 'react';
import { Button, Descriptions, Drawer, Form, Input, Modal, Table, Tooltip, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import { createBaseline, fetchBaseline, fetchBaselines } from '../api/projects';
import { extractErrorMessage } from '../api/client';
import type { Baseline, BaselineItem, IterationStatus } from '../types';
import { formatDateTime } from '../utils/format';

/** 基线 Tab 属性。 */
interface BaselineTabProps {
  iterationId: number;
  iterationStatus: IterationStatus;
}

export default function BaselineTab({ iterationId, iterationStatus }: BaselineTabProps) {
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [detail, setDetail] = useState<Baseline | null>(null);
  const [form] = Form.useForm<{ name: string }>();

  const baselinesQuery = useQuery({
    queryKey: ['baselines', iterationId],
    queryFn: () => fetchBaselines(iterationId),
  });

  // 基线详情（Drawer 打开时拉取）
  const detailQuery = useQuery({
    queryKey: ['baseline', detail?.id],
    queryFn: () => fetchBaseline(detail?.id as number),
    enabled: detail !== null,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createBaseline(iterationId, name),
    onSuccess: (data) => {
      message.success(`基线「${data.name}」已建立，锁定 ${data.items.length} 个产物版本`);
      setModalOpen(false);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['baselines', iterationId] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const columns: ColumnsType<Baseline> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: Baseline) => (
        <Button type="link" size="small" onClick={() => setDetail(record)}>
          查看快照
        </Button>
      ),
    },
  ];

  const itemColumns: ColumnsType<BaselineItem> = [
    { title: '条目 ID', dataIndex: 'id', key: 'id', width: 120 },
    { title: '产物 ID', dataIndex: 'artifact_id', key: 'artifact_id' },
    { title: '锁定版本 ID', dataIndex: 'artifact_version_id', key: 'artifact_version_id' },
  ];

  const plannedDisabled = iterationStatus === 'planned';
  const shownDetail = detailQuery.data ?? detail;
  const shownItems = detailQuery.data?.items ?? [];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Tooltip title={plannedDisabled ? '迭代激活后才能建立基线' : '锁定迭代内全部产物当前版本'}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={plannedDisabled}
            onClick={() => {
              form.resetFields();
              setModalOpen(true);
            }}
          >
            建立基线
          </Button>
        </Tooltip>
      </div>

      <Table<Baseline>
        rowKey="id"
        columns={columns}
        dataSource={baselinesQuery.data ?? []}
        loading={baselinesQuery.isPending}
        pagination={false}
        locale={{ emptyText: '暂无基线' }}
      />

      <Modal
        title="建立基线"
        open={modalOpen}
        confirmLoading={createMutation.isPending}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">
          建立基线将锁定迭代内全部产物的当前版本。
        </Typography.Paragraph>
        <Form<{ name: string }> form={form} layout="vertical" onFinish={(values) => createMutation.mutate(values.name.trim())}>
          <Form.Item
            name="name"
            label="基线名称"
            rules={[{ required: true, message: '请输入基线名称' }]}
          >
            <Input placeholder="如：迭代 N 设计冻结基线" />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={`基线快照${shownDetail ? ` - ${shownDetail.name}` : ''}`}
        width={640}
        open={detail !== null}
        onClose={() => setDetail(null)}
      >
        {shownDetail && (
          <>
            <Descriptions size="small" column={1} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="名称">{shownDetail.name}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(shownDetail.created_at)}</Descriptions.Item>
              <Descriptions.Item label="快照条目数量">
                <Typography.Text strong>{shownItems.length}</Typography.Text>
              </Descriptions.Item>
            </Descriptions>
            <Table<BaselineItem>
              rowKey="id"
              columns={itemColumns}
              dataSource={shownItems}
              loading={detailQuery.isPending}
              pagination={false}
              size="small"
              locale={{ emptyText: '无快照条目' }}
            />
          </>
        )}
      </Drawer>
    </div>
  );
}
