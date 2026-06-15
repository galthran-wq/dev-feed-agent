<script setup lang="ts">
// A carousel of Telegram-style chat cards, each previewing a different thing the agent
// does. Cards reveal their bubbles in sequence as they scroll into the track; a typing
// indicator precedes agent replies. Reduced-motion / no-IO falls back to fully shown.
import { onBeforeUnmount, onMounted, ref } from 'vue'

type Item = { icon: string; title: string; href: string; why: string }
type Msg = {
  role: 'agent' | 'user'
  text?: string
  head?: string
  items?: Item[]
  typing?: boolean
  time?: string
}
type Scenario = { label: string; sub: string; messages: Msg[] }

const scenarios: Scenario[] = [
  {
    label: 'Your morning feed',
    sub: 'delivered hourly',
    messages: [
      {
        role: 'agent',
        time: '09:00',
        head: '🗞 Today’s picks — 4 fresh for you',
        items: [
          {
            icon: '🦀',
            title: 'tokio-rs/axum',
            href: 'https://github.com/tokio-rs/axum',
            why: 'v0.8 — the ergonomic extractors you kept hitting',
          },
          {
            icon: '🌱',
            title: 'good first issue · ratatui',
            href: 'https://github.com/ratatui/ratatui',
            why: '“table row selection” · Rust, beginner-friendly',
          },
          {
            icon: '📄',
            title: 'arXiv',
            href: 'https://arxiv.org/list/cs.IR/recent',
            why: 'KV-cache compression for long-context LLMs · your retrieval focus',
          },
          {
            icon: '💬',
            title: 'HN',
            href: 'https://news.ycombinator.com',
            why: '“Show HN: a local-first sync engine” · 412 pts',
          },
        ],
      },
    ],
  },
  {
    label: 'Steer it in chat',
    sub: 'just tell it',
    messages: [
      { role: 'user', time: '09:02', text: 'more rust, less frontend' },
      {
        role: 'agent',
        time: '09:02',
        typing: true,
        text: 'Got it 👍 leaning into Rust & systems, easing off JS/frontend. Profile updated.',
      },
    ],
  },
  {
    label: 'Built from your GitHub',
    sub: 'on /init',
    messages: [
      { role: 'user', text: '/init' },
      {
        role: 'agent',
        typing: true,
        text: 'Scanned 23 repos + their dependencies. You’re into Rust async, LLM retrieval and terminal UIs — I’ll tune your feed to that. Profile ready ✅',
      },
    ],
  },
  {
    label: 'Go deeper, anytime',
    sub: 'on demand',
    messages: [
      { role: 'user', text: 'summarise that KV-cache paper' },
      {
        role: 'agent',
        typing: true,
        text: 'It prunes low-attention tokens to shrink the KV cache ~4× with <1% quality drop on long-context evals — slots right into your retrieval stack. Link + 3-bullet TL;DR below 👇',
      },
    ],
  },
]

const track = ref<HTMLElement | null>(null)
let obs: IntersectionObserver | null = null

onMounted(() => {
  const t = track.value
  if (!t) return
  const cards = Array.from(t.querySelectorAll<HTMLElement>('.card'))
  if (!('IntersectionObserver' in window)) {
    cards.forEach((c) => c.classList.add('visible'))
    return
  }
  obs = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) e.target.classList.add('visible')
      }
    },
    { root: t, threshold: 0.55 },
  )
  cards.forEach((c) => obs!.observe(c))
})
onBeforeUnmount(() => obs?.disconnect())

function nudge(dir: number) {
  const t = track.value
  if (!t) return
  const card = t.querySelector<HTMLElement>('.card')
  const step = (card?.offsetWidth ?? 320) + 18
  t.scrollBy({ left: dir * step, behavior: 'smooth' })
}
</script>

<template>
  <div class="carousel">
    <button class="arrow left" type="button" aria-label="Previous" @click="nudge(-1)">‹</button>
    <div ref="track" class="track">
      <article v-for="s in scenarios" :key="s.label" class="card">
        <div class="window">
          <header class="bar">
            <span class="avatar" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none">
                <rect x="5" y="8" width="14" height="11" rx="4" fill="#fff" />
                <circle cx="9.5" cy="13.5" r="1.4" fill="#2563eb" />
                <circle cx="14.5" cy="13.5" r="1.4" fill="#2563eb" />
                <path d="M12 8V5" stroke="#fff" stroke-width="1.6" stroke-linecap="round" />
                <circle cx="12" cy="4" r="1.6" fill="#7c3aed" />
              </svg>
            </span>
            <span class="who"
              ><strong>devfeed.fyi</strong><em>{{ s.sub }}</em></span
            >
            <span class="dot" aria-hidden="true"></span>
          </header>

          <div class="thread">
            <template v-for="(m, i) in s.messages" :key="i">
              <div v-if="m.typing" class="msg agent typing" :style="{ '--i': i }">
                <div class="bubble dots"><i></i><i></i><i></i></div>
              </div>
              <div class="msg" :class="m.role" :style="{ '--i': i }">
                <div class="bubble">
                  <template v-if="m.head">
                    <p class="head">{{ m.head }}</p>
                    <ul class="items">
                      <li v-for="it in m.items" :key="it.title">
                        {{ it.icon }}
                        <a :href="it.href" target="_blank" rel="noopener">{{ it.title }}</a>
                        <span class="why">{{ it.why }}</span>
                      </li>
                    </ul>
                  </template>
                  <template v-else>{{ m.text }}</template>
                  <span v-if="m.time" class="time">{{ m.time }}</span>
                </div>
              </div>
            </template>
          </div>
        </div>
        <p class="label">{{ s.label }}</p>
      </article>
    </div>
    <button class="arrow right" type="button" aria-label="Next" @click="nudge(1)">›</button>
  </div>
</template>

<style scoped>
.carousel {
  position: relative;
  width: 100%;
  max-width: 64rem;
}
.track {
  display: flex;
  gap: 1.1rem;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding: 0.5rem 1.25rem 1rem;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  /* fade the edges so off-screen cards peek out softly */
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
  mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
}
.track::-webkit-scrollbar {
  display: none;
}
.card {
  flex: 0 0 auto;
  width: min(22rem, 80vw);
  scroll-snap-align: center;
  /* stretch every card to the tallest (the digest) so all panels match */
  display: flex;
  flex-direction: column;
}

/* Arrows — hidden on touch-ish small screens, shown on wide */
.arrow {
  position: absolute;
  top: calc(50% - 1rem);
  transform: translateY(-50%);
  z-index: 2;
  width: 2.2rem;
  height: 2.2rem;
  display: grid;
  place-items: center;
  font-size: 1.3rem;
  line-height: 1;
  color: var(--color-text-muted);
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  box-shadow: 0 6px 18px -8px rgba(16, 24, 40, 0.35);
  cursor: pointer;
  transition:
    color 0.15s ease,
    transform 0.15s ease;
}
.arrow:hover {
  color: var(--color-text);
}
.arrow:active {
  transform: translateY(-50%) scale(0.92);
}
.arrow.left {
  left: -0.6rem;
}
.arrow.right {
  right: -0.6rem;
}

/* Chat window */
.window {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  overflow: hidden;
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.04),
    0 22px 44px -26px rgba(37, 41, 64, 0.3);
}
.bar {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.6rem 0.8rem;
  background: linear-gradient(120deg, #2563eb, #7c3aed);
  color: #fff;
}
.avatar {
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
}
.who {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}
.who strong {
  font-size: 0.86rem;
  letter-spacing: -0.01em;
}
.who em {
  font-style: normal;
  font-size: 0.68rem;
  opacity: 0.82;
}
.dot {
  margin-left: auto;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4ade80;
  box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.28);
}
.thread {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.95rem 0.8rem 1.05rem;
  min-height: 12.5rem;
  background:
    radial-gradient(120% 80% at 100% 0%, rgba(124, 58, 237, 0.06), transparent 60%),
    radial-gradient(120% 80% at 0% 100%, rgba(37, 99, 235, 0.06), transparent 55%), #f7f8fb;
  text-align: left;
}
.msg {
  display: flex;
  max-width: 90%;
}
.msg.agent {
  align-self: flex-start;
}
.msg.user {
  align-self: flex-end;
}
.bubble {
  position: relative;
  padding: 0.55rem 0.75rem 1.05rem;
  border-radius: 15px;
  font-size: 0.86rem;
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
  margin: 0 0 0.4rem;
  font-weight: 600;
}
.items {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
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
  font-size: 0.78rem;
}
.time {
  position: absolute;
  right: 0.65rem;
  bottom: 0.38rem;
  font-size: 0.64rem;
  opacity: 0.55;
}
.msg.user .time {
  color: rgba(255, 255, 255, 0.85);
}
.label {
  margin: 0.85rem 0 0;
  text-align: center;
  font-size: 0.92rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--color-text);
}

.typing {
  display: none;
}
.dots {
  display: inline-flex;
  gap: 4px;
  padding: 0.65rem 0.75rem;
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
@keyframes typing-cycle {
  0% {
    opacity: 0;
    transform: translateY(12px);
    max-height: 0;
    margin-bottom: -0.5rem;
  }
  12% {
    opacity: 1;
    transform: none;
    max-height: 42px;
    margin-bottom: 0;
  }
  78% {
    opacity: 1;
    max-height: 42px;
  }
  100% {
    opacity: 0;
    transform: translateY(-4px);
    max-height: 0;
    margin-bottom: -0.5rem;
  }
}

@media (max-width: 560px) {
  .arrow {
    display: none;
  }
}

@media (prefers-reduced-motion: no-preference) {
  .card:not(.visible) .msg {
    opacity: 0;
  }
  .card.visible .msg {
    animation: rise 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
    animation-delay: calc(var(--i) * 0.7s + 0.5s);
  }
  .card.visible .msg.typing {
    display: flex;
    animation: typing-cycle 1.5s ease both;
    animation-delay: calc(var(--i) * 0.7s + 0.5s - 1.2s);
  }
  .card.visible .msg.typing .dots i {
    animation: bounce 1.2s infinite ease-in-out;
  }
  .dots i:nth-child(2) {
    animation-delay: 0.16s;
  }
  .dots i:nth-child(3) {
    animation-delay: 0.32s;
  }
}
</style>
