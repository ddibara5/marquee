import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchWithJwtFutureRetry } from '../src/api-retry.js'

const future = () => new Response(JSON.stringify({ code: 'PGRST303', message: 'JWT issued at future' }), { status: 401, headers: { 'content-type': 'application/json' } })

test('retries only the transient JWT rejection on reads and keeps the same request', async () => {
  const delays = [], calls = []
  const headers = new Headers({ Authorization: 'Bearer test-token' })
  const request = async (_, init) => {
    calls.push(init)
    return calls.length < 3 ? future() : new Response('[]', { status: 200 })
  }
  const response = await fetchWithJwtFutureRetry('/rest/v1/marquee_titles', { method: 'GET', headers }, request, async ms => { delays.push(ms) })
  assert.equal(response.status, 200)
  assert.deepEqual(delays, [1000, 2000])
  assert.equal(calls.length, 3)
  assert.ok(calls.every(init => init.headers.get('Authorization') === 'Bearer test-token'))
})

test('never retries writes or unrelated authorization failures', async () => {
  let calls = 0
  const request = async () => { calls++; return future() }
  assert.equal((await fetchWithJwtFutureRetry('/rest/v1/marquee_statuses', { method: 'POST' }, request)).status, 401)
  assert.equal(calls, 1)
  const unrelated = async () => { calls++; return new Response(JSON.stringify({ code: 'PGRST303', message: 'Different JWT failure' }), { status: 401 }) }
  assert.equal((await fetchWithJwtFutureRetry('/rest/v1/marquee_titles', { method: 'GET' }, unrelated)).status, 401)
  assert.equal(calls, 2)
})

test('stops after a bounded number of failures', async () => {
  let calls = 0
  const delays = []
  const response = await fetchWithJwtFutureRetry('/rest/v1/marquee_titles', { method: 'GET' }, async () => { calls++; return future() }, async ms => { delays.push(ms) })
  assert.equal(response.status, 401)
  assert.equal(calls, 4)
  assert.deepEqual(delays, [1000, 2000, 4000])
})
