import test from 'node:test';
import assert from 'node:assert/strict';
import { createGateway } from './gateway.mjs';

const env = { AUTH_URL: 'http://auth:9999', REST_URL: 'http://rest:3000', REST_HEALTH_URL: 'http://rest:3001',
  SUPABASE_ANON_KEY: 'public-test-key', SUPABASE_SERVICE_ROLE_KEY: 'server-only-test-key', ALLOWED_ORIGINS: 'https://mentor.example.com' };
const request = (path, options = {}) => new Request(`https://api.example.com${path}`, options);

test('gateway rejects missing keys and unapproved origins without contacting upstreams', async () => {
  const gateway = createGateway(env, { fetcher: () => { throw new Error('Unexpected upstream request'); } });
  assert.equal((await gateway(request('/rest/v1/students'))).status, 401);
  assert.equal((await gateway(request('/rest/v1/students', { headers: { apikey: 'wrong' } }))).status, 401);
  const denied = await gateway(request('/rest/v1/students', { headers: { apikey: env.SUPABASE_ANON_KEY, origin: 'https://other.example.com' } }));
  assert.equal(denied.status, 403);
  assert.equal(denied.headers.get('access-control-allow-origin'), null);
});

test('proxy preserves caller JWT, filters, patches and total counts without escalating privileges', async () => {
  const gateway = createGateway(env, { fetcher: async (url, options) => {
    assert.equal(url, 'http://rest:3000/students?id=eq.one');
    assert.equal(options.headers.get('authorization'), 'Bearer admin-session-token');
    assert.equal(options.headers.get('prefer'), 'return=representation');
    assert.equal(options.headers.get('x-forwarded-for'), null);
    assert.deepEqual(JSON.parse(new TextDecoder().decode(options.body)), { group_name: 'Team' });
    return new Response('[{"id":"one"}]', { headers: { 'Content-Type': 'application/json', 'Content-Range': '0-0/1', 'Content-Encoding': 'gzip' } });
  } });
  const result = await gateway(request('/rest/v1/students?id=eq.one', { method: 'PATCH',
    headers: { apikey: env.SUPABASE_ANON_KEY, authorization: 'Bearer admin-session-token', prefer: 'return=representation', origin: env.ALLOWED_ORIGINS, 'x-forwarded-for': 'spoofed' },
    body: JSON.stringify({ group_name: 'Team' }) }));
  assert.equal(result.status, 200);
  assert.equal(result.headers.get('content-range'), '0-0/1');
  assert.equal(result.headers.get('content-encoding'), null);
  assert.equal(result.headers.get('access-control-allow-origin'), env.ALLOWED_ORIGINS);
  assert.equal(result.headers.get('cache-control'), 'no-store');
  assert.deepEqual(await result.json(), [{ id: 'one' }]);
});

test('anonymous telemetry and password login use the public key only', async () => {
  const seen = [];
  const gateway = createGateway(env, { fetcher: async (url, options) => {
    seen.push(url);
    assert.equal(options.headers.get('authorization'), `Bearer ${env.SUPABASE_ANON_KEY}`);
    return Response.json({ ok: true });
  } });
  for (const path of ['/rest/v1/rpc/ingest', '/auth/v1/token?grant_type=password']) {
    assert.equal((await gateway(request(path, { method: 'POST', headers: { apikey: env.SUPABASE_ANON_KEY }, body: '{}' }))).status, 200);
  }
  assert.deepEqual(seen, ['http://rest:3000/rpc/ingest', 'http://auth:9999/token?grant_type=password']);
});

test('browser authentication preflight permits every header sent by the Supabase client', async () => {
  const gateway = createGateway(env, { fetcher: async (_url, options) => {
    assert.equal(options.headers.get('x-supabase-api-version'), '2024-01-01');
    return Response.json({ ok: true });
  } });
  const headers = ['apikey', 'authorization', 'content-type', 'x-client-info', 'x-supabase-api-version', 'content-profile', 'accept-profile'];
  const preflight = await gateway(request('/auth/v1/token?grant_type=password', { method: 'OPTIONS', headers: {
    origin: env.ALLOWED_ORIGINS, 'access-control-request-method': 'POST', 'access-control-request-headers': headers.join(','),
  } }));
  assert.equal(preflight.status, 204);
  const allowed = preflight.headers.get('access-control-allow-headers').split(',').map(value => value.trim());
  assert.ok(headers.every(header => allowed.includes(header)));
  const response = await gateway(request('/auth/v1/token?grant_type=password', { method: 'POST', body: '{}', headers: {
    origin: env.ALLOWED_ORIGINS, apikey: env.SUPABASE_ANON_KEY, 'x-supabase-api-version': '2024-01-01',
  } }));
  assert.equal(response.status, 200);
});

test('startup, upstream failure and missing AI configuration never return fabricated data', async () => {
  const starting = createGateway(env, { isReady: () => false });
  assert.equal((await starting(request('/healthz'))).status, 503);
  assert.equal((await starting(request('/rest/v1/students'))).status, 503);
  const unavailable = createGateway(env, { fetcher: async () => { throw new Error('private credentials must not leak'); } });
  assert.equal((await unavailable(request('/healthz'))).status, 503);
  const response = await unavailable(request('/rest/v1/students', { headers: { apikey: env.SUPABASE_ANON_KEY } }));
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { error: 'Upstream service unavailable' });
  const analysis = await unavailable(request('/functions/v1/analyze-team', { method: 'POST', headers: { apikey: env.SUPABASE_ANON_KEY, authorization: 'Bearer user-token' }, body: '{"days":30}' }));
  assert.equal(analysis.status, 503);
});

test('summary-only deployment cannot call an AI provider even with leftover provider credentials', async () => {
  const gateway = createGateway({ ...env, AI_ANALYSIS_ENABLED: 'false', OPENAI_API_KEY: 'unused-key', AI_MODEL: 'unused-model' }, {
    fetcher: async () => { throw new Error('Disabled analysis must not contact any upstream'); },
  });
  const result = await gateway(request('/functions/v1/analyze-team', { method: 'POST', headers: { apikey: env.SUPABASE_ANON_KEY }, body: '{"days":30}' }));
  assert.equal(result.status, 404);
});
