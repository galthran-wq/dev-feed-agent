import { fileURLToPath } from 'node:url'
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      exclude: ['e2e/**', 'node_modules/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
    },
  }),
)
