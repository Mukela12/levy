'use client'

import { useState } from 'react'
import { useAuth } from '@/components/auth/auth-provider'
import { searchCorpus } from '@/lib/api'
import { Search, FileText, Clock, Loader2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import type { SearchResult } from '@/lib/api'

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [timing, setTiming] = useState<{ total_ms: number } | null>(null)
  const [searched, setSearched] = useState(false)
  const { session } = useAuth()

  async function handleSearch(e?: React.FormEvent) {
    e?.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    setSearched(true)
    try {
      const res = await searchCorpus(query, { top_k: 10, token: session?.access_token })
      setResults(res.results)
      setTiming(res.timing)
    } catch {
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-4 border-b border-white/[0.06]">
        <h1 className="text-xl font-bold text-white">Search Legal Corpus</h1>
        <p className="text-sm text-[#6a6a6f] mt-1">
          Search directly through ingested Zambian legislation
        </p>
      </div>

      <div className="px-6 py-4">
        <form onSubmit={handleSearch} className="flex gap-3 max-w-3xl">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#5a5a5f]" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for legal provisions, sections, or topics..."
              className="pl-10 bg-white/5 border-white/10 text-white placeholder:text-[#5a5a5f]"
            />
          </div>
          <Button type="submit" disabled={loading} className="bg-blue-600 hover:bg-blue-700 text-white">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Search'}
          </Button>
        </form>

        {timing && (
          <div className="flex items-center gap-1.5 mt-3 text-xs text-[#5a5a5f]">
            <Clock className="w-3 h-3" />
            <span>{results.length} results in {(timing.total_ms / 1000).toFixed(2)}s</span>
          </div>
        )}
      </div>

      <div className="flex-1 px-6 pb-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
          </div>
        ) : results.length > 0 ? (
          <div className="space-y-3 max-w-3xl">
            {results.map((result, i) => (
              <div
                key={result.id || i}
                className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.1] transition-colors space-y-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-blue-400" />
                    <span className="text-sm font-semibold text-blue-400">{result.act_name}</span>
                    {result.section && (
                      <span className="text-xs text-[#6a6a6f]">
                        Section {result.section}
                        {result.part ? `, Part ${result.part}` : ''}
                      </span>
                    )}
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-[#6a6a6f]">
                    {(result.similarity * 100).toFixed(0)}% match
                  </span>
                </div>
                <p className="text-sm text-[#a0a0a5] leading-relaxed">{result.content}</p>
                {(result.page_start || result.page_end) && (
                  <p className="text-[10px] text-[#5a5a5f]">
                    Page {result.page_start}
                    {result.page_end && result.page_end !== result.page_start ? `–${result.page_end}` : ''}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : searched ? (
          <div className="text-center py-12">
            <Search className="w-8 h-8 text-[#3a3a3f] mx-auto mb-3" />
            <p className="text-[#6a6a6f]">No results found. Try different keywords.</p>
          </div>
        ) : (
          <div className="text-center py-12">
            <Search className="w-8 h-8 text-[#3a3a3f] mx-auto mb-3" />
            <p className="text-[#6a6a6f]">Search across all ingested Zambian legislation</p>
          </div>
        )}
      </div>
    </div>
  )
}
