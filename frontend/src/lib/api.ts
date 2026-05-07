const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

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
  const r = await fetch(`${API_URL}/api/documents?${params.toString()}`)
  if (!r.ok) throw new Error(`documents ${r.status}`)
  return r.json()
}

export async function attachDocumentToSession(sessionId: string, documentId: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/sessions/${sessionId}/documents/attach`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_id: documentId }),
  })
  if (!r.ok) throw new Error(`attach ${r.status}`)
}

export async function detachDocumentFromSession(sessionId: string, documentId: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/sessions/${sessionId}/documents/${documentId}`, {
    method: 'DELETE',
  })
  if (!r.ok) throw new Error(`detach ${r.status}`)
}

export async function listSessionDocuments(sessionId: string): Promise<{ documents: LibraryDocument[] }> {
  const r = await fetch(`${API_URL}/api/sessions/${sessionId}/documents`)
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
  const r = await fetch(`${API_URL}/api/folders?user_id=${encodeURIComponent(userId)}`)
  if (!r.ok) throw new Error(`folders ${r.status}`)
  return r.json()
}

export async function createFolder(userId: string, name: string): Promise<FolderRow> {
  const r = await fetch(`${API_URL}/api/folders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, name }),
  })
  if (!r.ok) throw new Error((await r.text()) || `create folder ${r.status}`)
  return r.json()
}

export async function renameFolder(folderId: string, name: string): Promise<void> {
  const r = await fetch(`${API_URL}/api/folders/${folderId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!r.ok) throw new Error(`rename ${r.status}`)
}

export async function deleteFolder(folderId: string, cascade = false): Promise<void> {
  const r = await fetch(`${API_URL}/api/folders/${folderId}?cascade=${cascade}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(`delete ${r.status}`)
}

export async function moveDocumentToFolder(documentId: string, folderId: string | null): Promise<void> {
  const r = await fetch(`${API_URL}/api/documents/${documentId}/folder`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
  if (!r.ok) throw new Error(`move ${r.status}`)
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
): Promise<{ status: string; document_id: string }> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

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
  source: 'generated' | 'extracted' | 'merged' | 'uploaded'
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

export interface StreamHandlers {
  onThinking?: () => void
  onToken?: (text: string) => void
  onToolCall?: (call: ToolCallEvent) => void
  onToolResult?: (result: ToolResultEvent) => void
  onArtifact?: (artifact: ArtifactView) => void
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

  if (!res.ok) throw new Error(`API error: ${res.status}`)

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  // Sources accumulator — emitted as a single block when the run ends.
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

export type { ChatResponse, ChunkUsed, SearchResult, SearchResponse, DocumentInfo, DocumentsResponse }
