import { GoTrueClient } from '@supabase/auth-js'
import { PostgrestClient } from '@supabase/postgrest-js'

// The publishable key is public; row-level security protects personal records.
const url = import.meta.env?.VITE_SUPABASE_URL || 'https://eiskobjlvxzwvucgpenk.supabase.co'
const key = import.meta.env?.VITE_SUPABASE_PUBLISHABLE_KEY || 'sb_publishable_Rfcg7pTWt0Vq7ep3WQYFvQ_anT_mnX7'
export const ownerEmail = 'ddibara@gmail.com'
export const auth = new GoTrueClient({ url: `${url}/auth/v1`, headers: { apikey: key }, storageKey: 'marquee-auth-v1', persistSession: true, autoRefreshToken: true, detectSessionInUrl: true })
const rest = new PostgrestClient(`${url}/rest/v1`, { schema: 'public', headers: { apikey: key }, fetch: async (input, init = {}) => {
  const { data } = await auth.getSession()
  const headers = new Headers(init.headers || {})
  headers.set('apikey', key)
  headers.set('Authorization', `Bearer ${data?.session?.access_token || key}`)
  return fetch(input, { ...init, headers })
} })
export const from = rest.from.bind(rest)
