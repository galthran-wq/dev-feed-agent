import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import {
  loginUser,
  createAnonUser,
  registerWithToken,
  getCurrentUser,
  type UserResponse,
} from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserResponse | null>(null)
  const token = ref<string | null>(localStorage.getItem('token'))
  const isAuthenticated = computed(() => !!token.value && !!user.value)

  async function login(email: string, password: string) {
    const response = await loginUser(email, password)
    token.value = response.access_token
    user.value = response.user
    localStorage.setItem('token', response.access_token)
  }

  async function register(email: string, password: string) {
    // Step 1: create anonymous user to get a token
    const anon = await createAnonUser()
    token.value = anon.access_token
    localStorage.setItem('token', anon.access_token)

    // Step 2: register with email/password using the anon token
    try {
      const response = await registerWithToken(email, password)
      token.value = response.access_token
      user.value = response.user
      localStorage.setItem('token', response.access_token)
    } catch (error) {
      token.value = null
      localStorage.removeItem('token')
      throw error
    }
  }

  async function fetchUser() {
    try {
      user.value = await getCurrentUser()
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  return { user, token, isAuthenticated, login, register, fetchUser, logout }
})
