import { createHandler } from '../supabase/functions/analyze-team/handler.mjs';

export function createGateway(env, { fetcher = fetch, isReady = () => true } = {}) {
  const origins = (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
  const analyze = createHandler(env, fetcher);
  const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
  return async request => {
    const url = new URL(request.url);
    const origin = request.headers.get('origin');
    const cors = response => {
      response.headers.set('Vary', 'Origin');
      response.headers.set('X-Content-Type-Options', 'nosniff');
      if (origin && origins.includes(origin)) response.headers.set('Access-Control-Allow-Origin', origin);
      response.headers.set('Access-Control-Allow-Methods', 'GET, HEAD, POST, PATCH, PUT, DELETE, OPTIONS');
      response.headers.set('Access-Control-Allow-Headers', 'authorization, apikey, content-type, accept, accept-profile, content-profile, x-client-info, x-supabase-api-version, prefer, range, range-unit');
      response.headers.set('Access-Control-Expose-Headers', 'content-range, range-unit');
      return response;
    };
    if (origin && !origins.includes(origin)) return cors(json({ error: 'Origin not allowed' }, 403));
    if (url.pathname === '/healthz') {
      if (!isReady()) return cors(json({ status: 'starting' }, 503));
      try {
        const results = await Promise.all([`${env.AUTH_URL}/health`, `${env.REST_HEALTH_URL}/ready`].map(address => fetcher(address, { signal: AbortSignal.timeout(3000) })));
        if (results.some(result => !result.ok)) return cors(json({ status: 'unavailable' }, 503));
        return cors(json({ status: 'ok', analysis_configured: env.AI_ANALYSIS_ENABLED !== 'false' && !!(env.OPENAI_API_KEY && env.AI_MODEL) }));
      } catch { return cors(json({ status: 'unavailable' }, 503)); }
    }
    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }));
    if (!isReady()) return cors(json({ error: 'Backend is starting' }, 503));
    const key = request.headers.get('apikey');
    if (!key || ![env.SUPABASE_ANON_KEY, env.SUPABASE_SERVICE_ROLE_KEY].includes(key)) return cors(json({ error: 'Invalid API key' }, 401));
    if (url.pathname === '/functions/v1/analyze-team') {
      if (env.AI_ANALYSIS_ENABLED === 'false') return cors(json({ error: 'Серверный ИИ-анализ выключен. Сводки участников доступны в кабинете.' }, 404));
      return cors(await analyze(request));
    }
    let target;
    if (url.pathname.startsWith('/auth/v1/')) target = env.AUTH_URL + url.pathname.slice('/auth/v1'.length) + url.search;
    else if (url.pathname.startsWith('/rest/v1/')) target = env.REST_URL + url.pathname.slice('/rest/v1'.length) + url.search;
    else return cors(json({ error: 'Not found' }, 404));
    const headers = new Headers();
    for (const name of ['authorization', 'content-type', 'accept', 'accept-profile', 'content-profile', 'prefer', 'range', 'range-unit', 'x-client-info', 'x-supabase-api-version']) {
      const value = request.headers.get(name); if (value) headers.set(name, value);
    }
    // The caller's role remains subject to GoTrue/PostgREST JWT validation and RLS.
    if (!headers.has('authorization')) headers.set('authorization', `Bearer ${key}`);
    try {
      const upstream = await fetcher(target, { method: request.method, headers,
        ...(['GET', 'HEAD'].includes(request.method) ? {} : { body: await request.arrayBuffer() }),
        redirect: 'manual', signal: AbortSignal.timeout(25000) });
      const outputHeaders = new Headers(upstream.headers);
      for (const name of ['content-encoding', 'content-length', 'connection', 'transfer-encoding', 'access-control-allow-origin']) outputHeaders.delete(name);
      outputHeaders.set('Cache-Control', 'no-store');
      return cors(new Response(upstream.body, { status: upstream.status, headers: outputHeaders }));
    } catch { return cors(json({ error: 'Upstream service unavailable' }, 502)); }
  };
}
