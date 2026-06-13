import api from './client'

export interface AgentStatus {
  github_connected: boolean
  github_username: string | null
  avatar_url: string | null
  telegram_linked: boolean
  profile_built: boolean
  agent_enabled: boolean
}

export interface TelegramLink {
  linked: boolean
  url: string | null
  bot_configured: boolean
}

export async function getStatus(): Promise<AgentStatus> {
  const { data } = await api.get<AgentStatus>('/agent/status')
  return data
}

export async function getTelegramLink(): Promise<TelegramLink> {
  const { data } = await api.get<TelegramLink>('/agent/telegram-link')
  return data
}
