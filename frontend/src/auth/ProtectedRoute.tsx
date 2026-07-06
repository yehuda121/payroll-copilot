import { Navigate, Outlet } from 'react-router-dom';
import { getRoleHomePath } from './authProvider';
import { useAuth } from './AuthContext';
import type { UserRole } from '../types/auth';

type ProtectedRouteProps = {
  allowedRoles: UserRole[];
};

export function ProtectedRoute({ allowedRoles }: ProtectedRouteProps) {
  const { session, isAuthenticated } = useAuth();

  if (!isAuthenticated || !session) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(session.user.role)) {
    return <Navigate to={getRoleHomePath(session.user.role)} replace />;
  }

  return <Outlet />;
}
