<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getStatus, getTelegramLink, type AgentStatus, type TelegramLink } from '@/api/agent'

const status = ref<AgentStatus | null>(null)
const telegram = ref<TelegramLink | null>(null)
const loading = ref(true)

async function refresh() {
  loading.value = true
  try {
    ;[status.value, telegram.value] = await Promise.all([getStatus(), getTelegramLink()])
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="connected">
    <h1>You're connected 🎉</h1>

    <div v-if="loading && !status" class="muted">Loading…</div>

    <template v-else-if="status">
      <ul class="checklist">
        <li>
          <span class="ok">✓</span>
          GitHub: <strong>@{{ status.github_username }}</strong>
        </li>
        <li>
          <span :class="status.profile_built ? 'ok' : 'pending'">{{
            status.profile_built ? '✓' : '…'
          }}</span>
          Interest profile:
          <strong>{{ status.profile_built ? 'ready' : 'building from your activity' }}</strong>
        </li>
        <li>
          <span :class="status.telegram_linked ? 'ok' : 'pending'">{{
            status.telegram_linked ? '✓' : '…'
          }}</span>
          Telegram: <strong>{{ status.telegram_linked ? 'linked' : 'not linked yet' }}</strong>
        </li>
      </ul>

      <p class="instructions">
        Everything happens in Telegram — that's where your feed arrives and where you chat with the
        agent to steer it.
      </p>

      <a
        v-if="telegram?.url"
        class="telegram-btn"
        :href="telegram.url"
        target="_blank"
        rel="noopener"
      >
        {{ status.telegram_linked ? 'Open Telegram' : 'Go to Telegram' }}
      </a>
      <p v-else-if="telegram && !telegram.bot_configured" class="muted">
        The Telegram bot isn't configured on this server yet.
      </p>

      <button class="refresh" @click="refresh" :disabled="loading">Refresh status</button>
    </template>
  </div>
</template>

<style scoped>
.connected {
  max-width: 520px;
  margin: 0 auto;
  padding: 3rem 1.5rem;
}
h1 {
  font-size: 1.75rem;
}
.checklist {
  list-style: none;
  padding: 0;
  margin: 1.5rem 0;
}
.checklist li {
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--color-border);
}
.ok {
  color: #16a34a;
  font-weight: 700;
  margin-right: 0.5rem;
}
.pending {
  color: #d97706;
  font-weight: 700;
  margin-right: 0.5rem;
}
.instructions {
  color: var(--color-text-muted);
  line-height: 1.6;
}
.telegram-btn {
  display: inline-block;
  margin-top: 0.5rem;
  padding: 0.75rem 1.25rem;
  font-weight: 600;
  color: #fff;
  background: #229ed9;
  border-radius: 8px;
  text-decoration: none;
}
.refresh {
  display: block;
  margin-top: 1.5rem;
  padding: 0.4rem 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: none;
  cursor: pointer;
}
.muted {
  color: var(--color-text-muted);
}
</style>
