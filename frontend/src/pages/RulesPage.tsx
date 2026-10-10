/** 规则库页：规则条目 Table + 新建规则 Modal + 规则集管理区块。 */

import { useState } from 'react';
import {
  Button,
  Card,
  Divider,
  Form,
  Input,
  Modal,
  Select,
  Table,
  Tag,
  Typography,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import { createRule, createRuleSet, fetchRules, fetchRuleSets, RULE_CATEGORY_OPTIONS, SEVERITY_OPTIONS } from '../api/rules';
import { extractErrorMessage } from '../api/client';
import {
  RULE_CATEGORY_LABELS,
  SEVERITY_LABELS,
  type RuleCategory,
  type RuleInput,
  type RuleItem,
  type RuleSet,
  type Severity,
} from '../types';
import { SeverityTag } from '../components/StatusTags';
import { formatDateTime } from '../utils/format';

/** 新建规则表单值。 */
interface RuleFormValues {
  code: string;
  name: string;
  category: RuleCategory;
  checker_type: string;
  params?: string;
  severity_default: Severity;
  description?: string;
}

/** 新建规则集表单值。 */
interface RuleSetFormValues {
  name: string;
  rule_ids: number[];
}

/** 规则库页。 */
export default function RulesPage() {
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [ruleModalOpen, setRuleModalOpen] = useState(false);
  const [ruleSetModalOpen, setRuleSetModalOpen] = useState(false);
  const [ruleForm] = Form.useForm<RuleFormValues>();
  const [ruleSetForm] = Form.useForm<RuleSetFormValues>();

  const rulesQuery = useQuery({
    queryKey: ['rules'],
    queryFn: () => fetchRules(),
  });

  const ruleSetsQuery = useQuery({
    queryKey: ['rule-sets', undefined],
    queryFn: () => fetchRuleSets(),
  });

  /** 校验参数为合法 JSON。 */
  const validateParams = (_rule: unknown, value: string | undefined): Promise<void> => {
    if (!value || value.trim().length === 0) {
      return Promise.resolve();
    }
    try {
      JSON.parse(value);
      return Promise.resolve();
    } catch {
      return Promise.reject(new Error('参数必须为合法 JSON'));
    }
  };

  const createRuleMutation = useMutation({
    mutationFn: (input: RuleInput) => createRule(input),
    onSuccess: () => {
      message.success('规则创建成功');
      setRuleModalOpen(false);
      ruleForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['rules'] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const createRuleSetMutation = useMutation({
    mutationFn: (values: { name: string; rule_ids: number[] }) =>
      createRuleSet({ name: values.name, rule_ids: values.rule_ids }),
    onSuccess: () => {
      message.success('规则集创建成功');
      setRuleSetModalOpen(false);
      ruleSetForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['rule-sets'] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const ruleColumns: ColumnsType<RuleItem> = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 140 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '分类',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (category: RuleCategory) => RULE_CATEGORY_LABELS[category] ?? category,
    },
    { title: '检查器', dataIndex: 'checker_type', key: 'checker_type', width: 140 },
    {
      title: '默认级别',
      dataIndex: 'severity_default',
      key: 'severity_default',
      width: 110,
      render: (severity: Severity) => <SeverityTag severity={severity} />,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      render: (enabled: boolean) => (enabled ? <Tag color="green">是</Tag> : <Tag>否</Tag>),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
  ];

  const ruleSetColumns: ColumnsType<RuleSet> = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '所属项目',
      dataIndex: 'project_id',
      key: 'project_id',
      width: 120,
      render: (value: number | null) => (value ? `项目 #${value}` : '全局'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (value: string) => formatDateTime(value),
    },
  ];

  const handleRuleSubmit = (values: RuleFormValues) => {
    let params: Record<string, unknown> | null = null;
    if (values.params && values.params.trim().length > 0) {
      try {
        params = JSON.parse(values.params) as Record<string, unknown>;
      } catch {
        message.error('参数必须为合法 JSON');
        return;
      }
    }
    createRuleMutation.mutate({
      code: values.code.trim(),
      name: values.name.trim(),
      category: values.category,
      checker_type: values.checker_type.trim(),
      params,
      severity_default: values.severity_default,
      description: values.description?.trim() ?? '',
    });
  };

  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        规则库
      </Typography.Title>

      <Card
        title="规则条目"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              ruleForm.resetFields();
              setRuleModalOpen(true);
            }}
          >
            新建规则
          </Button>
        }
      >
        <Table<RuleItem>
          rowKey="id"
          columns={ruleColumns}
          dataSource={rulesQuery.data ?? []}
          loading={rulesQuery.isPending}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无规则' }}
        />
      </Card>

      <Divider />

      <Card
        title="规则集"
        extra={
          <Button
            icon={<PlusOutlined />}
            onClick={() => {
              ruleSetForm.resetFields();
              setRuleSetModalOpen(true);
            }}
          >
            新建规则集
          </Button>
        }
      >
        <Table<RuleSet>
          rowKey="id"
          columns={ruleSetColumns}
          dataSource={ruleSetsQuery.data ?? []}
          loading={ruleSetsQuery.isPending}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无规则集' }}
        />
      </Card>

      {/* 新建规则 Modal */}
      <Modal
        title="新建规则"
        open={ruleModalOpen}
        confirmLoading={createRuleMutation.isPending}
        onOk={() => ruleForm.submit()}
        onCancel={() => setRuleModalOpen(false)}
        destroyOnClose
      >
        <Form<RuleFormValues> form={ruleForm} layout="vertical" onFinish={handleRuleSubmit}>
          <Form.Item name="code" label="编码" rules={[{ required: true, message: '请输入规则编码' }]}>
            <Input placeholder="如 RULE-D-001" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="规则名称" />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true, message: '请选择分类' }]}>
            <Select<RuleCategory> options={RULE_CATEGORY_OPTIONS} placeholder="选择分类" />
          </Form.Item>
          <Form.Item
            name="checker_type"
            label="检查器类型"
            rules={[{ required: true, message: '请输入检查器类型' }]}
          >
            <Input placeholder="如 missing_dimension" />
          </Form.Item>
          <Form.Item
            name="params"
            label="参数（JSON）"
            rules={[{ validator: validateParams }]}
          >
            <Input.TextArea rows={3} placeholder='如 {"min_value": 10}（可选）' />
          </Form.Item>
          <Form.Item name="severity_default" label="默认严重级别" initialValue="warning">
            <Select<Severity> options={SEVERITY_OPTIONS} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="规则描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新建规则集 Modal */}
      <Modal
        title="新建规则集"
        open={ruleSetModalOpen}
        confirmLoading={createRuleSetMutation.isPending}
        onOk={() => ruleSetForm.submit()}
        onCancel={() => setRuleSetModalOpen(false)}
        destroyOnClose
      >
        <Form<RuleSetFormValues>
          form={ruleSetForm}
          layout="vertical"
          onFinish={(values) =>
            createRuleSetMutation.mutate({ name: values.name.trim(), rule_ids: values.rule_ids })
          }
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入规则集名称' }]}
          >
            <Input placeholder="规则集名称" />
          </Form.Item>
          <Form.Item
            name="rule_ids"
            label="包含规则"
            rules={[{ required: true, message: '请至少选择一条规则' }]}
          >
            <Select<number>
              mode="multiple"
              placeholder="选择规则（可多选）"
              loading={rulesQuery.isPending}
              options={(rulesQuery.data ?? []).map((rule) => ({
                value: rule.id,
                label: `${rule.code} ${rule.name}（${SEVERITY_LABELS[rule.severity_default]}）`,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
