type SupabaseUser = {
  id: string
  email?: string
  user_metadata?: {
    full_name?: string
  }
}

function extractBearerToken(authorization: string | null) {
  if (!authorization) return null
  const [scheme, token] = authorization.split(' ', 2)
  if (scheme?.toLowerCase() !== 'bearer' || !token?.trim()) return null
  return token.trim()
}

export async function getAuthenticatedSupabaseUser(authorization: string | null) {
  const token = extractBearerToken(authorization)
  if (!token) return null

  const baseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!baseUrl || !anonKey) {
    throw new Error('Missing Supabase public envs for server-side auth verification')
  }

  const response = await fetch(`${baseUrl}/auth/v1/user`, {
    headers: {
      apikey: anonKey,
      Authorization: `Bearer ${token}`,
    },
    cache: 'no-store',
  })

  if (!response.ok) return null
  return (await response.json()) as SupabaseUser
}
