import api from './client'

export interface GithubProfile {
  github_username: string | null
  has_github_token: boolean
  telegram_linked: boolean
  poll_enabled: boolean
  last_polled_at: string | null
}

export interface InterestProfile {
  summary: string
  languages: string[]
  topics: string[]
  keywords: string[]
  updated_at: string | null
}

export interface TelegramLink {
  linked: boolean
  url: string | null
  bot_configured: boolean
}

export interface SentIssue {
  id: string
  repo_full_name: string
  issue_url: string
  title: string
  languages: string | null
  stars: number
  relevance: number
  reason: string | null
  sent_at: string
}

export interface ChatMessage {
  role: string
  content: string
  created_at: string
}

export interface ChatResponse {
  reply: string
  interests: InterestProfile
}

export interface RebuildResponse {
  interests: InterestProfile
  repos_scanned: number
}

export interface PollNowResponse {
  matches_sent: number
  candidates_scanned: number
  message: string
}

export async function getProfile(): Promise<GithubProfile> {
  const { data } = await api.get<GithubProfile>('/agent/profile')
  return data
}

export async function updateProfile(payload: {
  github_username?: string | null
  github_token?: string | null
  poll_enabled?: boolean | null
}): Promise<GithubProfile> {
  const { data } = await api.put<GithubProfile>('/agent/profile', payload)
  return data
}

export async function getInterests(): Promise<InterestProfile> {
  const { data } = await api.get<InterestProfile>('/agent/interests')
  return data
}

export async function rebuildInterests(): Promise<RebuildResponse> {
  const { data } = await api.post<RebuildResponse>('/agent/interests/rebuild')
  return data
}

export async function getTelegramLink(): Promise<TelegramLink> {
  const { data } = await api.get<TelegramLink>('/agent/telegram-link')
  return data
}

export async function sendChat(message: string): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>('/agent/chat', { message })
  return data
}

export async function getChatHistory(): Promise<ChatMessage[]> {
  const { data } = await api.get<ChatMessage[]>('/agent/chat/history')
  return data
}

export async function getMatches(): Promise<SentIssue[]> {
  const { data } = await api.get<SentIssue[]>('/agent/matches')
  return data
}

export async function pollNow(): Promise<PollNowResponse> {
  const { data } = await api.post<PollNowResponse>('/agent/poll-now')
  return data
}
