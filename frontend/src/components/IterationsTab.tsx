/** 项目详情 - 迭代 Tab：迭代列表 / 新建迭代 / 状态流转 / 进入详情。 */

import { useState } from 'react';
import { Button, Form, Input, Modal, Space, Table, Tooltip, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { App as AntApp } from 'antd';
import {
  createIteration,
  fetchIterations,
  updateIteration,
} from '../api/projects';
import { extractErrorMessage } from '../api/client';
import type { Iteration, IterationInput, IterationStatus } from '../types';
import { ITERATION_STATUS_LABELS } from '../types';
import { IterationStatusTag } from './StatusTags';
import { formatDateTime } from '../utils/format';

/** 新建迭代表单值。 */
interface IterationFormValues {
  title: string;
  objective?: string;
}

/** 迭代 Tab 属性。 */
interface IterationsTabProps {
  projectId: number;
}

export default function IterationsTab({ projectId }: IterationsTabProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<IterationFormValues>();

  const iterationsQuery = useQuery({
    queryKey: ['iterations', projectId],
    queryFn: () => fetchIterations(projectId),
  });

  // 迭代列表变动后联动刷新（检查运行等）
  const invalidateIterations = () => {
    void queryClient.invalidateQueries({ queryKey: ['iterations', projectId] });
    void queryClient.invalidateQueries({ queryKey: ['project', projectId] });
  };

  const createMutation = useMutation({
    mutationFn: (values: IterationInput) => createIteration(projectId, values),
    onSuccess: () => {
      message.success('迭代创建成功');
      setModalOpen(false);
      form.resetFields();
      invalidateIterations();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: IterationStatus }) =>
      updateIteration(id, { status }),
    onSuccess: (data) => {
      message.success(`迭代状态已更新为「${ITERATION_STATUS_LABELS[data.status]}」`);
      invalidateIterations();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const columns: ColumnsType<Iteration> = [
    { title: '编号', dataIndex: 'number', key: 'number', width: 80 },
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '目标', dataIndex: 'objective', key: 'objective', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (_: string, record: Iteration) => <IterationStatusTag status={record.status} />,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: unknown, record: Iteration) => (
        <Space>
          <Button type="link" size="small" onClick={() => navigate(`/iterations/${record.id}`)}>
            进入
          </Button>
          {record.status === 'planned' && (
            <Tooltip title="状态流转：已计划 -> 进行中">
              <Button
                type="link"
                size="small"
                loading={statusMutation.isPending}
                onClick={() => statusMutation.mutate({ id: record.id, status: 'active' })}
              >
                激活
              </Button>
            </Tooltip>
          )}
          {record.status === 'active' && (
            <Tooltip title="状态流转：进行中 -> 已关闭">
              <Button
                type="link"
                size="small"
                loading={statusMutation.isPending}
                onClick={() => statusMutation.mutate({ id: record.id, status: 'closed' })}
              >
                关闭
              </Button>
            </Tooltip>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            form.resetFields();
            setModalOpen(true);
          }}
        >
          新建迭代
        </Button>
      </div>

      <Table<Iteration>
        rowKey="id"
        columns={columns}
        dataSource={iterationsQuery.data ?? []}
        loading={iterationsQuery.isPending}
        pagination={false}
        locale={{ emptyText: '暂无迭代' }}
      />

      <Modal
        title="新建迭代"
        open={modalOpen}
        confirmLoading={createMutation.isPending}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">
          编号自动自增，新迭代初始状态为「已计划」。
        </Typography.Paragraph>
        <Form<IterationFormValues> form={form} layout="vertical" onFinish={(values) => createMutation.mutate(values)}>
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: '请输入迭代标题' }]}
          >
            <Input placeholder="迭代标题" />
          </Form.Item>
          <Form.Item name="objective" label="目标">
            <Input.TextArea rows={3} placeholder="迭代目标（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
