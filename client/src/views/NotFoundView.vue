<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="not-found">
    <h1>404</h1>
    <p>The page you are looking for does not exist.</p>
    <button @click="router.push('/')">Go Home</button>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  text-align: center;
}

.not-found h1 {
  font-size: 4rem;
  margin: 0;
  color: var(--color-text-muted);
}

.not-found p {
  color: var(--color-text-muted);
  margin: 0.5rem 0 1.5rem;
}

.not-found button {
  padding: 0.5rem 1.5rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: none;
  font-size: 0.875rem;
  cursor: pointer;
}
</style>
