import { test, expect } from '@playwright/test';

test('live mode requires login and an admin role, handles empty data, failures and logout', async ({ page }) => {
  let isAdmin = false;
  let statsFail = false;
  let statsRequests = 0;
  const user = { id: '00000000-0000-4000-8000-000000000001', email: 'mentor@example.com', aud: 'authenticated', role: 'authenticated', app_metadata: {}, user_metadata: {}, created_at: new Date().toISOString() };
  const payload = Buffer.from(JSON.stringify({ sub: user.id, exp: Math.floor(Date.now() / 1000) + 3600, role: 'authenticated' })).toString('base64url');
  const token = `eyJhbGciOiJIUzI1NiJ9.${payload}.test-signature`;
  await page.route('https://dashboard-test.supabase.co/**', async route => {
    const url = new URL(route.request().url());
    const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-expose-headers': 'content-range' };
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 200, headers });
    if (url.pathname === '/auth/v1/token') return route.fulfill({ json: { access_token: token, token_type: 'bearer', expires_in: 3600, refresh_token: 'test-refresh', user }, headers });
    if (url.pathname === '/auth/v1/user') return route.fulfill({ json: user, headers });
    if (url.pathname === '/auth/v1/logout') return route.fulfill({ status: 204, headers });
    if (url.pathname === '/rest/v1/rpc/is_admin') return route.fulfill({ json: isAdmin, headers });
    if (url.pathname === '/rest/v1/rpc/dashboard_stats') {
      statsRequests++;
      if (statsFail) return route.fulfill({ status: 500, json: { message: 'Test database unavailable' }, headers });
      return route.fulfill({ json: { students: 0, new_students: 0, active_students: 0, prompts: 0, summaries: 0, average_level: null, unassessed: 0, groups: [], levels: Array.from({ length: 6 }, (_, level) => ({ level, count: 0 })), activity: Array.from({ length: 30 }, (_, i) => ({ date: new Date(Date.now() - (29 - i) * 86400000).toISOString().slice(0, 10), prompts: 0 })) }, headers });
    }
    if (url.pathname === '/rest/v1/students') return route.fulfill({ json: [], headers: { ...headers, 'content-range': '*/0' } });
    return route.fulfill({ status: 404, json: { message: `Unexpected test request: ${url.pathname}` }, headers });
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Войти в кабинет' })).toBeVisible();
  await page.getByLabel('Email', { exact: true }).fill(user.email);
  await page.getByLabel('Пароль', { exact: true }).fill('test-password');
  await page.getByRole('button', { name: 'Войти в кабинет' }).click();
  await expect(page.getByRole('alert')).toContainText('нет доступа');
  expect(statsRequests).toBe(0);
  isAdmin = true;
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page.getByRole('heading', { name: 'Каждый ученик — на виду.' })).toBeVisible();
  await expect(page.getByText('Первые ученики скоро появятся')).toBeVisible();
  await expect(page.getByText('Демо-режим')).toHaveCount(0);
  statsFail = true;
  await page.getByRole('button', { name: 'Обновить данные' }).click();
  await expect(page.getByRole('alert')).toContainText('Test database unavailable');
  await expect(page.getByText('Демо-режим')).toHaveCount(0);
  await page.getByRole('button', { name: 'Выйти из аккаунта' }).click();
  await expect(page.getByRole('button', { name: 'Войти в кабинет' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Каждый ученик — на виду.' })).toHaveCount(0);
});
