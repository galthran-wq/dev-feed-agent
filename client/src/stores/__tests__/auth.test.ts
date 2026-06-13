import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../auth'

vi.mock('@/api/auth', () => ({
  loginUser: vi.fn(),
  createAnonUser: vi.fn(),
  registerWithToken: vi.fn(),
  getCurrentUser: vi.fn(),
}))

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('starts unauthenticated', () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.user).toBeNull()
    expect(auth.token).toBeNull()
  })

  it('login sets user and token', async () => {
    const { loginUser } = await import('@/api/auth')
    const mockLogin = vi.mocked(loginUser)
    mockLogin.mockResolvedValueOnce({
      access_token: 'test-token',
      token_type: 'bearer',
      user: {
        id: '123',
        email: 'test@example.com',
        is_verified: true,
        is_superuser: false,
        created_at: '2024-01-01T00:00:00Z',
      },
    })

    const auth = useAuthStore()
    await auth.login('test@example.com', 'password')

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.token).toBe('test-token')
    expect(auth.user?.email).toBe('test@example.com')
    expect(localStorage.getItem('token')).toBe('test-token')
  })

  it('register creates anon user then registers', async () => {
    const { createAnonUser, registerWithToken } = await import('@/api/auth')
    const mockCreateAnon = vi.mocked(createAnonUser)
    const mockRegister = vi.mocked(registerWithToken)

    mockCreateAnon.mockResolvedValueOnce({
      access_token: 'anon-token',
      token_type: 'bearer',
      user: {
        id: '456',
        email: null,
        is_verified: false,
        is_superuser: false,
        created_at: '2024-01-01T00:00:00Z',
      },
    })
    mockRegister.mockResolvedValueOnce({
      access_token: 'registered-token',
      token_type: 'bearer',
      user: {
        id: '456',
        email: 'new@example.com',
        is_verified: true,
        is_superuser: false,
        created_at: '2024-01-01T00:00:00Z',
      },
    })

    const auth = useAuthStore()
    await auth.register('new@example.com', 'password123')

    expect(auth.token).toBe('registered-token')
    expect(auth.user?.email).toBe('new@example.com')
    expect(localStorage.getItem('token')).toBe('registered-token')
  })

  it('register cleans up on failure', async () => {
    const { createAnonUser, registerWithToken } = await import('@/api/auth')
    const mockCreateAnon = vi.mocked(createAnonUser)
    const mockRegister = vi.mocked(registerWithToken)

    mockCreateAnon.mockResolvedValueOnce({
      access_token: 'anon-token',
      token_type: 'bearer',
      user: {
        id: '456',
        email: null,
        is_verified: false,
        is_superuser: false,
        created_at: '2024-01-01T00:00:00Z',
      },
    })
    mockRegister.mockRejectedValueOnce(new Error('Registration failed'))

    const auth = useAuthStore()
    await expect(auth.register('new@example.com', 'password123')).rejects.toThrow(
      'Registration failed',
    )

    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('logout clears state', async () => {
    const auth = useAuthStore()
    auth.token = 'some-token'
    auth.user = {
      id: '123',
      email: 'test@example.com',
      is_verified: true,
      is_superuser: false,
      created_at: '2024-01-01T00:00:00Z',
    }
    localStorage.setItem('token', 'some-token')

    auth.logout()

    expect(auth.isAuthenticated).toBe(false)
    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })
})
