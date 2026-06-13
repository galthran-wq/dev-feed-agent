<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

onMounted(() => {
  if (!auth.user) {
    auth.fetchUser()
  }
})
</script>

<template>
  <div class="dashboard">
    <h1>Dashboard</h1>

    <div v-if="auth.user" class="user-card">
      <h2>{{ auth.user.email }}</h2>
      <dl>
        <dt>User ID</dt>
        <dd>{{ auth.user.id }}</dd>
        <dt>Superuser</dt>
        <dd>{{ auth.user.is_superuser ? 'Yes' : 'No' }}</dd>
        <dt>Created</dt>
        <dd>{{ new Date(auth.user.created_at).toLocaleDateString() }}</dd>
      </dl>
    </div>

    <p v-else class="loading">Loading user info...</p>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 600px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.user-card {
  margin-top: 1.5rem;
  padding: 1.5rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.user-card h2 {
  margin: 0 0 1rem;
}

.user-card dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.5rem 1rem;
  margin: 0;
}

.user-card dt {
  font-weight: 500;
  color: #6b7280;
}

.user-card dd {
  margin: 0;
}

.loading {
  color: #6b7280;
}
</style>
