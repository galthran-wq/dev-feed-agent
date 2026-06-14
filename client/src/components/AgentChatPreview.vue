<script setup lang="ts">
// A scripted preview of what the agent actually sends to Telegram: a feed digest,
// a user "steer" reply, a typing indicator, then the agent's confirmation.
// Reveals sequentially when scrolled into view; falls back to fully-shown when
// IntersectionObserver is missing or the user prefers reduced motion (CSS-gated).
import { onBeforeUnmount, onMounted, ref } from 'vue'

const root = ref<HTMLElement | null>(null)
const visible = ref(false)
let obs: IntersectionObserver | null = null

onMounted(() => {
  const el = root.value
  if (!el || !('IntersectionObserver' in window)) {
    visible.value = true
    return
  }
  obs = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          visible.value = true
          obs?.disconnect()
          break
        }
      }
    },
    { threshold: 0.3 },
  )
  obs.observe(el)
})
onBeforeUnmount(() => obs?.disconnect())
</script>

<template>
  <div ref="root" class="chat" :class="{ visible }">
    <div class="window">
      <header class="bar">
        <span class="avatar" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none">
            <rect x="5" y="8" width="14" height="11" rx="4" fill="#fff" />
            <circle cx="9.5" cy="13.5" r="1.4" fill="#2563eb" />
            <circle cx="14.5" cy="13.5" r="1.4" fill="#2563eb" />
            <path d="M12 8V5" stroke="#fff" stroke-width="1.6" stroke-linecap="round" />
            <circle cx="12" cy="4" r="1.6" fill="#7c3aed" />
          </svg>
        </span>
        <span class="who">
          <strong>devfeed.fyi</strong>
          <em>bot · delivers your feed</em>
        </span>
        <span class="dot" aria-hidden="true"></span>
      </header>

      <div class="thread">
        <!-- Agent: the feed digest -->
        <div class="msg agent rise" style="--d: 0.1s">
          <div class="bubble">
            <p class="head">🗞 Today’s picks — 4 fresh for you</p>
            <ul class="items">
              <li>
                🦀 <a href="https://github.com/tokio-rs/axum" target="_blank" rel="noopener">tokio-rs/axum</a>
                <span class="why">v0.8 — the ergonomic extractors you kept hitting</span>
              </li>
              <li>
                🌱 <a href="https://github.com/ratatui/ratatui" target="_blank" rel="noopener">good first issue · ratatui</a>
                <span class="why">“table row selection” · Rust, beginner-friendly</span>
              </li>
              <li>
                📄 <a href="https://arxiv.org/list/cs.IR/recent" target="_blank" rel="noopener">arXiv</a>
                <span class="why">KV-cache compression for long-context LLMs · your retrieval focus</span>
              </li>
              <li>
                💬 <a href="https://news.ycombinator.com" target="_blank" rel="noopener">HN</a>
                <span class="why">“Show HN: a local-first sync engine” · 412 pts</span>
              </li>
            </ul>
            <span class="time">09:00</span>
          </div>
        </div>

        <!-- User: steer it -->
        <div class="msg user rise" style="--d: 0.75s">
          <div class="bubble">more rust, less frontend<span class="time">09:02</span></div>
        </div>

        <!-- Agent typing… (motion-only) -->
        <div class="msg agent typing">
          <div class="bubble dots"><i></i><i></i><i></i></div>
        </div>

        <!-- Agent: confirms -->
        <div class="msg agent rise" style="--d: 2.5s">
          <div class="bubble">
            Got it 👍 leaning into Rust &amp; systems, easing off JS/frontend. Profile updated.
            <span class="time">09:02</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  justify-content: center;
}
.window {
  width: 100%;
  max-width: 30rem;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 20px;
  overflow: hidden;
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.04),
    0 24px 48px -24px rgba(37, 41, 64, 0.28);
}

/* Header — Telegram-ish, with the brand gradient */
.bar {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.7rem 0.9rem;
  background: linear-gradient(120deg, #2563eb, #7c3aed);
  color: #fff;
}
.avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
}
.who {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}
.who strong {
  font-size: 0.92rem;
  letter-spacing: -0.01em;
}
.who em {
  font-style: normal;
  font-size: 0.72rem;
  opacity: 0.8;
}
.dot {
  margin-left: auto;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #4ade80;
  box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.28);
}

/* Thread */
.thread {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  padding: 1.1rem 0.9rem 1.25rem;
  background:
    radial-gradient(120% 80% at 100% 0%, rgba(124, 58, 237, 0.06), transparent 60%),
    radial-gradient(120% 80% at 0% 100%, rgba(37, 99, 235, 0.06), transparent 55%),
    #f7f8fb;
  text-align: left;
}
.msg {
  display: flex;
  max-width: 88%;
}
.msg.agent {
  align-self: flex-start;
}
.msg.user {
  align-self: flex-end;
}
.bubble {
  position: relative;
  padding: 0.6rem 0.8rem 1.15rem;
  border-radius: 16px;
  font-size: 0.9rem;
  line-height: 1.45;
}
.msg.agent .bubble {
  background: #fff;
  border: 1px solid var(--color-border);
  border-bottom-left-radius: 5px;
  color: #1f2430;
}
.msg.user .bubble {
  background: linear-gradient(120deg, #2563eb, #7c3aed);
  color: #fff;
  border-bottom-right-radius: 5px;
}
.head {
  margin: 0 0 0.45rem;
  font-weight: 600;
}
.items {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.items li {
  display: block;
}
.items a {
  color: var(--color-primary);
  font-weight: 600;
  text-decoration: none;
}
.items a:hover {
  text-decoration: underline;
}
.why {
  display: block;
  color: var(--color-text-muted);
  font-size: 0.82rem;
}
.time {
  position: absolute;
  right: 0.7rem;
  bottom: 0.4rem;
  font-size: 0.66rem;
  opacity: 0.55;
}
.msg.user .time {
  color: rgba(255, 255, 255, 0.85);
  opacity: 0.9;
}

/* Typing indicator: hidden unless motion is welcome */
.msg.typing {
  display: none;
}
.dots {
  display: inline-flex;
  gap: 4px;
  padding: 0.7rem 0.8rem;
}
.dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9aa3b2;
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(12px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@keyframes bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.5;
  }
  40% {
    transform: translateY(-4px);
    opacity: 1;
  }
}
/* pop in, hold, then collapse away just before the reply lands */
@keyframes typing-cycle {
  0% {
    opacity: 0;
    transform: translateY(12px);
    max-height: 0;
    margin-top: -0.55rem;
  }
  10% {
    opacity: 1;
    transform: none;
    max-height: 44px;
    margin-top: 0;
  }
  78% {
    opacity: 1;
    max-height: 44px;
    margin-top: 0;
  }
  100% {
    opacity: 0;
    transform: translateY(-4px);
    max-height: 0;
    margin-top: -0.55rem;
  }
}

@media (prefers-reduced-motion: no-preference) {
  /* hide-then-reveal only when motion is allowed and not yet in view */
  .chat:not(.visible) .rise {
    opacity: 0;
  }
  .chat.visible .rise {
    animation: rise 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
    animation-delay: var(--d, 0s);
  }
  .chat.visible .msg.typing {
    display: flex;
    animation: typing-cycle 1.7s ease both;
    animation-delay: 1.4s;
  }
  .chat.visible .msg.typing .dots i {
    animation: bounce 1.2s infinite ease-in-out;
    animation-delay: calc(var(--n, 0) * 0.16s);
  }
  .dots i:nth-child(2) {
    --n: 1;
  }
  .dots i:nth-child(3) {
    --n: 2;
  }
}
</style>
