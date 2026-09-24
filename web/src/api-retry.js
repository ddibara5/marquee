// Supabase can briefly reject a newly issued, otherwise valid JWT with
// PGRST303 while its Data API validator catches up. Retry only safe reads and
// only this exact response; writes and all other failures surface unchanged.
const delays = [1000, 2000, 4000]

export async function fetchWithJwtFutureRetry(input, init, request = fetch, wait = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase()
  for (let attempt = 0; ; attempt++) {
    const response = await request(input, init)
    if (!['GET', 'HEAD'].includes(method) || response.status !== 401 || attempt === delays.length) return response
    let error
    try { error = await response.clone().json() } catch { return response }
    if (error?.code !== 'PGRST303' || error?.message !== 'JWT issued at future') return response
    await wait(delays[attempt])
  }
}
