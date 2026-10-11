/** 项目详情 - 迭代 Tab：迭代列表 / 新建迭代（含时间窗） / 编辑 / 状态流转 / 进入详情。 */

import { useState } from 'react';
import { Button, DatePicker, Form, Input, Modal, Space, Table, Tooltip, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { App as AntApp } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import {
  createIteration,
  fetchIterations,
  updateIteration,
} from '../api/projects';
import { extractErrorMessage } from '../api/client';
import type { Iteration, IterationInput, IterationStatus } from '../types';
import { ITERATION_STATUS_LABELS } from '../types';
import { IterationStatusTag } from './StatusTags';
import { formatDate, formatDateTime } from '../utils/format';

/** 迭代表单值（日期用 Dayjs 便于 DatePicker）。 */
interface IterationFormValues {
  title: string;
  objective?: string;
  start_date?: Dayjs | null;
  end_date?: Dayjs | null;
}

/** 迭代 Tab 属性。 */
interface IterationsTabProps {
  projectId: number;
}

/** 表单值转接口入参（日期转 YYYY-MM-DD）。 */
function toInput(values: IterationFormValues): IterationInput {
  return {
    title: values.title.trim(),
    objective: values.objective?.trim() ?? '',
    start_date: values.start_date ? values.start_date.format('YYYY-MM-DD') : null,
    end_date: values.end_date ? values.end_date.format('YYYY-MM-DD') : null,
  };
}

export default function IterationsTab({ projectId }: IterationsTabProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Iteration | null>(null);
  const [form] = Form.useForm<IterationFormValues>();

  const iterationsQuery = useQuery({
    queryKey: ['iterations', projectId],
    queryFn: () => fetchIterations(projectId),
  });

  // 迭代列表变动后联动刷新（检查运行等）
  const invalidateIterations = () => {
    void queryClient.invalidateQueries({ queryKey: ['iterations', projectId] });
    void queryClient.invalidateQueries({ queryKey: ['project', projectId] });
    void queryClient.invalidateQueries({ queryKey: ['iteration'] });
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

  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: number; values: IterationInput }) =>
      updateIteration(id, values),
    onSuccess: () => {
      message.success('迭代已更新');
      setModalOpen(false);
      setEditing(null);
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

  /** 打开新建/编辑 Modal。 */
  const openModal = (iteration: Iteration | null) => {
    setEditing(iteration);
    setModalOpen(true);
    if (iteration) {
      form.setFieldsValue({
        title: iteration.title,
        objective: iteration.objective,
        start_date: iteration.start_date ? dayjs(iteration.start_date) : null,
        end_date: iteration.end_date ? dayjs(iteration.end_date) : null,
      });
    } else {
      form.resetFields();
    }
  };

  const handleSubmit = (values: IterationFormValues) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, values: toInput(values) });
      return;
    }
    createMutation.mutate(toInput(values));
  };

  const columns: ColumnsType<Iteration> = [
    { title: '编号', dataIndex: 'number', key: 'number', width: 80 },
    { title: '标题', dataIndex: 'title', key: 'title' },
    { title: '目标', dataIndex: 'objective', key: 'objective', ellipsis: true },
    {
      title: '时间窗',
      key: 'period',
      width: 200,
      render: (_: unknown, record: Iteration) =>
        `${formatDate(record.start_date)} ~ ${formatDate(record.end_date)}`,
    },
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
      width: 150,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, record: Iteration) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => navigate(`/iterations/${record.id}`)}>
            进入
          </Button>
          <Button type="link" size="small" onClick={() => openModal(record)}>
            编辑
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

  const pending = createMutation.isPending || updateMutation.isPending;

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => openModal(null)}
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
        title={editing ? '编辑迭代' : '新建迭代'}
        open={modalOpen}
        confirmLoading={pending}
        onOk={() => form.submit()}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        destroyOnClose
      >
        {editing === null && (
          <Typography.Paragraph type="secondary">
            编号自动自增，新迭代初始状态为「已计划」。
          </Typography.Paragraph>
        )}
        <Form<IterationFormValues> form={form} layout="vertical" onFinish={handleSubmit}>
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
          <Space size={12}>
            <Form.Item name="start_date" label="开始日期">
              <DatePicker placeholder="选择开始日期" />
            </Form.Item>
            <Form.Item name="end_date" label="结束日期">
              <DatePicker placeholder="选择结束日期" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
