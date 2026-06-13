<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="layout">
    <header v-if="auth.isAuthenticated" class="navbar">
      <RouterLink to="/dashboard" class="brand">{{ 'WebApp' }}</RouterLink>
      <nav>
        <RouterLink to="/dashboard">Dashboard</RouterLink>
        <button class="logout-btn" @click="handleLogout">Logout</button>
      </nav>
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}

.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--color-border);
}

.brand {
  font-weight: 600;
  font-size: 1.125rem;
  text-decoration: none;
  color: inherit;
}

nav {
  display: flex;
  align-items: center;
  gap: 1rem;
}

nav a {
  font-size: 0.875rem;
  text-decoration: none;
  color: inherit;
}

.logout-btn {
  padding: 0.375rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: none;
  font-size: 0.875rem;
  cursor: pointer;
}
</style>
