import { PROMPT_VERSION, prepareInput, callModel, restoreIds, emptyReport } from './analysis.mjs';

export function createHandler(env, fetcher = fetch) {
  return async function handler(req) {
    const origin = req.headers.get('Origin');
    const allowed = (env.ALLOWED_ORIGINS ?? '').split(',').map(v => v.trim()).filter(Boolean);
    const headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'Vary': 'Origin',
      'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type', 'Access-Control-Allow-Methods': 'POST, OPTIONS' };
    if (origin && allowed.includes(origin)) headers['Access-Control-Allow-Origin'] = origin;
    const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers });
    if (origin && !allowed.includes(origin)) return json({ error: 'Этот адрес дашборда не разрешён сервером.' }, 403);
    if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers });
    if (req.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
    const auth = req.headers.get('Authorization') || '';
    if (!auth.startsWith('Bearer ')) return json({ error: 'Требуется вход администратора.' }, 401);
    const needed = ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'OPENAI_API_KEY', 'AI_MODEL'];
    if (needed.some(k => !env[k])) return json({ error: 'Сервер ИИ-анализа ещё не настроен. Заполните серверные секреты.' }, 503);
    const base = env.SUPABASE_URL.replace(/\/$/, '');
    let jobId;
    async function request(path, body, service = false, method = 'POST') {
      const key = service ? env.SUPABASE_SERVICE_ROLE_KEY : env.SUPABASE_ANON_KEY;
      const response = await fetcher(`${base}${path}`, { method, signal: AbortSignal.timeout(20000),
        headers: { apikey: key, Authorization: service ? `Bearer ${key}` : auth, 'Content-Type': 'application/json', Prefer: 'return=representation' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(data?.message || 'Database request failed'); error.status = response.status; error.code = data?.code; throw error;
      }
      return data;
    }
    async function finish(values) {
      await request(`/rest/v1/team_reports?id=eq.${jobId}`, { ...values, completed_at: new Date().toISOString() }, true, 'PATCH');
    }
    try {
      const user = await request('/auth/v1/user', undefined, false, 'GET');
      if (!user?.id) return json({ error: 'Сессия недействительна.' }, 401);
      if (await request('/rest/v1/rpc/is_admin', {}) !== true) return json({ error: 'Доступ только для администратора.' }, 403);
      const raw = await req.text();
      if (raw.length > 2000) return json({ error: 'Request too large' }, 413);
      let params;
      try { params = JSON.parse(raw); } catch { return json({ error: 'Invalid JSON' }, 400); }
      if (!params || ![14, 30, 90].includes(params.days) || (params.group !== null && params.group !== undefined && (typeof params.group !== 'string' || params.group.length > 200))) return json({ error: 'Некорректный период или группа.' }, 400);
      const job = await request('/rest/v1/rpc/begin_team_analysis', { p_days: params.days, p_group: params.group || null });
      jobId = job.id;
      const { input, aliases } = prepareInput(job.input_snapshot);
      const hasEvents = input.students.some(s => s.metrics.prompts || s.metrics.summaries);
      if (!hasEvents) {
        await finish({ status: 'insufficient_data', report: restoreIds(emptyReport(input), aliases), model: null, prompt_version: PROMPT_VERSION });
      } else {
        const { report, usage } = await callModel(input, env, fetcher);
        await finish({ status: 'complete', report: restoreIds(report, aliases), model: env.AI_MODEL, prompt_version: PROMPT_VERSION, usage });
      }
      return json({ id: jobId });
    } catch (error) {
      // Provider and database responses never expose prompt text or credentials to logs.
      const message = error.message?.startsWith('AI ') ? error.message : error.code === 'P0001' ? 'Подождите две минуты перед следующим анализом.' : error.code === '22023' ? 'Выберите группу поменьше или допустимый период.' : 'Анализ не завершён. Проверьте подключение и настройки сервера.';
      if (jobId) { try { await finish({ status: 'failed', error: message }); } catch { /* A running row remains visible for diagnosis. */ } }
      return json({ error: message, ...(jobId ? { id: jobId } : {}) }, error.status === 401 ? 401 : error.code === 'P0001' ? 429 : error.code === '22023' ? 400 : 502);
    }
  };
}
