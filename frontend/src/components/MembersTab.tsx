/** 项目详情 - 成员 Tab：成员列表 / 添加成员（用户列表 403 时隐藏入口）。 */

import { useState } from 'react';
import { Button, Form, Modal, Select, Table, Tooltip, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { App as AntApp } from 'antd';
import { fetchMembers, upsertMember } from '../api/projects';
import { fetchUsers } from '../api/auth';
import { extractErrorMessage, isForbidden } from '../api/client';
import { ROLE_LABELS, type Member, type MemberRole, type User } from '../types';

/** 角色选项。 */
const ROLE_OPTIONS = (Object.keys(ROLE_LABELS) as MemberRole[]).map((role) => ({
  value: role,
  label: ROLE_LABELS[role],
}));

/** 添加成员表单值。 */
interface MemberFormValues {
  user_id: number;
  role: MemberRole;
}

/** 成员 Tab 属性。 */
interface MembersTabProps {
  projectId: number;
}

export default function MembersTab({ projectId }: MembersTabProps) {
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<MemberFormValues>();

  const membersQuery = useQuery({
    queryKey: ['members', projectId],
    queryFn: () => fetchMembers(projectId),
  });

  // 用户列表（管理员接口）：非管理员 403，隐藏添加入口
  const usersQuery = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: fetchUsers,
    retry: false,
  });

  const userForbidden = usersQuery.isError && isForbidden(usersQuery.error);
  const userNameMap = new Map<number, string>(
    (usersQuery.data ?? []).map((user) => [user.id, user.username]),
  );

  const addMutation = useMutation({
    mutationFn: (values: { user_id: number; role: MemberRole }) =>
      upsertMember(projectId, values),
    onSuccess: () => {
      message.success('成员已保存');
      setModalOpen(false);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ['members', projectId] });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  const columns: ColumnsType<Member> = [
    {
      title: '用户名',
      dataIndex: 'user_id',
      key: 'user_id',
      render: (userId: number, record: Member) =>
        record.username || userNameMap.get(userId) || `用户 #${userId}`,
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 140,
      render: (role: MemberRole) => ROLE_LABELS[role] ?? role,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        {userForbidden ? (
          <Tooltip title="仅管理员可查看用户列表">
            <Button type="primary" icon={<PlusOutlined />} disabled>
              添加成员
            </Button>
          </Tooltip>
        ) : (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              form.resetFields();
              setModalOpen(true);
            }}
          >
            添加成员
          </Button>
        )}
      </div>

      <Table<Member>
        rowKey="id"
        columns={columns}
        dataSource={membersQuery.data ?? []}
        loading={membersQuery.isPending}
        pagination={false}
        locale={{ emptyText: '暂无成员' }}
      />

      <Modal
        title="添加成员"
        open={modalOpen}
        confirmLoading={addMutation.isPending}
        onOk={() => form.submit()}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">
          已存在同用户记录时将更新其角色。
        </Typography.Paragraph>
        <Form<MemberFormValues> form={form} layout="vertical" onFinish={(values) => addMutation.mutate(values)}>
          <Form.Item
            name="user_id"
            label="用户"
            rules={[{ required: true, message: '请选择用户' }]}
          >
            <Select<number>
              placeholder="选择用户"
              showSearch
              optionFilterProp="label"
              options={(usersQuery.data ?? []).map((user) => ({
                value: user.id,
                label: user.username,
              }))}
              loading={usersQuery.isPending}
            />
          </Form.Item>
          <Form.Item
            name="role"
            label="角色"
            initialValue="viewer"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select<MemberRole> options={ROLE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
