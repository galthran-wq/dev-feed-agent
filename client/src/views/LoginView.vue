<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    router.push('/dashboard')
  } catch (e: unknown) {
    if (e && typeof e === 'object' && 'response' in e) {
      const axiosError = e as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || 'Login failed'
    } else {
      error.value = 'Login failed'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <form class="auth-form" @submit.prevent="handleLogin">
      <h1>Sign in</h1>

      <div v-if="error" class="error">{{ error }}</div>

      <label>
        Email
        <input v-model="email" type="email" required autocomplete="email" />
      </label>

      <label>
        Password
        <input v-model="password" type="password" required autocomplete="current-password" />
      </label>

      <button type="submit" :disabled="loading">
        {{ loading ? 'Signing in...' : 'Sign in' }}
      </button>

      <p class="link">Don't have an account? <RouterLink to="/register">Register</RouterLink></p>
    </form>
  </div>
</template>

<style scoped src="@/assets/auth.css"></style>
