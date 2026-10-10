/** 登录守卫：无 token 重定向登录页，登录后回跳原路径。 */

import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { getToken } from '../api/client';

export default function RequireAuth() {
  const location = useLocation();
  if (!getToken()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
