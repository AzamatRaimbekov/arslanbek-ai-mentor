import type { Page } from '@playwright/test';
import { createFixtures } from './fixtures';
import { observationFixtures } from './observability-fixtures';

// All synthetic data stays in the test process. The browser uses its normal API client.
export async function loginWithFixtures(page: Page) {
  const fixtures = createFixtures();
  const observed = observationFixtures(fixtures);
  const user = { id: '00000000-0000-4000-8000-000000000001', email: 'mentor@example.com', aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: new Date().toISOString() };
  const payload = btoa(JSON.stringify({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600, role: 'authenticated' })).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  const token = `eyJhbGciOiJIUzI1NiJ9.${payload}.test-signature`;
  await page.route('https://dashboard-test.supabase.co/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const params = url.searchParams;
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*', 'access-control-expose-headers': 'content-range' };
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 200, headers });
    if (url.pathname === '/auth/v1/token') return route.fulfill({ json: { access_token: token, token_type: 'bearer', expires_in: 3600, refresh_token: 'test-refresh', user }, headers });
    if (url.pathname === '/auth/v1/user') return route.fulfill({ json: user, headers });
    if (url.pathname === '/auth/v1/logout') return route.fulfill({ status: 204, headers });
    if (url.pathname === '/rest/v1/rpc/is_admin') return route.fulfill({ json: true, headers });
    if (url.pathname === '/rest/v1/rpc/dashboard_stats') return route.fulfill({ json: fixtures.stats(request.postDataJSON().p_days), headers });
    if (url.pathname === '/rest/v1/rpc/student_observability') { const args = request.postDataJSON(); return route.fulfill({ json: observed.snapshot(args.p_student, args.p_days), headers }); }
    if (url.pathname === '/rest/v1/rpc/security_alert_counts') return route.fulfill({ json: { open: observed.alerts.filter(a => a.status === 'open').length, critical: observed.alerts.filter(a => a.status === 'open' && a.severity === 'critical').length, latest_id: 2001 }, headers });
    if (url.pathname === '/rest/v1/rpc/review_security_alert') { const args = request.postDataJSON(); const alert = observed.alerts.find(a => a.id === args.p_alert)!; alert.status = args.p_status; alert.reviewed_at = new Date().toISOString(); return route.fulfill({ status: 204, headers }); }
    const table = url.pathname.split('/').at(-1);
    if (table !== 'students' && table !== 'prompts' && table !== 'summaries' && table !== 'security_alerts') return route.fulfill({ status: 404, json: { message: `Unexpected test request: ${url.pathname}` }, headers });
    let rows = [...(table === 'security_alerts' ? observed.alerts : fixtures[table])] as unknown as Record<string, unknown>[];
    for (const [field, filter] of params) {
      if (['select', 'order', 'offset', 'limit'].includes(field)) continue;
      if (field === 'or') {
        const search = filter.match(/\.ilike\.%(.+?)%/)?.[1]?.replace(/\\_/g, '_').toLowerCase();
        if (search) rows = rows.filter(row => ['display_name', 'claude_name', 'claude_email', 'git_name', 'git_email', 'hostname', 'os_user'].some(key => String(row[key] ?? '').toLowerCase().includes(search)));
        else if (filter.includes('group_name.is.null')) rows = rows.filter(row => !row.group_name);
      } else if (field === 'observability') {
        const query = JSON.parse(filter.slice(3));
        rows = rows.filter(row => query.tags.every((tag: string) => (row.observability as { tags: string[] } | null)?.tags.includes(tag)));
      } else {
        const [operator, ...parts] = filter.split('.');
        const value = parts.join('.');
        rows = rows.filter(row => operator === 'is' ? row[field] === null : operator === 'eq' ? String(row[field]) === value : operator === 'gte' ? String(row[field]) >= value : operator === 'lt' ? String(row[field]) < value : false);
      }
    }
    if (request.method() === 'PATCH') {
      if (rows.length !== 1) return route.fulfill({ status: 406, json: { message: 'Expected one row' }, headers });
      Object.assign(rows[0], request.postDataJSON());
      return route.fulfill({ json: { id: rows[0].id }, headers });
    }
    const sort = (params.get('order') || '').split(',').filter(Boolean);
    rows.sort((a, b) => {
      for (const term of sort) {
        const [field, direction] = term.split('.');
        const left = a[field], right = b[field];
        if (left === right) continue;
        if (left == null) return 1;
        if (right == null) return -1;
        const difference = typeof left === 'number' && typeof right === 'number' ? left - right : String(left).localeCompare(String(right));
        if (difference) return direction === 'desc' ? -difference : difference;
      }
      return 0;
    });
    if (request.headers().accept?.includes('application/vnd.pgrst.object+json')) return route.fulfill({ json: rows[0], headers });
    const offset = Number(params.get('offset') || 0), limit = Number(params.get('limit') || rows.length);
    let selected = rows.slice(offset, offset + limit);
    if (table === 'summaries' && params.get('select')?.includes('student:students')) {
      selected = selected.map(row => ({ ...row, student: fixtures.students.find(s => s.id === row.student_id) || null }));
    }
    return route.fulfill({ json: selected, headers: { ...headers, 'content-range': selected.length ? `${offset}-${offset + selected.length - 1}/${rows.length}` : `*/${rows.length}` } });
  });
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill(user.email);
  await page.getByLabel('Пароль', { exact: true }).fill('test-password');
  await page.getByRole('button', { name: 'Войти в кабинет' }).click();
}
