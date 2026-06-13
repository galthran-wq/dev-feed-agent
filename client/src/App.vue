<script setup lang="ts">
import DefaultLayout from '@/layouts/DefaultLayout.vue'
</script>

<template>
  <DefaultLayout />
</template>

<style>
:root {
  --color-primary: #2563eb;
  --color-border: #e5e7eb;
  --color-text: #111827;
  --color-text-muted: #6b7280;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  color: var(--color-text);
  -webkit-font-smoothing: antialiased;
}

a {
  color: var(--color-primary);
}
</style>
