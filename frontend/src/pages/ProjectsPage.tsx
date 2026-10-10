/** 项目列表页：Table 展示 + 新建项目 Modal，行点击进入详情。 */

import { useState } from 'react';
import { Button, Form, Input, Modal, Table, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { createProject, fetchProjects } from '../api/projects';
import { extractErrorMessage } from '../api/client';
import type { Project, ProjectInput } from '../types';
import { formatDateTime } from '../utils/format';

/** 新建项目表单值。 */
interface ProjectFormValues {
  code: string;
  name: string;
  description?: string;
}

export default function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<ProjectFormValues>();

  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  });

  const createMutation = useMutation({
    mutationFn: (values: ProjectInput) => createProject(values),
    onSuccess: () => {
      message.success('项目创建成功');
      setModalOpen(false);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const columns: ColumnsType<Project> = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 160 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string) => formatDateTime(value),
    },
  ];

  const handleSubmit = (values: ProjectFormValues) => {
    createMutation.mutate({
      code: values.code.trim(),
      name: values.name.trim(),
      description: values.description?.trim() ?? '',
    });
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          项目管理
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            form.resetFields();
            setModalOpen(true);
          }}
        >
          新建项目
        </Button>
      </div>

      <Table<Project>
        rowKey="id"
        columns={columns}
        dataSource={projectsQuery.data ?? []}
        loading={projectsQuery.isPending}
        rowHoverable
        onRow={(record) => ({
          style: { cursor: 'pointer' },
          onClick: () => navigate(`/projects/${record.id}`),
        })}
        pagination={false}
        locale={{ emptyText: '暂无项目' }}
      />

      <Modal
        title="新建项目"
        open={modalOpen}
        confirmLoading={createMutation.isPending}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form<ProjectFormValues>
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
        >
          <Form.Item
            name="code"
            label="编码"
            rules={[{ required: true, message: '请输入项目编码' }]}
          >
            <Input placeholder="如 PRJ-001" />
          </Form.Item>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入项目名称' }]}
          >
            <Input placeholder="项目名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="项目描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
