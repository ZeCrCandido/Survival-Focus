import { useAuthStore } from "@/stores/auth"

const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/$/, "")

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE"

export interface ApiRequestOptions<TBody = unknown> {
  method?: HttpMethod
  body?: TBody
  headers?: HeadersInit
}

export async function apiClient<T = unknown>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {} } = options
  const session = useAuthStore.getState().session

  const token = session?.access_token
  console.log(`[API] ${method} ${path}`, {
    hasSession: !!session,
    hasToken: !!token,
    token: token ? `${token.slice(0, 20)}...` : "null",
  })

  const fetchOptions: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  }

  const response = await fetch(`${apiBase}${path}`, fetchOptions)

  if (!response.ok) {
    const errorPayload = await response.json().catch(() => null)
    // Normalize common validation/error shapes into a readable message
    let errorMessage = response.statusText || "Unprocessable response"

    if (errorPayload) {
      if (typeof errorPayload === "string") {
        errorMessage = errorPayload
      } else if (errorPayload.message) {
        errorMessage = errorPayload.message
      } else if (errorPayload.detail) {
        errorMessage = Array.isArray(errorPayload.detail) ? errorPayload.detail.join("; ") : String(errorPayload.detail)
      } else if (errorPayload.errors) {
        try {
          if (Array.isArray(errorPayload.errors)) {
            errorMessage = errorPayload.errors.map((e: any) => (typeof e === 'string' ? e : JSON.stringify(e))).join("; ")
          } else if (typeof errorPayload.errors === 'object') {
            errorMessage = Object.entries(errorPayload.errors).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : String(v)}`).join('; ')
          }
        } catch (e) {
          errorMessage = JSON.stringify(errorPayload)
        }
      } else {
        errorMessage = JSON.stringify(errorPayload)
      }
    }

    const err = new Error(errorMessage)
    // attach payload for further inspection if needed by catch blocks
    ;(err as any).payload = errorPayload
    throw err
  }

  return (await response.json()) as T
}
