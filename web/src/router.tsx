import { Navigate, createBrowserRouter } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import NotificationComposePage from './pages/NotificationComposePage'
import RecipientsPage from './pages/RecipientsPage'
import ResetPasswordPage from './pages/ResetPasswordPage'

export const router = createBrowserRouter([
  { path: '/', element: <LoginPage /> },
  { path: '/dashboard', element: <DashboardPage /> },
  { path: '/recipients', element: <RecipientsPage /> },
  { path: '/notifications/compose', element: <NotificationComposePage /> },
  { path: '/forgot-password', element: <ForgotPasswordPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
  { path: '*', element: <Navigate to="/" replace /> },
])
