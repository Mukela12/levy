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

export async function uploadDocument(file: File, token?: string): Promise<{ status: string; document_id: string }> {
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const formData = new FormData()
  formData.append('file', file)

  const res = await fetch(`${API_URL}/api/documents/upload`, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (!res.ok) throw new Error(`Upload error: ${res.status}`)
  return res.json()
}

export async function streamQuery(
  question: string,
  options?: { model?: string; top_k?: number; token?: string },
  onChunk?: (text: string) => void,
  onDone?: (metadata: { chunks_used: ChunkUsed[]; timing: Record<string, number> }) => void
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
    }),
  })

  if (!res.ok) throw new Error(`API error: ${res.status}`)

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') continue
        try {
          const parsed = JSON.parse(data)
          if (parsed.type === 'token') onChunk?.(parsed.content)
          if (parsed.type === 'done') onDone?.(parsed)
        } catch {
          // skip malformed lines
        }
      }
    }
  }
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
