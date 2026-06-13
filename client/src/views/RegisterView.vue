<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)

async function handleRegister() {
  error.value = ''

  if (password.value !== confirmPassword.value) {
    error.value = 'Passwords do not match'
    return
  }

  if (password.value.length < 6) {
    error.value = 'Password must be at least 6 characters'
    return
  }

  loading.value = true
  try {
    await auth.register(email.value, password.value)
    router.push('/dashboard')
  } catch (e: unknown) {
    if (e && typeof e === 'object' && 'response' in e) {
      const axiosError = e as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || 'Registration failed'
    } else {
      error.value = 'Registration failed'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <form class="auth-form" @submit.prevent="handleRegister">
      <h1>Create account</h1>

      <div v-if="error" class="error">{{ error }}</div>

      <label>
        Email
        <input v-model="email" type="email" required autocomplete="email" />
      </label>

      <label>
        Password
        <input v-model="password" type="password" required autocomplete="new-password" />
      </label>

      <label>
        Confirm password
        <input v-model="confirmPassword" type="password" required autocomplete="new-password" />
      </label>

      <button type="submit" :disabled="loading">
        {{ loading ? 'Creating account...' : 'Create account' }}
      </button>

      <p class="link">Already have an account? <RouterLink to="/login">Sign in</RouterLink></p>
    </form>
  </div>
</template>

<style scoped src="@/assets/auth.css"></style>
