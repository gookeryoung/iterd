/** 侧边栏布局：导航菜单 + 当前用户 + 退出登录。 */

import { useMemo } from 'react';
import { Avatar, Dropdown, Layout, Menu, Space, Typography, theme } from 'antd';
import {
  AuditOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  LogoutOutlined,
  ProjectOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { clearCredentials } from '../api/client';
import { fetchMe } from '../api/auth';

const { Sider, Header, Content } = Layout;

/** 主导航菜单项。 */
const MENU_ITEMS = [
  { key: '/', icon: <ProjectOutlined />, label: '项目管理' },
  { key: '/rules', icon: <ExperimentOutlined />, label: '规则库' },
  { key: '/workflows', icon: <DeploymentUnitOutlined />, label: '审查模板' },
  { key: '/audit', icon: <AuditOutlined />, label: '审计日志' },
];

/** 根据 pathname 计算选中菜单 key。 */
function resolveSelectedKey(pathname: string): string {
  if (pathname.startsWith('/rules')) {
    return '/rules';
  }
  if (pathname.startsWith('/workflows')) {
    return '/workflows';
  }
  if (pathname.startsWith('/audit')) {
    return '/audit';
  }
  return '/';
}

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = theme.useToken();

  const meQuery = useQuery({ queryKey: ['auth', 'me'], queryFn: fetchMe, staleTime: 60000 });

  const selectedKey = useMemo(() => resolveSelectedKey(location.pathname), [location.pathname]);

  const handleLogout = () => {
    clearCredentials();
    navigate('/login', { replace: true });
  };

  const userMenu = {
    items: [
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        onClick: handleLogout,
      },
    ],
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={208} theme="dark">
        <div
          style={{
            height: 56,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
          }}
        >
          <Typography.Title level={4} style={{ color: '#fff', margin: 0 }}>
            IterD
          </Typography.Title>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={MENU_ITEMS}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            paddingInline: 24,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space style={{ cursor: 'pointer' }}>
              <Avatar size="small" icon={<UserOutlined />} />
              <span>{meQuery.data?.username ?? '加载中'}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
