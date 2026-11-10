/**
 * The outside services that receive a question or a document's text. The app
 * asks for consent with this list (App Store guideline 5.1.2(i) wants the AI
 * providers named before personal data goes to them) and the privacy policy
 * prints it, so the two can't drift apart. Keep it in step with the services
 * the backend actually calls (backend/app/config.py keys).
 *
 * Raise AI_CONSENT_VERSION when a provider is added or data goes somewhere
 * new: everyone in the app is asked again.
 */
export interface AiProvider {
  name: string
  what: string
  where: string
}

export const AI_PROVIDERS: AiProvider[] = [
  { name: 'Anthropic', what: 'Writes answers and drafts (Claude models)', where: 'United States' },
  { name: 'OpenAI', what: 'Turns questions and uploaded documents into search vectors', where: 'United States' },
  { name: 'Google (Gemini API)', what: 'Backup search vectors when OpenAI is unavailable', where: 'United States' },
  { name: 'Moonshot AI and OpenRouter', what: 'Backup answer models when Anthropic is unavailable', where: 'China and the United States' },
  { name: 'Tavily', what: 'Web searches when Levy looks beyond its library', where: 'United States' },
]

export const AI_CONSENT_VERSION = 1

export interface AiConsentRecord {
  version: number
  at: string
}

/** The consent saved on the account, if it covers the current list. */
export function currentAiConsent(metadata: Record<string, unknown> | undefined): AiConsentRecord | null {
  const raw = metadata?.ai_consent as Partial<AiConsentRecord> | undefined
  if (!raw || typeof raw.version !== 'number' || typeof raw.at !== 'string') return null
  return raw.version >= AI_CONSENT_VERSION ? { version: raw.version, at: raw.at } : null
}
