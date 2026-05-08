import { Navigate } from "react-router-dom"
import { useAuthStore } from "@/stores/auth"

export function ProtectedRoute({ children }: { children: JSX.Element }) {
  const session = useAuthStore((state) => state.session)

  if (!session) {
    return <Navigate to="/login" replace />
  }

  return children
}
