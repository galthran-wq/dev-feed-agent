<script setup lang="ts">
// The single public entry point: explain the product, then "Connect with GitHub".
// The button hits the backend, which redirects to GitHub's OAuth consent screen.
import logoUrl from '@/assets/logo.png'

function connect() {
  window.location.href = '/api/auth/github/login'
}
</script>

<template>
  <div class="landing">
    <section class="hero">
      <img class="logo" :src="logoUrl" alt="" width="1077" height="724" />
      <h1>dev-feed-agent</h1>
      <p class="tagline">A personalized, agentic feed for developers &amp; ML engineers.</p>

      <p class="blurb">
        Connect your GitHub and the agent reads what you build to learn your interests. Then it
        watches GitHub, HuggingFace, Hacker News, arXiv and Reddit and sends you a hand-picked feed
        — projects, good-first-issues, help-wanted tickets, papers and discussions — straight to
        Telegram. Chat with it anytime to steer what you see.
      </p>

      <button class="connect" @click="connect">
        <svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true">
          <path
            fill="currentColor"
            d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
          />
        </svg>
        Connect with GitHub
      </button>
    </section>
  </div>
</template>

<style scoped>
.landing {
  display: flex;
  justify-content: center;
  padding: 3.5rem 1.5rem 5.5rem;
}
.hero {
  max-width: 34rem;
  text-align: center;
}
.logo {
  display: block;
  width: 100%;
  max-width: 320px;
  height: auto;
  margin: 0 auto 1.25rem;
}
h1 {
  font-size: 2.75rem;
  font-weight: 600;
  letter-spacing: -0.035em;
  line-height: 1.05;
  margin: 0 0 0.6rem;
}
.tagline {
  font-size: 1.15rem;
  letter-spacing: -0.01em;
  color: var(--color-text-muted);
  margin: 0 0 1.75rem;
}
.blurb {
  font-size: 1.0625rem;
  line-height: 1.65;
  color: #374151;
  margin: 0 auto 2.25rem;
  max-width: 30rem;
  text-align: left;
}
.connect {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.8rem 1.35rem;
  font-size: 0.975rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #fff;
  background: #1f2328;
  border: none;
  border-radius: 9px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.connect:hover {
  background: #000;
}
</style>
