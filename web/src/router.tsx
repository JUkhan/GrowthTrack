import { Navigate, createBrowserRouter } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'

export const router = createBrowserRouter([
  { path: '/', element: <LoginPage /> },
  { path: '/home', element: <HomePage /> },
  { path: '/forgot-password', element: <ForgotPasswordPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
  { path: '*', element: <Navigate to="/" replace /> },
])
