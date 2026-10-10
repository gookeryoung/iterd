/** 迭代详情 - 产物 Tab：产物列表 / 新建产物 / 上传新版本 / 版本历史与下载。 */

import { useState } from 'react';
import {
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Upload,
  Typography,
} from 'antd';
import { InboxOutlined, PlusOutlined, UploadOutlined, HistoryOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload/interface';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import {
  CATEGORY_OPTIONS,
  createArtifact,
  downloadVersion,
  fetchArtifacts,
  fetchVersions,
  uploadVersion,
} from '../api/artifacts';
import { extractErrorMessage } from '../api/client';
import {
  type Artifact,
  type ArtifactCategory,
  type ArtifactInput,
  type ArtifactVersion,
} from '../types';
import { CategoryTag } from './StatusTags';
import { formatDateTime, formatSize, shortSha } from '../utils/format';

/** 新建产物表单值。 */
interface ArtifactFormValues {
  code: string;
  name: string;
  category: ArtifactCategory;
  description?: string;
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
  const [versionDrawer, setVersionDrawer] = useState<VersionDrawerState>({ open: false, artifact: null });
  const [uploadTarget, setUploadTarget] = useState<Artifact | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [artifactForm] = Form.useForm<ArtifactFormValues>();
  const [uploadForm] = Form.useForm<UploadFormValues>();

  const artifactsQuery = useQuery({
    queryKey: ['artifacts', iterationId],
    queryFn: () => fetchArtifacts({ iteration_id: iterationId }),
  });

  // 版本历史（Drawer 打开时拉取）
  const versionsQuery = useQuery({
    queryKey: ['versions', versionDrawer.artifact?.id],
    queryFn: () => fetchVersions(versionDrawer.artifact?.id as number),
    enabled: versionDrawer.open && versionDrawer.artifact !== null,
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
      // 若版本历史 Drawer 打开，联动刷新
      if (versionDrawer.open && versionDrawer.artifact) {
        void queryClient.invalidateQueries({
          queryKey: ['versions', versionDrawer.artifact.id],
        });
      }
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
      width: 240,
      render: (_: unknown, record: Artifact) => (
        <Space>
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
      width: 90,
      render: (_: unknown, record: ArtifactVersion) => (
        <Button
          type="link"
          size="small"
          loading={downloadMutation.isPending && downloadMutation.variables?.id === record.id}
          onClick={() => downloadMutation.mutate(record)}
        >
          下载
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
        dataSource={artifactsQuery.data ?? []}
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
            <Input.TextArea rows={3} placeholder='如 {"source": "CAD"}（可选）' />
          </Form.Item>
        </Form>
      </Modal>

      {/* 版本历史 Drawer */}
      <Drawer
        title={`版本历史${versionDrawer.artifact ? ` - ${versionDrawer.artifact.name}` : ''}`}
        width={900}
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
    </div>
  );
}
