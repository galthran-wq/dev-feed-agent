import api from './client'

export interface UserResponse {
  id: string
  email: string | null
  is_verified: boolean
  is_superuser: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: UserResponse
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/users/login', { email, password })
  return data
}

export async function createAnonUser(): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/users/')
  return data
}

export async function registerWithToken(email: string, password: string): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/users/register', { email, password })
  return data
}

export async function getCurrentUser(): Promise<UserResponse> {
  const { data } = await api.get<UserResponse>('/users/me')
  return data
}
