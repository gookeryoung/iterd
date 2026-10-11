/** 迭代详情 - 产物 Tab：产物列表 / 新建 / 上传版本 / 版本历史与预览下载 / 关联 / 编辑 / 软删。 */

import { useMemo, useState } from 'react';
import {
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Upload,
  Typography,
} from 'antd';
import {
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  InboxOutlined,
  LinkOutlined,
  PlusOutlined,
  UploadOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload/interface';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import {
  CATEGORY_OPTIONS,
  createArtifact,
  createLink,
  deleteArtifact,
  deleteLink,
  downloadVersion,
  fetchArtifacts,
  fetchLinks,
  fetchVersions,
  LINK_TYPE_OPTIONS,
  updateArtifact,
  uploadVersion,
} from '../api/artifacts';
import { extractErrorMessage } from '../api/client';
import {
  type Artifact,
  type ArtifactCategory,
  type ArtifactInput,
  type ArtifactLink,
  type ArtifactVersion,
  type LinkType,
} from '../types';
import { CategoryTag } from './StatusTags';
import PreviewDrawer from './PreviewDrawer';
import { formatDateTime, formatSize, shortSha } from '../utils/format';

/** 新建产物表单值。 */
interface ArtifactFormValues {
  code: string;
  name: string;
  category: ArtifactCategory;
  description?: string;
}

/** 编辑产物表单值。 */
interface EditFormValues {
  name: string;
  description?: string;
  category: ArtifactCategory;
  metadata?: string;
}

/** 上传版本表单值。 */
interface UploadFormValues {
  note?: string;
  metadata?: string;
}

/** 版本历史 Drawer 状态。 */
interface VersionDrawerState {
  open: boolean;
  artifact: Artifact | null;
}

/** 产物 Tab 属性。 */
interface ArtifactTabProps {
  iterationId: number;
}

/** 关联类型中文标签。 */
const LINK_LABELS: Record<LinkType, string> = {
  part_of: '组成',
  refers_to: '引用',
  derived_from: '派生',
};

/** 渲染版本元数据 JSON。 */
function renderMetadata(metadata: Record<string, unknown> | null): string {
  if (!metadata || Object.keys(metadata).length === 0) {
    return '-';
  }
  return JSON.stringify(metadata);
}

export default function ArtifactTab({ iterationId }: ArtifactTabProps) {
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [createOpen, setCreateOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Artifact | null>(null);
  const [versionDrawer, setVersionDrawer] = useState<VersionDrawerState>({ open: false, artifact: null });
  const [linkTarget, setLinkTarget] = useState<Artifact | null>(null);
  const [preview, setPreview] = useState<{ version: ArtifactVersion } | null>(null);
  const [uploadTarget, setUploadTarget] = useState<Artifact | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [artifactForm] = Form.useForm<ArtifactFormValues>();
  const [editForm] = Form.useForm<EditFormValues>();
  const [uploadForm] = Form.useForm<UploadFormValues>();
  const [linkForm] = Form.useForm<{ dst_artifact_id: number; link_type: LinkType }>();

  const artifactsQuery = useQuery({
    queryKey: ['artifacts', iterationId],
    queryFn: () => fetchArtifacts({ iteration_id: iterationId }),
  });

  const artifacts = artifactsQuery.data ?? [];
  const artifactNameMap = useMemo(
    () => new Map(artifacts.map((item) => [item.id, `${item.code} ${item.name}`])),
    [artifacts],
  );

  // 版本历史（Drawer 打开时拉取）
  const versionsQuery = useQuery({
    queryKey: ['versions', versionDrawer.artifact?.id],
    queryFn: () => fetchVersions(versionDrawer.artifact?.id as number),
    enabled: versionDrawer.open && versionDrawer.artifact !== null,
  });

  // 关联列表（Drawer 打开时拉取）
  const linksQuery = useQuery({
    queryKey: ['artifact-links', linkTarget?.id],
    queryFn: () => fetchLinks(linkTarget?.id as number),
    enabled: linkTarget !== null,
  });

  const invalidateArtifacts = () => {
    void queryClient.invalidateQueries({ queryKey: ['artifacts', iterationId] });
  };

  const createMutation = useMutation({
    mutationFn: (values: ArtifactInput) => createArtifact(iterationId, values),
    onSuccess: () => {
      message.success('产物创建成功');
      setCreateOpen(false);
      artifactForm.resetFields();
      invalidateArtifacts();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (args: { artifactId: number; file: File; note: string; metadata?: string }) =>
      uploadVersion(args.artifactId, { file: args.file, note: args.note, metadata: args.metadata }),
    onSuccess: (version) => {
      message.success(`版本 v${version.version_no} 上传成功`);
      setUploadOpen(false);
      uploadForm.resetFields();
      setFileList([]);
      invalidateArtifacts();
      if (versionDrawer.open && versionDrawer.artifact) {
        void queryClient.invalidateQueries({ queryKey: ['versions', versionDrawer.artifact.id] });
      }
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const editMutation = useMutation({
    mutationFn: ({ id, values }: { id: number; values: EditFormValues }) =>
      updateArtifact(id, {
        name: values.name.trim(),
        description: values.description?.trim() ?? '',
        category: values.category,
        metadata: values.metadata && values.metadata.trim() ? (JSON.parse(values.metadata) as Record<string, unknown>) : null,
      }),
    onSuccess: () => {
      message.success('产物已更新');
      setEditTarget(null);
      invalidateArtifacts();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteArtifact(id),
    onSuccess: () => {
      message.success('产物已删除（软删，历史版本保留）');
      invalidateArtifacts();
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const createLinkMutation = useMutation({
    mutationFn: ({ id, values }: { id: number; values: { dst_artifact_id: number; link_type: LinkType } }) =>
      createLink(id, values),
    onSuccess: () => {
      message.success('关联已创建');
      linkForm.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['artifact-links', linkTarget?.id] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const deleteLinkMutation = useMutation({
    mutationFn: ({ id, linkId }: { id: number; linkId: number }) => deleteLink(id, linkId),
    onSuccess: () => {
      message.success('关联已删除');
      void queryClient.invalidateQueries({ queryKey: ['artifact-links', linkTarget?.id] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const downloadMutation = useMutation({
    mutationFn: (version: ArtifactVersion) => downloadVersion(version.id, version.filename),
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  /** 校验元数据为合法 JSON。 */
  const validateMetadata = (_rule: unknown, value: string | undefined): Promise<void> => {
    if (!value || value.trim().length === 0) {
      return Promise.resolve();
    }
    try {
      JSON.parse(value);
      return Promise.resolve();
    } catch {
      return Promise.reject(new Error('元数据必须为合法 JSON'));
    }
  };

  /** 提交上传新版本。 */
  const handleUploadSubmit = (values: UploadFormValues) => {
    if (!uploadTarget) {
      return;
    }
    const file = fileList[0]?.originFileObj;
    if (!(file instanceof File)) {
      message.error('请选择要上传的文件');
      return;
    }
    uploadMutation.mutate({
      artifactId: uploadTarget.id,
      file,
      note: values.note?.trim() ?? '',
      metadata: values.metadata,
    });
  };

  /** 打开编辑弹窗（元数据回填为 JSON 字符串）。 */
  const openEdit = (artifact: Artifact) => {
    setEditTarget(artifact);
    editForm.setFieldsValue({
      name: artifact.name,
      description: artifact.description,
      category: artifact.category,
      metadata: '',
    });
  };

  const artifactColumns: ColumnsType<Artifact> = [
    { title: '编码', dataIndex: 'code', key: 'code', width: 140 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (category: ArtifactCategory) => <CategoryTag category={category} />,
    },
    {
      title: '当前版本',
      dataIndex: 'current_version_id',
      key: 'current_version_id',
      width: 120,
      render: (value: number | null) => (value ? `#${value}` : '无'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 400,
      render: (_: unknown, record: Artifact) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            icon={<UploadOutlined />}
            onClick={() => {
              setUploadTarget(record);
              uploadForm.resetFields();
              setFileList([]);
              setUploadOpen(true);
            }}
          >
            上传新版本
          </Button>
          <Button
            type="link"
            size="small"
            icon={<HistoryOutlined />}
            onClick={() => setVersionDrawer({ open: true, artifact: record })}
          >
            版本历史
          </Button>
          <Button
            type="link"
            size="small"
            icon={<LinkOutlined />}
            onClick={() => setLinkTarget(record)}
          >
            关联
          </Button>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该产物？"
            description="软删后列表不可见，历史版本与存储对象保留。"
            okText="删除"
            cancelText="取消"
            onConfirm={() => deleteMutation.mutate(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const versionColumns: ColumnsType<ArtifactVersion> = [
    { title: '版本号', dataIndex: 'version_no', key: 'version_no', width: 90, render: (v: number) => `v${v}` },
    { title: '文件名', dataIndex: 'filename', key: 'filename', ellipsis: true },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 90,
      render: (size: number) => formatSize(size),
    },
    {
      title: 'SHA256',
      dataIndex: 'sha256',
      key: 'sha256',
      width: 110,
      render: (sha: string) => <Typography.Text code>{shortSha(sha)}</Typography.Text>,
    },
    {
      title: '元数据',
      dataIndex: 'metadata_json',
      key: 'metadata_json',
      ellipsis: true,
      render: (value: Record<string, unknown> | null) => renderMetadata(value),
    },
    { title: '备注', dataIndex: 'note', key: 'note', ellipsis: true },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (value: string) => formatDateTime(value),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: unknown, record: ArtifactVersion) => (
        <Space size={0}>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => setPreview({ version: record })}
          >
            预览
          </Button>
          <Button
            type="link"
            size="small"
            loading={downloadMutation.isPending && downloadMutation.variables?.id === record.id}
            onClick={() => downloadMutation.mutate(record)}
          >
            下载
          </Button>
        </Space>
      ),
    },
  ];

  const linkColumns: ColumnsType<ArtifactLink> = [
    {
      title: '类型',
      dataIndex: 'link_type',
      key: 'link_type',
      width: 100,
      render: (type: LinkType) => <Tag>{LINK_LABELS[type] ?? type}</Tag>,
    },
    {
      title: '关联产物',
      key: 'peer',
      render: (_: unknown, record: ArtifactLink) => {
        const peerId = record.src_artifact_id === linkTarget?.id ? record.dst_artifact_id : record.src_artifact_id;
        return artifactNameMap.get(peerId) ?? `产物 #${peerId}`;
      },
    },
    {
      title: '方向',
      key: 'direction',
      width: 100,
      render: (_: unknown, record: ArtifactLink) =>
        record.src_artifact_id === linkTarget?.id ? '本产物 →' : '→ 本产物',
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, record: ArtifactLink) =>
        linkTarget && (
          <Button
            type="link"
            size="small"
            danger
            loading={deleteLinkMutation.isPending}
            onClick={() => deleteLinkMutation.mutate({ id: linkTarget.id, linkId: record.id })}
          >
            删除
          </Button>
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
            artifactForm.resetFields();
            setCreateOpen(true);
          }}
        >
          新建产物
        </Button>
      </div>

      <Table<Artifact>
        rowKey="id"
        columns={artifactColumns}
        dataSource={artifacts}
        loading={artifactsQuery.isPending}
        pagination={false}
        locale={{ emptyText: '暂无产物' }}
        expandable={{
          rowExpandable: (record) => record.description.length > 0,
          expandedRowRender: (record) => (
            <Typography.Text type="secondary">{record.description}</Typography.Text>
          ),
        }}
      />

      {/* 新建产物 */}
      <Modal
        title="新建产物"
        open={createOpen}
        confirmLoading={createMutation.isPending}
        onOk={() => artifactForm.submit()}
        onCancel={() => setCreateOpen(false)}
        destroyOnClose
      >
        <Form<ArtifactFormValues> form={artifactForm} layout="vertical" onFinish={(values) => createMutation.mutate(values)}>
          <Form.Item name="code" label="编码" rules={[{ required: true, message: '请输入产物编码' }]}>
            <Input placeholder="如 ART-001" />
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入产物名称' }]}>
            <Input placeholder="产物名称" />
          </Form.Item>
          <Form.Item name="category" label="类别" rules={[{ required: true, message: '请选择类别' }]}>
            <Select<ArtifactCategory> options={CATEGORY_OPTIONS} placeholder="选择类别" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="产物描述（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑产物 */}
      <Modal
        title={`编辑产物${editTarget ? ` - ${editTarget.code}` : ''}`}
        open={editTarget !== null}
        confirmLoading={editMutation.isPending}
        onOk={() => editForm.submit()}
        onCancel={() => setEditTarget(null)}
        destroyOnClose
      >
        <Form<EditFormValues>
          form={editForm}
          layout="vertical"
          onFinish={(values) => editMutation.mutate({ id: editTarget?.id as number, values })}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入产物名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="category" label="类别" rules={[{ required: true, message: '请选择类别' }]}>
            <Select<ArtifactCategory> options={CATEGORY_OPTIONS} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="metadata"
            label="当前版本元数据（JSON）"
            extra="留空表示不修改；填写后将覆盖当前版本的元数据"
            rules={[{ validator: validateMetadata }]}
          >
            <Input.TextArea rows={3} placeholder='如 {"材料": "Q235"}' />
          </Form.Item>
        </Form>
      </Modal>

      {/* 上传新版本 */}
      <Modal
        title={`上传新版本${uploadTarget ? ` - ${uploadTarget.name}` : ''}`}
        open={uploadOpen}
        confirmLoading={uploadMutation.isPending}
        onOk={() => uploadForm.submit()}
        onCancel={() => setUploadOpen(false)}
        destroyOnClose
      >
        <Form<UploadFormValues> form={uploadForm} layout="vertical" onFinish={handleUploadSubmit}>
          <Form.Item label="文件" required>
            <Upload.Dragger
              maxCount={1}
              fileList={fileList}
              beforeUpload={() => false}
              onChange={({ fileList: files }) => setFileList(files)}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input.TextArea rows={2} placeholder="版本说明（可选）" />
          </Form.Item>
          <Form.Item
            name="metadata"
            label="元数据（JSON）"
            rules={[{ validator: validateMetadata }]}
          >
            <Input.TextArea rows={3} placeholder='如 {"材料": "Q235", "尺寸": "100x50"}（可选）' />
          </Form.Item>
        </Form>
      </Modal>

      {/* 版本历史 Drawer */}
      <Drawer
        title={`版本历史${versionDrawer.artifact ? ` - ${versionDrawer.artifact.name}` : ''}`}
        width={960}
        open={versionDrawer.open}
        onClose={() => setVersionDrawer({ open: false, artifact: null })}
      >
        <Table<ArtifactVersion>
          rowKey="id"
          columns={versionColumns}
          dataSource={versionsQuery.data ?? []}
          loading={versionsQuery.isPending}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无版本' }}
        />
      </Drawer>

      {/* 关联管理 Drawer */}
      <Drawer
        title={`产物关联${linkTarget ? ` - ${linkTarget.code}` : ''}`}
        width={760}
        open={linkTarget !== null}
        onClose={() => setLinkTarget(null)}
      >
        <Form<{ dst_artifact_id: number; link_type: LinkType }>
          form={linkForm}
          layout="inline"
          style={{ marginBottom: 16 }}
          onFinish={(values) =>
            createLinkMutation.mutate({ id: linkTarget?.id as number, values })
          }
        >
          <Form.Item name="dst_artifact_id" rules={[{ required: true, message: '请选择关联产物' }]}>
            <Select<number>
              style={{ width: 260 }}
              placeholder="选择本迭代内的产物"
              showSearch
              optionFilterProp="label"
              options={artifacts
                .filter((item) => item.id !== linkTarget?.id)
                .map((item) => ({ value: item.id, label: `${item.code} ${item.name}` }))}
            />
          </Form.Item>
          <Form.Item name="link_type" initialValue="part_of">
            <Select<LinkType> style={{ width: 200 }} options={LINK_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={createLinkMutation.isPending}>
              添加关联
            </Button>
          </Form.Item>
        </Form>
        <Table<ArtifactLink>
          rowKey="id"
          columns={linkColumns}
          dataSource={linksQuery.data ?? []}
          loading={linksQuery.isPending}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无关联' }}
        />
      </Drawer>

      {/* 在线预览 */}
      <PreviewDrawer
        versionId={preview?.version.id ?? null}
        filename={preview?.version.filename ?? ''}
        size={preview?.version.size ?? 0}
        onClose={() => setPreview(null)}
      />
    </div>
  );
}
