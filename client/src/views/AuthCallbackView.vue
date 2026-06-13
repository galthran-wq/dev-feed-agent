<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const error = ref('')

onMounted(async () => {
  // The backend delivers the JWT in the URL fragment (#token=...), which never
  // reaches the server/logs. Read it, then scrub it from the address bar.
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token')
  history.replaceState(null, '', window.location.pathname)
  if (!token) {
    error.value = 'Missing sign-in token.'
    return
  }
  try {
    await auth.setToken(token)
    router.replace('/connected')
  } catch {
    error.value = 'Could not complete sign-in.'
  }
})
</script>

<template>
  <div class="callback">
    <p v-if="!error">Signing you in…</p>
    <div v-else class="error">
      <p>{{ error }}</p>
      <RouterLink to="/">Back to start</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.callback {
  display: flex;
  justify-content: center;
  padding: 4rem 1.5rem;
  color: var(--color-text-muted);
}
.error {
  text-align: center;
  color: #b91c1c;
}
</style>
