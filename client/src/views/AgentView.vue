<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  getProfile,
  updateProfile,
  getInterests,
  rebuildInterests,
  getTelegramLink,
  sendChat,
  getChatHistory,
  getMatches,
  pollNow,
  type GithubProfile,
  type InterestProfile,
  type TelegramLink,
  type SentIssue,
  type ChatMessage,
} from '@/api/agent'

const profile = ref<GithubProfile | null>(null)
const interests = ref<InterestProfile | null>(null)
const telegram = ref<TelegramLink | null>(null)
const matches = ref<SentIssue[]>([])
const messages = ref<ChatMessage[]>([])

const username = ref('')
const token = ref('')
const chatInput = ref('')

const savingProfile = ref(false)
const rebuilding = ref(false)
const polling = ref(false)
const chatting = ref(false)
const status = ref<string>('')

async function loadAll() {
  profile.value = await getProfile()
  username.value = profile.value.github_username ?? ''
  interests.value = await getInterests()
  telegram.value = await getTelegramLink()
  matches.value = await getMatches()
  messages.value = await getChatHistory()
}

async function saveProfile() {
  savingProfile.value = true
  status.value = ''
  try {
    profile.value = await updateProfile({
      github_username: username.value,
      github_token: token.value || undefined,
    })
    token.value = ''
    telegram.value = await getTelegramLink()
    status.value = 'Profile saved.'
  } catch {
    status.value = 'Failed to save profile.'
  } finally {
    savingProfile.value = false
  }
}

async function doRebuild() {
  rebuilding.value = true
  status.value = ''
  try {
    const res = await rebuildInterests()
    interests.value = res.interests
    status.value = `Interest profile rebuilt from ${res.repos_scanned} repositories.`
  } catch {
    status.value = 'Could not rebuild — check your GitHub username and that the agent is configured.'
  } finally {
    rebuilding.value = false
  }
}

async function doPoll() {
  polling.value = true
  status.value = ''
  try {
    const res = await pollNow()
    status.value = `${res.message} — ${res.matches_sent} match(es) delivered.`
    matches.value = await getMatches()
  } catch {
    status.value = 'Poll failed.'
  } finally {
    polling.value = false
  }
}

async function send() {
  const text = chatInput.value.trim()
  if (!text || chatting.value) return
  chatting.value = true
  messages.value.push({ role: 'user', content: text, created_at: new Date().toISOString() })
  chatInput.value = ''
  try {
    const res = await sendChat(text)
    messages.value.push({ role: 'assistant', content: res.reply, created_at: new Date().toISOString() })
    interests.value = res.interests
  } catch {
    messages.value.push({
      role: 'assistant',
      content: 'Sorry, the agent is unavailable right now.',
      created_at: new Date().toISOString(),
    })
  } finally {
    chatting.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="agent">
    <h1>Good-First-Issue Agent</h1>
    <p class="status" v-if="status">{{ status }}</p>

    <section class="card">
      <h2>1. Connect GitHub</h2>
      <label>GitHub username</label>
      <input v-model="username" placeholder="octocat" />
      <label>Personal access token <span class="muted">(optional, lifts rate limits)</span></label>
      <input v-model="token" type="password" :placeholder="profile?.has_github_token ? '•••••• stored' : 'ghp_…'" />
      <button :disabled="savingProfile" @click="saveProfile">
        {{ savingProfile ? 'Saving…' : 'Save' }}
      </button>
    </section>

    <section class="card">
      <h2>2. Connect Telegram</h2>
      <p v-if="telegram?.linked" class="ok">✅ Telegram is linked — matches will be delivered there.</p>
      <template v-else>
        <p class="muted" v-if="!telegram?.bot_configured">
          Telegram bot is not configured on the server yet.
        </p>
        <a
          v-else-if="telegram?.url"
          class="tg-btn"
          :href="telegram.url"
          target="_blank"
          rel="noopener"
        >
          Go to Telegram →
        </a>
      </template>
    </section>

    <section class="card">
      <h2>3. Your interests</h2>
      <button :disabled="rebuilding" @click="doRebuild">
        {{ rebuilding ? 'Building…' : 'Rebuild from GitHub activity' }}
      </button>
      <p class="summary" v-if="interests?.summary">{{ interests.summary }}</p>
      <p class="muted" v-else>No interest profile yet — rebuild from your activity or chat below.</p>
      <div class="chips" v-if="interests">
        <span class="chip" v-for="l in interests.languages" :key="'l-' + l">{{ l }}</span>
        <span class="chip topic" v-for="t in interests.topics" :key="'t-' + t">{{ t }}</span>
      </div>
    </section>

    <section class="card">
      <h2>4. Refine by chatting</h2>
      <div class="chat">
        <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
          <span>{{ m.content }}</span>
        </div>
        <p class="muted" v-if="messages.length === 0">
          e.g. “I’m into Rust CLIs and dev tooling, not web frontend.”
        </p>
      </div>
      <form class="chat-input" @submit.prevent="send">
        <input v-model="chatInput" placeholder="Tell the agent what you like…" />
        <button :disabled="chatting" type="submit">Send</button>
      </form>
    </section>

    <section class="card">
      <h2>5. Matches</h2>
      <button :disabled="polling" @click="doPoll">
        {{ polling ? 'Searching…' : 'Find matches now' }}
      </button>
      <ul class="matches">
        <li v-for="m in matches" :key="m.id">
          <a :href="m.issue_url" target="_blank" rel="noopener">
            🔧 {{ m.repo_full_name }} — {{ m.title }}
          </a>
          <div class="meta">
            🏷 {{ m.languages || 'n/a' }} | ⭐ {{ m.stars }} | Match: {{ m.relevance.toFixed(2) }}
          </div>
          <div class="reason" v-if="m.reason">{{ m.reason }}</div>
        </li>
      </ul>
      <p class="muted" v-if="matches.length === 0">No matches yet.</p>
    </section>
  </div>
</template>

<style scoped>
.agent {
  max-width: 720px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.status {
  padding: 0.5rem 0.75rem;
  background: #eef6ff;
  border-radius: 6px;
  font-size: 0.875rem;
}

.card {
  margin-top: 1.25rem;
  padding: 1.25rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.card h2 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
}

label {
  display: block;
  margin: 0.5rem 0 0.25rem;
  font-size: 0.8125rem;
  font-weight: 500;
}

input {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  box-sizing: border-box;
}

button {
  margin-top: 0.75rem;
  padding: 0.5rem 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: #f8fafc;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: default;
}

.muted {
  color: #6b7280;
  font-size: 0.875rem;
}

.ok {
  color: #16a34a;
}

.tg-btn {
  display: inline-block;
  margin-top: 0.5rem;
  padding: 0.5rem 1rem;
  background: #229ed9;
  color: #fff;
  border-radius: 6px;
  text-decoration: none;
}

.summary {
  margin: 0.75rem 0 0.5rem;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.chip {
  padding: 0.15rem 0.6rem;
  background: #eef2ff;
  border-radius: 999px;
  font-size: 0.8125rem;
}

.chip.topic {
  background: #f1f5f9;
}

.chat {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  max-height: 260px;
  overflow-y: auto;
}

.msg {
  padding: 0.4rem 0.7rem;
  border-radius: 10px;
  max-width: 85%;
  font-size: 0.9rem;
}

.msg.user {
  align-self: flex-end;
  background: #dbeafe;
}

.msg.assistant {
  align-self: flex-start;
  background: #f3f4f6;
}

.chat-input {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.chat-input input {
  flex: 1;
}

.chat-input button {
  margin-top: 0;
}

.matches {
  list-style: none;
  padding: 0;
  margin: 0.75rem 0 0;
}

.matches li {
  padding: 0.6rem 0;
  border-top: 1px solid var(--color-border);
}

.matches a {
  font-weight: 500;
  text-decoration: none;
  color: inherit;
}

.meta {
  font-size: 0.8125rem;
  color: #6b7280;
  margin-top: 0.2rem;
}

.reason {
  font-size: 0.8125rem;
  margin-top: 0.2rem;
}
</style>
