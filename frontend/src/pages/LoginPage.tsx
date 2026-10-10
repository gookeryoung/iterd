/** 登录页：用户名 + 密码，成功后存 token 并跳转。 */

import { Button, Card, Form, Input, Typography } from 'antd';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { App as AntApp } from 'antd';
import { getToken, setToken, extractErrorMessage } from '../api/client';
import { login } from '../api/auth';

/** 登录表单值。 */
interface LoginFormValues {
  username: string;
  password: string;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { message } = AntApp.useApp();

  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const loginMutation = useMutation({
    mutationFn: (values: LoginFormValues) => login(values),
    onSuccess: (data) => {
      setToken(data.access_token);
      message.success(`欢迎回来，${data.user.username}`);
      navigate(from, { replace: true });
    },
    onError: (error: unknown) => {
      message.error(extractErrorMessage(error));
    },
  });

  // 已登录则直接进入
  if (getToken()) {
    return <Navigate to="/" replace />;
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: 380, boxShadow: '0 4px 16px rgba(0, 0, 0, 0.08)' }}>
        <Typography.Title level={3} style={{ textAlign: 'center', marginBottom: 4 }}>
          IterD
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center' }}>
          产品迭代式开发系统
        </Typography.Paragraph>
        <Form<LoginFormValues>
          layout="vertical"
          onFinish={(values) => loginMutation.mutate(values)}
          disabled={loginMutation.isPending}
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            block
            loading={loginMutation.isPending}
          >
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
