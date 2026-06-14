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
  --font-sans: 'Inter Variable', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: var(--font-sans);
  color: var(--color-text);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  /* Inter: enable contextual alternates + disable slashed-zero noise for clean body text. */
  font-feature-settings: 'cv11', 'ss01';
}

a {
  color: var(--color-primary);
}
</style>
