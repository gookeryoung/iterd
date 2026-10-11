/** 审查模板管理页：列表 + 新建/编辑 Drawer（YAML 编辑 + 实时结构预览）+ YAML 查看。 */

import { useMemo, useState } from 'react';
import {
  Button,
  Drawer,
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
import { CodeOutlined, PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import {
  createWorkflow,
  fetchWorkflows,
  updateWorkflow,
  type WorkflowTemplateInput,
} from '../api/workflows';
import { extractErrorMessage } from '../api/client';
import { fetchProjects } from '../api/projects';
import type { WorkflowTemplate } from '../types';
import { formatDateTime } from '../utils/format';
import YamlBlock from '../components/workflows/YamlBlock';

/** 新建模板默认 YAML（含门禁链示例）。 */
const DEFAULT_DEFINITION = `name: 详细设计审查
description: 静态规则检查通过后执行仿真

jobs:
  rules-check:
    name: 静态规则检查
    uses: rules/check
    with:
      rule_set: 规则集名称
  beam-sim:
    name: 仿真验证
    needs: rules-check
    uses: simulation/run
    with:
      template: 仿真模板编码
`;

/** 表单值。 */
interface TemplateFormValues {
  code: string;
  project_id: number | null;
  definition: string;
  enabled: boolean;
}

/** YAML 首部快速解析（name 行），用于本地预览提示。 */
function previewName(definition: string): string {
  const match = definition.match(/^name:\s*(.+)$/m);
  return match ? match[1].trim() : '';
}

export default function WorkflowTemplatesPage() {
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<WorkflowTemplate | null>(null);
  const [viewTemplate, setViewTemplate] = useState<WorkflowTemplate | null>(null);
  const [form] = Form.useForm<TemplateFormValues>();

  const workflowsQuery = useQuery({ queryKey: ['workflows', 'all'], queryFn: () => fetchWorkflows() });
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: fetchProjects });

  const [projectFilter, setProjectFilter] = useState<number | undefined>(undefined);
  const workflows = useMemo(() => {
    const all = workflowsQuery.data ?? [];
    return projectFilter === undefined
      ? all
      : all.filter((w) => w.project_id === projectFilter || w.project_id === null);
  }, [workflowsQuery.data, projectFilter]);

  const saveMutation = useMutation({
    mutationFn: (values: TemplateFormValues) => {
      if (editing) {
        return updateWorkflow(editing.id, {
          definition: values.definition,
          enabled: values.enabled,
        });
      }
      const payload: WorkflowTemplateInput = {
        code: values.code,
        name: previewName(values.definition) || values.code,
        project_id: values.project_id,
        definition: values.definition,
        enabled: values.enabled,
      };
      return createWorkflow(payload);
    },
    onSuccess: (template) => {
      message.success(`审查模板 ${template.code} 已保存`);
      setEditorOpen(false);
      setEditing(null);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['workflows'] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({
      code: '',
      project_id: null,
      definition: DEFAULT_DEFINITION,
      enabled: true,
    });
    setEditorOpen(true);
  };

  const openEdit = (template: WorkflowTemplate) => {
    setEditing(template);
    form.setFieldsValue({
      code: template.code,
      project_id: template.project_id,
      definition: template.definition,
      enabled: template.enabled,
    });
    setEditorOpen(true);
  };

  const columns: ColumnsType<WorkflowTemplate> = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 140, render: (code: string) => <Typography.Text code>{code}</Typography.Text> },
    { title: '名称', dataIndex: 'name', key: 'name', width: 180 },
    {
      title: '范围',
      dataIndex: 'project_id',
      key: 'scope',
      width: 130,
      render: (projectId: number | null) =>
        projectId === null ? (
          <Tag>全局</Tag>
        ) : (
          <Tag color="blue">
            {(projectsQuery.data ?? []).find((p) => p.id === projectId)?.name ?? `项目 #${projectId}`}
          </Tag>
        ),
    },
    {
      title: '作业',
      key: 'jobs',
      width: 90,
      render: (_: unknown, record: WorkflowTemplate) => `${record.jobs.length} 个`,
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
      width: 180,
      render: (_: unknown, record: WorkflowTemplate) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => setViewTemplate(record)}>
            YAML
          </Button>
          <Button type="link" size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
        </Space>
      ),
    },
  ];

  const definitionValue = Form.useWatch('definition', form);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          审查模板
          <Typography.Text type="secondary" style={{ fontSize: 13, marginLeft: 12, fontWeight: 400 }}>
            YAML 编排的迭代审查流水线（GitHub Actions 模式：jobs / needs / uses / with）
          </Typography.Text>
        </Typography.Title>
        <Space>
          <Select
            style={{ width: 200 }}
            allowClear
            placeholder="按项目过滤（含全局）"
            value={projectFilter}
            onChange={(value) => setProjectFilter(value)}
            options={(projectsQuery.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建模板
          </Button>
        </Space>
      </div>

      <Table<WorkflowTemplate>
        rowKey="id"
        columns={columns}
        dataSource={workflows}
        loading={workflowsQuery.isPending}
        pagination={false}
        size="middle"
        locale={{
          emptyText: (
            <Empty description="暂无审查模板">
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                新建第一个模板
              </Button>
            </Empty>
          ),
        }}
      />

      {/* 新建/编辑 Drawer */}
      <Drawer
        title={editing ? `编辑模板 ${editing.code}` : '新建审查模板'}
        width={720}
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => setEditorOpen(false)}>取消</Button>
            <Button type="primary" loading={saveMutation.isPending} onClick={() => form.submit()}>
              保存（校验 YAML）
            </Button>
          </Space>
        }
      >
        <Form<TemplateFormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Space size={16} style={{ display: 'flex' }} align="start">
            <Form.Item
              name="code"
              label="模板编码"
              rules={[{ required: true, message: '请输入模板编码' }]}
              style={{ width: 200 }}
            >
              <Input placeholder="DESIGN-REVIEW" disabled={editing !== null} />
            </Form.Item>
            <Form.Item name="project_id" label="所属项目（空为全局）" style={{ width: 260 }}>
              <Select
                allowClear
                placeholder="全局"
                disabled={editing !== null}
                options={(projectsQuery.data ?? []).map((p) => ({ value: p.id, label: p.name }))}
              />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
              <Switch />
            </Form.Item>
          </Space>
          <Form.Item
            name="definition"
            label="YAML 定义"
            extra="保存时后端校验：uses 仅支持 rules/check 与 simulation/run；needs 引用须存在且无环"
            rules={[{ required: true, message: '请输入 YAML 定义' }]}
          >
            <Input.TextArea
              rows={16}
              style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 12.5 }}
            />
          </Form.Item>
        </Form>
        {/* 实时结构预览 */}
        {definitionValue && (
          <div style={{ marginTop: 8 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              预览：{previewName(definitionValue) || '（name 缺失，保存时将校验报错）'}
            </Typography.Text>
            <div style={{ marginTop: 6 }}>
              <YamlBlock content={definitionValue} maxHeight={200} />
            </div>
          </div>
        )}
      </Drawer>

      {/* YAML 查看 Modal */}
      <Modal
        title={
          <Space>
            <CodeOutlined />
            <span>{viewTemplate ? `${viewTemplate.code} ${viewTemplate.name}` : ''}</span>
          </Space>
        }
        open={viewTemplate !== null}
        onCancel={() => setViewTemplate(null)}
        footer={null}
        width={680}
      >
        {viewTemplate && <YamlBlock content={viewTemplate.definition} maxHeight={520} />}
      </Modal>
    </div>
  );
}
