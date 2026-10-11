/** 项目列表页：树形 Table（支持子项目）+ 新建/编辑项目 Modal，行点击进入详情。 */

import { useMemo, useState } from 'react';
import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { createProject, fetchProjects, updateProject } from '../api/projects';
import { extractErrorMessage } from '../api/client';
import type { Project, ProjectInput } from '../types';
import { formatDateTime } from '../utils/format';

/** 项目表单值。 */
interface ProjectFormValues {
  code: string;
  name: string;
  description?: string;
  status: string;
}

/** 树形节点：项目 + 子节点。 */
interface ProjectNode extends Project {
  children?: ProjectNode[];
}

/** 由扁平列表构建项目树（parent_id 为空为根节点）。 */
function buildTree(projects: Project[]): ProjectNode[] {
  const nodes = new Map<number, ProjectNode>();
  for (const project of projects) {
    nodes.set(project.id, { ...project });
  }
  const roots: ProjectNode[] = [];
  for (const project of projects) {
    const node = nodes.get(project.id) as ProjectNode;
    const parent = project.parent_id !== null ? nodes.get(project.parent_id) : undefined;
    if (parent) {
      parent.children = parent.children ?? [];
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

export default function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [parentId, setParentId] = useState<number | null>(null);
  const [form] = Form.useForm<ProjectFormValues>();

  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  });

  const invalidateProjects = () => {
    void queryClient.invalidateQueries({ queryKey: ['projects'] });
  };

  const createMutation = useMutation({
    mutationFn: (values: ProjectInput) => createProject(values),
    onSuccess: () => {
      message.success('项目创建成功');
      setModalOpen(false);
      form.resetFields();
      invalidateProjects();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: number; values: ProjectInput }) => updateProject(id, values),
    onSuccess: () => {
      message.success('项目已更新');
      setModalOpen(false);
      setEditing(null);
      invalidateProjects();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const projects = projectsQuery.data ?? [];
  const treeData = useMemo(() => buildTree(projects), [projects]);
  const projectNameMap = useMemo(
    () => new Map(projects.map((project) => [project.id, `${project.code} ${project.name}`])),
    [projects],
  );

  /** 打开新建/编辑 Modal。 */
  const openModal = (project: Project | null, parent: number | null) => {
    setEditing(project);
    setParentId(parent);
    setModalOpen(true);
    if (project) {
      form.setFieldsValue({
        code: project.code,
        name: project.name,
        description: project.description,
        status: project.status,
      });
    } else {
      form.resetFields();
      form.setFieldsValue({ status: 'active' });
    }
  };

  const handleSubmit = (values: ProjectFormValues) => {
    const payload: ProjectInput = {
      code: values.code.trim(),
      name: values.name.trim(),
      description: values.description?.trim() ?? '',
      status: values.status,
      parent_id: editing ? undefined : parentId,
    };
    if (editing) {
      updateMutation.mutate({ id: editing.id, values: payload });
      return;
    }
    createMutation.mutate(payload);
  };

  const columns: ColumnsType<ProjectNode> = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 160 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>{status}</Tag>
      ),
    },
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
      width: 200,
      render: (_: unknown, record: ProjectNode) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            onClick={() => openModal(record, null)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => openModal(null, record.id)}
          >
            新建子项目
          </Button>
        </Space>
      ),
    },
  ];

  const pending = createMutation.isPending || updateMutation.isPending;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          项目管理
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => openModal(null, null)}
        >
          新建项目
        </Button>
      </div>

      <Table<ProjectNode>
        rowKey="id"
        columns={columns}
        dataSource={treeData}
        loading={projectsQuery.isPending}
        rowHoverable
        expandable={{ defaultExpandAllRows: true }}
        onRow={(record) => ({
          style: { cursor: 'pointer' },
          onClick: () => navigate(`/projects/${record.id}`),
        })}
        pagination={false}
        locale={{ emptyText: '暂无项目' }}
      />

      <Modal
        title={editing ? '编辑项目' : parentId ? '新建子项目' : '新建项目'}
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
          <Form.Item label="父项目">
            <Select<number | null>
              value={parentId}
              onChange={(value) => setParentId(value ?? null)}
              allowClear
              placeholder="根目录（不选则为顶级项目）"
              options={projects.map((project) => ({
                value: project.id,
                label: projectNameMap.get(project.id) ?? project.name,
              }))}
            />
          </Form.Item>
        )}
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
            <Input placeholder="如 PRJ-001" disabled={editing !== null} />
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
          <Form.Item name="status" label="状态">
            <Select<string>
              options={[
                { value: 'active', label: '进行中' },
                { value: 'archived', label: '已归档' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
