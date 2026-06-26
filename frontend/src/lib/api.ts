const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/**
 * Attach the logged-in user's Supabase access token so the backend can
 * verify identity. The backend authorizes every owner-scoped endpoint from
 * this token (it no longer trusts a client-supplied user_id), so any call
 * that touches user data must carry it. Reads the live session straight
 * from the Supabase browser client, so callers don't have to thread a token
 * through every function.
 */
async function authHeaders(): Promise<Record<string, string>> {
  try {
    const { createClient } = await import('@/lib/supabase')
    const supabase = createClient()
    const { data } = await supabase.auth.getSession()
    const token = data.session?.access_token
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

interface ChatResponse {
  answer: string
  chunks_used: ChunkUsed[]
  chunks_retrieved: number
  model: string
  usage: { input_tokens: number; output_tokens: number }
  timing: { embedding_ms: number; retrieval_ms: number; generation_ms: number; total_ms: number }
}

interface ChunkUsed {
  id: string
  document_id?: string
  act_name: string
  section: string
  part: string
  page_start: number
  page_end: number
  similarity: number
  content_preview: string
}

interface SearchResult {
  id: string
  content: string
  act_name: string
  section: string
  part: string
  page_start: number
  page_end: number
  similarity: number
}

interface SearchResponse {
  results: SearchResult[]
  total: number
  timing: { embedding_ms: number; retrieval_ms: number; total_ms: number }
}

interface DocumentInfo {
  title: string
  year: number
  total_chunks: number
  total_sections: number
}

interface DocumentsResponse {
  documents: number
  details: DocumentInfo[]
}

export interface LibraryDocument {
  id: string
  title: string
  short_name?: string
  year?: number | null
  document_type?: string
  total_chunks?: number
  pdf_page_count?: number
  pdf_size_bytes?: number
  pdf_storage_path?: string | null
  canonical_url?: string | null
  is_global: boolean
  owner_id?: string | null
  folder_id?: string | null
  created_at?: string
  attached_at?: string
}

export interface DocumentsByVisibility {
  global: LibraryDocument[]
  owned: LibraryDocument[]
  attached: LibraryDocument[]
  counts: { global: number; owned: number; attached: number }
}

export async function listDocumentsForUser(
  userId?: string,
  sessionId?: string,
  folderId?: string | null,
): Promise<DocumentsByVisibility> {
  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  if (sessionId) params.set('session_id', sessionId)
  if (folderId) params.set('folder_id', folderId)
  const r = await fetch(`${API_URL}/api/documents?${params.toString()}`, { headers: await authHeaders() })
  if (!r.ok) throw new Error(`documents ${r.status}`)
  return r.json()
}

export async function attachDocumentToSession(sessionId: string, documentId: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/sessions/${sessionId}/documents/attach`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ document_id: documentId }),
  })
  if (!r.ok) throw new Error(`attach ${r.status}`)
}

export async function detachDocumentFromSession(sessionId: string, documentId: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/sessions/${sessionId}/documents/${documentId}`, {
    method: 'DELETE',
    headers: await authHeaders(),
  })
  if (!r.ok) throw new Error(`detach ${r.status}`)
}

export async function listSessionDocuments(sessionId: string): Promise<{ documents: LibraryDocument[] }> {
  const r = await fetch(`${API_URL}/api/sessions/${sessionId}/documents`, { headers: await authHeaders() })
  if (!r.ok) throw new Error(`session-docs ${r.status}`)
  return r.json()
}

// ─── Folders ────────────────────────────────────────────────────────────────

export interface FolderRow {
  id: string
  name: string
  created_at?: string
  doc_count: number
}

export async function listFolders(userId: string): Promise<{ folders: FolderRow[]; unfiled_count: number }> {
  const r = await fetch(`${API_URL}/api/folders?user_id=${encodeURIComponent(userId)}`, { headers: await authHeaders() })
  if (!r.ok) throw new Error(`folders ${r.status}`)
  return r.json()
}

export async function createFolder(userId: string, name: string): Promise<FolderRow> {
  const r = await fetch(`${API_URL}/api/folders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ user_id: userId, name }),
  })
  if (!r.ok) throw new Error((await r.text()) || `create folder ${r.status}`)
  return r.json()
}

export async function renameFolder(folderId: string, name: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/folders/${folderId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ name }),
  })
  if (!r.ok) throw new Error(`rename ${r.status}`)
}

export async function deleteFolder(folderId: string, cascade = false): Promise<void> {
  const r = await fetch(`${API_URL}/api/folders/${folderId}?cascade=${cascade}`, { method: 'DELETE', headers: await authHeaders() })
  if (!r.ok) throw new Error(`delete ${r.status}`)
}

export async function moveDocumentToFolder(documentId: string, folderId: string | null): Promise<void> {
  const r = await fetch(`${API_URL}/api/documents/${documentId}/folder`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ folder_id: folderId }),
  })
  if (!r.ok) throw new Error(`move ${r.status}`)
}

// ─── Templates ──────────────────────────────────────────────────────────────

export interface TemplateRow {
  id: string
  name: string
  description?: string | null
  file_type: 'docx' | 'pdf' | 'txt' | 'md'
  file_size_bytes?: number | null
  page_count?: number | null
  preview_text?: string | null
  folder_id?: string | null
  created_at?: string
  updated_at?: string
}

export interface TemplateFolderRow {
  id: string
  name: string
  created_at?: string
  doc_count: number
}

export interface TemplateSuggestion {
  id: string
  name: string
  description?: string
  file_type: 'docx' | 'pdf' | 'txt' | 'md'
  page_count?: number | null
  preview?: string
}

export async function listTemplates(
  userId: string,
  folderId?: string | null,
): Promise<{ templates: TemplateRow[]; count: number }> {
  const params = new URLSearchParams()
  params.set('user_id', userId)
  if (folderId) params.set('folder_id', folderId)
  const r = await fetch(`${API_URL}/api/templates?${params.toString()}`, { headers: await authHeaders() })
  if (!r.ok) throw new Error(`templates ${r.status}`)
  return r.json()
}

export async function uploadTemplate(
  file: File,
  options: { userId: string; name?: string; description?: string; folderId?: string | null },
): Promise<{ template: TemplateRow }> {
  const params = new URLSearchParams()
  params.set('user_id', options.userId)
  if (options.name) params.set('name', options.name)
  if (options.description) params.set('description', options.description)
  if (options.folderId) params.set('folder_id', options.folderId)
  const formData = new FormData()
  formData.append('file', file)
  const r = await fetch(`${API_URL}/api/templates/upload?${params.toString()}`, {
    method: 'POST',
    headers: await authHeaders(),
    body: formData,
  })
  if (!r.ok) throw new Error((await r.text()) || `upload-template ${r.status}`)
  return r.json()
}

// Template folders
export async function listTemplateFolders(
  userId: string,
): Promise<{ folders: TemplateFolderRow[]; unfiled_count: number }> {
  const r = await fetch(`${API_URL}/api/template-folders?user_id=${encodeURIComponent(userId)}`, { headers: await authHeaders() })
  if (!r.ok) throw new Error(`template-folders ${r.status}`)
  return r.json()
}

export async function createTemplateFolder(userId: string, name: string): Promise<TemplateFolderRow> {
  const r = await fetch(`${API_URL}/api/template-folders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ user_id: userId, name }),
  })
  if (!r.ok) throw new Error((await r.text()) || `create template folder ${r.status}`)
  return r.json()
}

export async function renameTemplateFolder(folderId: string, name: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/template-folders/${folderId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ name }),
  })
  if (!r.ok) throw new Error(`rename ${r.status}`)
}

export async function deleteTemplateFolder(folderId: string, cascade = false): Promise<void> {
  const r = await fetch(`${API_URL}/api/template-folders/${folderId}?cascade=${cascade}`, {
    method: 'DELETE',
    headers: await authHeaders(),
  })
  if (!r.ok) throw new Error(`delete ${r.status}`)
}

export async function moveTemplateToFolder(templateId: string, folderId: string | null): Promise<void> {
  const r = await fetch(`${API_URL}/api/templates/${templateId}/folder`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify({ folder_id: folderId }),
  })
  if (!r.ok) throw new Error(`move ${r.status}`)
}

export async function updateTemplate(id: string, patch: { name?: string; description?: string }): Promise<void> {
  const r = await fetch(`${API_URL}/api/templates/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...(await authHeaders()) },
    body: JSON.stringify(patch),
  })
  if (!r.ok) throw new Error(`update-template ${r.status}`)
}

export async function deleteTemplate(id: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/templates/${id}`, { method: 'DELETE', headers: await authHeaders() })
  if (!r.ok) throw new Error(`delete-template ${r.status}`)
}

export async function getTemplateSignedUrl(id: string): Promise<{ signed_url: string; name: string; file_type: string }> {
  const r = await fetch(`${API_URL}/api/templates/${id}/file`, { headers: await authHeaders() })
  if (!r.ok) throw new Error(`template-url ${r.status}`)
  return r.json()
}

export async function sendQuery(
  question: string,
  options?: { model?: string; top_k?: number; threshold?: number; token?: string }
): Promise<ChatResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (options?.token) headers['Authorization'] = `Bearer ${options.token}`

  const res = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query: question,
      model: options?.model,
      top_k: options?.top_k,
      threshold: options?.threshold,
    }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function searchCorpus(
  query: string,
  options?: { top_k?: number; threshold?: number; token?: string }
): Promise<SearchResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (options?.token) headers['Authorization'] = `Bearer ${options.token}`

  const res = await fetch(`${API_URL}/api/search`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query,
      top_k: options?.top_k,
      threshold: options?.threshold,
    }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getDocuments(token?: string): Promise<DocumentsResponse> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_URL}/api/documents`, { headers })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function uploadDocument(
  file: File,
  token?: string,
  userId?: string,
  folderId?: string | null,
): Promise<{
  status: string
  document_id: string
  chunks_created?: number
  tier?: 'inline' | 'rag'
  page_count?: number
  suggest_promotion?: boolean
}> {
  const headers: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : await authHeaders()

  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams()
  if (userId) params.set('user_id', userId)
  if (folderId) params.set('folder_id', folderId)
  const qs = params.toString()
  const url = qs ? `${API_URL}/api/documents/upload?${qs}` : `${API_URL}/api/documents/upload`
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (!res.ok) throw new Error(`Upload error: ${res.status}`)
  return res.json()
}

export interface WebSource {
  title?: string
  url: string
  snippet?: string
  domain?: string
  score?: number
}

export interface ToolCallEvent {
  id: string
  name: string
  input: Record<string, unknown>
}

export interface ArtifactView {
  id: string
  title: string
  kind: 'pdf' | 'docx' | 'md' | 'txt'
  source: 'generated' | 'extracted' | 'merged' | 'uploaded' | 'fetched'
  page_count?: number
  size_bytes?: number
  meta?: Record<string, unknown>
  created_at?: string
  storage_path?: string
}

export interface ToolResultEvent {
  id: string
  name: string
  ok: boolean
  db: ChunkUsed[]
  web: WebSource[]
  artifact?: ArtifactView | null
  ms: number
}

export interface AgentDoneMetadata {
  chunks_used: ChunkUsed[]
  web_sources: WebSource[]
  timing: Record<string, number>
  iterations?: number
  usage?: { input_tokens: number; output_tokens: number }
  model?: string
}

export interface CompactionEvent {
  tokens_before: number
  tokens_after: number
  summarised_messages: number
  kept_messages: number
  summary_chars?: number
  model?: string
  error?: string
}

export interface TemplateSuggestionEvent {
  tool_call_id: string
  templates: TemplateSuggestion[]
}

export interface ApplicationPlan {
  cause_of_action: string
  procedural_mode: string
  court_division: string
  urgency: 'ex_parte' | 'inter_partes'
  reliefs: string[]
  documents_to_file: string[]
  statutory_basis?: string[]
  authorities?: string[]
  notes?: string | null
}

export interface ApplicationPlanEvent {
  tool_call_id: string
  plan: ApplicationPlan
}

export interface EntitlementLineItem {
  item: string
  status: 'owed' | 'conditional' | 'contested' | 'not_applicable' | 'compliance' | 'needs_input'
  basis: string
  amount?: number | null
  formula?: string
  note?: string
}

export interface EntitlementBreakdown {
  currency: string
  monthly_basic_pay: number
  years_of_service: number
  termination_reason: string
  contract_type: string
  daily_rate: number
  line_items: EntitlementLineItem[]
  total_clearly_owed: number
  needs_input: string[]
  contested: string[]
  assumptions: string[]
  disclaimer: string
}

export interface EntitlementBreakdownEvent {
  tool_call_id: string
  breakdown: EntitlementBreakdown
}

export interface CaseLawMatch {
  document_id: string
  case: string
  citation?: string
  court?: string
  area?: string
  year?: number | null
  page_count?: number | null
  holding?: string
  similarity?: number
}

export interface CaseLawEvent {
  tool_call_id: string
  cases: CaseLawMatch[]
}

// ── Study Mode ────────────────────────────────────────────────────────────
export interface CheatSheet {
  title: string
  area: string
  topic: string
  key_statutes?: Array<{ name: string; note?: string }>
  sections: Array<{ heading: string; points: string[] }>
  key_cases?: Array<{ name: string; holding?: string }>
  exam_traps?: string[]
  mnemonic?: string
  artifact_id?: string
}

export interface CheatSheetEvent {
  tool_call_id: string
  cheat_sheet: CheatSheet
}

export interface QuizQuestion {
  stem: string
  options: string[]
  correct_index: number
  explanation?: string
  citation?: string
}

export interface Quiz {
  title: string
  area: string
  topic: string
  questions: QuizQuestion[]
}

export interface QuizEvent {
  tool_call_id: string
  quiz: Quiz
}

export interface StreamHandlers {
  onThinking?: () => void
  onToken?: (text: string) => void
  onToolCall?: (call: ToolCallEvent) => void
  onToolResult?: (result: ToolResultEvent) => void
  onArtifact?: (artifact: ArtifactView) => void
  onCompaction?: (event: CompactionEvent) => void
  onTemplateSuggestion?: (event: TemplateSuggestionEvent) => void
  onApplicationPlan?: (event: ApplicationPlanEvent) => void
  onEntitlementBreakdown?: (event: EntitlementBreakdownEvent) => void
  onCaseLaw?: (event: CaseLawEvent) => void
  onCheatSheet?: (event: CheatSheetEvent) => void
  onQuiz?: (event: QuizEvent) => void
  onDone?: (metadata: AgentDoneMetadata) => void
  onError?: (message: string) => void
}

export async function streamQuery(
  question: string,
  options?: {
    model?: string
    top_k?: number
    token?: string
    webSearch?: boolean
    history?: Array<{ role: string; content: string }>
    userId?: string
    sessionId?: string
    attachedDocIds?: string[]
  },
  legacyOnChunk?: (text: string) => void,
  legacyOnDone?: (metadata: AgentDoneMetadata) => void,
  handlers?: StreamHandlers,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (options?.token) headers['Authorization'] = `Bearer ${options.token}`

  const res = await fetch(`${API_URL}/api/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query: question,
      model: options?.model,
      top_k: options?.top_k,
      web_search: options?.webSearch ?? false,
      history: options?.history,
      user_id: options?.userId,
      session_id: options?.sessionId,
      attached_doc_ids: options?.attachedDocIds,
    }),
  })

  if (!res.ok) {
    // Friendly, recognizable messages so callers can show them verbatim.
    // 401/403 = anonymous chat is currently disabled (abuse guard); 429 = rate limited.
    if (res.status === 401 || res.status === 403)
      throw new Error('Please sign in to chat with Levy. Anonymous chat is temporarily disabled to prevent abuse.')
    if (res.status === 429)
      throw new Error('Levy is handling a lot of requests right now. Please wait a moment and try again.')
    throw new Error(`API error: ${res.status}`)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  // Sources accumulator - emitted as a single block when the run ends.
  let dbSources: ChunkUsed[] = []
  let webSources: WebSource[] = []
  let lastTiming: Record<string, number> | undefined
  let lastUsage: AgentDoneMetadata['usage']
  let lastIterations: number | undefined
  let lastModel: string | undefined

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') continue
      let parsed: Record<string, unknown>
      try {
        parsed = JSON.parse(data)
      } catch {
        continue
      }
      switch (parsed.type) {
        case 'thinking':
          handlers?.onThinking?.()
          break
        case 'token':
          legacyOnChunk?.(parsed.content as string)
          handlers?.onToken?.(parsed.content as string)
          break
        case 'tool_call':
          handlers?.onToolCall?.(parsed as unknown as ToolCallEvent)
          break
        case 'tool_result':
          handlers?.onToolResult?.(parsed as unknown as ToolResultEvent)
          if ((parsed as { artifact?: ArtifactView }).artifact) {
            handlers?.onArtifact?.((parsed as { artifact: ArtifactView }).artifact)
          }
          break
        case 'artifact':
          handlers?.onArtifact?.(parsed.artifact as ArtifactView)
          break
        case 'compaction':
          handlers?.onCompaction?.(parsed as unknown as CompactionEvent)
          break
        case 'template_suggestion':
          handlers?.onTemplateSuggestion?.(parsed as unknown as TemplateSuggestionEvent)
          break
        case 'entitlement_breakdown':
          handlers?.onEntitlementBreakdown?.(parsed as unknown as EntitlementBreakdownEvent)
          break
        case 'case_law':
          handlers?.onCaseLaw?.(parsed as unknown as CaseLawEvent)
          break
        case 'cheat_sheet':
          handlers?.onCheatSheet?.(parsed as unknown as CheatSheetEvent)
          break
        case 'quiz':
          handlers?.onQuiz?.(parsed as unknown as QuizEvent)
          break
        case 'application_plan':
          handlers?.onApplicationPlan?.(parsed as unknown as ApplicationPlanEvent)
          break
        case 'sources':
          dbSources = ((parsed.db as ChunkUsed[]) ?? (parsed.chunks_used as ChunkUsed[]) ?? [])
          webSources = (parsed.web as WebSource[]) ?? []
          break
        case 'done':
          lastTiming = parsed.timing as Record<string, number>
          lastUsage = parsed.usage as AgentDoneMetadata['usage']
          lastIterations = parsed.iterations as number | undefined
          lastModel = parsed.model as string | undefined
          break
        case 'error':
          handlers?.onError?.(String(parsed.message ?? 'unknown error'))
          break
      }
    }
  }

  const meta: AgentDoneMetadata = {
    chunks_used: dbSources,
    web_sources: webSources,
    timing: lastTiming ?? {},
    iterations: lastIterations,
    usage: lastUsage,
    model: lastModel,
  }
  legacyOnDone?.(meta)
  handlers?.onDone?.(meta)
}

// IRAC Brief Generation
export interface BriefCitation {
  act: string
  section: string
  page: number
}

export interface BriefResponse {
  issue: string
  rule: string
  application: string
  conclusion: string
  citations: BriefCitation[]
}

export async function generateBrief(
  messages: Array<{ role: string; content: string }>,
  token?: string
): Promise<BriefResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_URL}/api/brief/generate`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ messages }),
  })
  if (!res.ok) throw new Error(`Brief generation error: ${res.status}`)
  return res.json()
}

/**
 * Promote an inline-tier document to full RAG (chunk + embed in place, no new
 * document_id). Used by the "Save to library" affordance on attachment chips.
 */
export async function promoteDocument(
  documentId: string,
  token?: string,
): Promise<{ status: string; document_id: string; chunks_created: number }> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_URL}/api/documents/${documentId}/promote`, {
    method: 'POST',
    headers,
  })
  if (!res.ok) throw new Error((await res.text()) || `promote ${res.status}`)
  return res.json()
}

export async function exportBrief(
  brief: BriefResponse,
  format: 'pdf' | 'docx',
  token?: string,
  title = 'Legal Brief',
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_URL}/api/brief/export`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ...brief, format, title }),
  })
  if (!res.ok) throw new Error(`Brief export error: ${res.status}`)

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title.replace(/[^A-Za-z0-9]+/g, '-').toLowerCase() || 'legal-brief'}.${format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export type { ChatResponse, ChunkUsed, SearchResult, SearchResponse, DocumentInfo, DocumentsResponse }
