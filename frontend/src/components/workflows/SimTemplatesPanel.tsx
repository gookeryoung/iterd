/** 仿真模板管理面板：列表 + 新建/编辑 Modal（求解器选择 + 阈值 JSON），供模板管理页「仿真模板」Tab 使用。 */

import { useState } from 'react';
import {
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import {
  createSimTemplate,
  fetchSimTemplates,
  fetchSolvers,
  updateSimTemplate,
} from '../../api/simulation';
import { extractErrorMessage } from '../../api/client';
import type { SimTemplate, SimTemplateUpdateInput } from '../../types';
import { formatDateTime } from '../../utils/format';

/** 模板表单值（新建/编辑共用）。 */
interface TemplateFormValues {
  code: string;
  name: string;
  solver_type: string;
  project_id: number | null;
  thresholds: string;
  description: string;
  enabled?: boolean;
}

/** 仿真模板面板属性。 */
interface SimTemplatesPanelProps {
  /** 项目选项（模板范围选择）。 */
  projectOptions: { value: number; label: string }[];
}

export default function SimTemplatesPanel({ projectOptions }: SimTemplatesPanelProps) {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<SimTemplate | null>(null);
  const [form] = Form.useForm<TemplateFormValues>();

  const templatesQuery = useQuery({
    queryKey: ['sim-templates', 'all'],
    queryFn: () => fetchSimTemplates(),
  });

  const solversQuery = useQuery({
    queryKey: ['solvers'],
    queryFn: fetchSolvers,
  });

  // 打开编辑时回填表单（新建时重置为默认值）
  const openModal = (template: SimTemplate | null) => {
    setEditingTemplate(template);
    form.setFieldsValue(
      template
        ? {
            code: template.code,
            name: template.name,
            solver_type: template.solver_type,
            project_id: template.project_id,
            thresholds: template.thresholds ? JSON.stringify(template.thresholds) : '',
            description: template.description,
            enabled: template.enabled,
          }
        : {
            code: '',
            name: '',
            solver_type: 'beam_static',
            project_id: null,
            thresholds: '',
            description: '',
            enabled: true,
          },
    );
    setTemplateModalOpen(true);
  };

  const saveTemplateMutation = useMutation({
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
      if (editingTemplate) {
        const patch: SimTemplateUpdateInput = {
          name: values.name,
          solver_type: values.solver_type,
          thresholds,
          description: values.description,
          enabled: values.enabled ?? true,
        };
        return updateSimTemplate(editingTemplate.id, patch);
      }
      return createSimTemplate({
        code: values.code,
        name: values.name,
        solver_type: values.solver_type,
        project_id: values.project_id ?? null,
        thresholds,
        description: values.description,
      });
    },
    onSuccess: (template: SimTemplate) => {
      message.success(editingTemplate ? `模板 ${template.code} 已更新` : `模板 ${template.code} 已创建`);
      setTemplateModalOpen(false);
      setEditingTemplate(null);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['sim-templates'] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const columns: ColumnsType<SimTemplate> = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 140, render: (code: string) => <Typography.Text code>{code}</Typography.Text> },
    { title: '名称', dataIndex: 'name', key: 'name', width: 160 },
    { title: '求解器', dataIndex: 'solver_type', key: 'solver_type', width: 130, render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
    {
      title: '范围',
      dataIndex: 'project_id',
      key: 'scope',
      width: 120,
      render: (projectId: number | null) =>
        projectId === null ? <Tag>全局</Tag> : <Tag color="blue">{projectOptions.find((o) => o.value === projectId)?.label ?? `项目 #${projectId}`}</Tag>,
    },
    {
      title: '验收阈值',
      key: 'thresholds',
      render: (_: unknown, record: SimTemplate) =>
        record.thresholds ? (
          <Typography.Text code style={{ fontSize: 12 }}>
            {JSON.stringify(record.thresholds)}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">未设置（仅记录不判定）</Typography.Text>
        ),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean) => (enabled ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 150, render: (v: string) => formatDateTime(v) },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, record: SimTemplate) => (
        <Button type="link" size="small" onClick={() => openModal(record)}>
          编辑
        </Button>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal(null)}>
          新建仿真模板
        </Button>
      </div>

      <Table<SimTemplate>
        rowKey="id"
        columns={columns}
        dataSource={templatesQuery.data ?? []}
        loading={templatesQuery.isPending}
        pagination={false}
        size="middle"
        locale={{
          emptyText: (
            <Empty description="暂无仿真模板">
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openModal(null)}>
                新建第一个模板
              </Button>
            </Empty>
          ),
        }}
      />

      {/* 新建/编辑模板 Modal */}
      <Modal
        title={editingTemplate ? `编辑仿真模板（${editingTemplate.code}）` : '新建仿真模板'}
        open={templateModalOpen}
        onCancel={() => {
          setTemplateModalOpen(false);
          setEditingTemplate(null);
        }}
        onOk={() => form.submit()}
        confirmLoading={saveTemplateMutation.isPending}
        destroyOnHidden
      >
        <Form<TemplateFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => saveTemplateMutation.mutate(values)}
        >
          <Space size={16} style={{ display: 'flex' }} align="start">
            <Form.Item name="code" label="模板编码" rules={[{ required: true, message: '请输入模板编码' }]} style={{ width: 200 }}>
              <Input placeholder="BEAM-CHECK" disabled={editingTemplate !== null} />
            </Form.Item>
            <Form.Item name="project_id" label="所属项目（空为全局）" style={{ width: 240 }}>
              <Select allowClear placeholder="全局" disabled={editingTemplate !== null} options={projectOptions} />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
              <Switch />
            </Form.Item>
          </Space>
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
            <Input placeholder="梁强度校核" />
          </Form.Item>
          <Form.Item name="solver_type" label="求解器" rules={[{ required: true, message: '请选择求解器' }]}>
            <Select
              loading={solversQuery.isPending}
              options={(solversQuery.data ?? []).map((s) => ({ value: s.solver_type, label: `${s.solver_type}（${s.description}）` }))}
            />
          </Form.Item>
          <Form.Item
            name="thresholds"
            label="验收阈值（JSON，min/max）"
            extra={'示例：{"max_stress":{"max":100},"safety_factor":{"min":1.5}}；留空表示仅记录不判定'}
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
