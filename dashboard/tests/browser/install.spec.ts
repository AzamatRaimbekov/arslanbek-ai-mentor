import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('public guide survives reload, never requests student data and downloads the actual ZIP', async ({ page }, testInfo) => {
  const requests: string[] = [];
  await page.route('https://dashboard-test.supabase.co/**', route => { requests.push(route.request().url()); return route.abort(); });
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/install/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Установите Arslanbek');
  await expect(page.getByRole('button', { name: 'Войти в кабинет' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Кабинет наставника' })).toHaveAttribute('href', '/');
  await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', 'Установить Arslanbek — инструкция для учеников');
  const downloaded = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Скачать скилл', exact: true }).first().click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe('arslanbek-ai-mentor.zip');
  const output = testInfo.outputPath('downloaded.zip');
  await download.saveAs(output);
  expect(await readFile(output)).toEqual(await readFile(new URL('../../public/downloads/arslanbek-ai-mentor.zip', import.meta.url)));
  await page.goto('/install');
  await page.reload({ waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  expect(requests).toEqual([]);
  expect(errors).toEqual([]);
  await page.screenshot({ path: '/private/tmp/arslanbek-install-desktop.png' });
  await page.goto('http://127.0.0.1:5181/install/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Установите Arslanbek');
  await expect(page.getByText('База ещё не подключена.', { exact: false })).toHaveCount(0);
});

test('client selection supplies matching installation, update and opt-out instructions with working copying', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/install');
  await expect(page.locator('#client-instructions')).toContainText('~/.claude/skills/arslanbek-ai-mentor/SKILL.md');
  await page.getByRole('button', { name: 'Codex Установка с помощью агента' }).click();
  await expect(page.locator('#client-instructions')).toContainText('python3 install.py --client codex');
  await expect(page.locator('#client-instructions')).toContainText('$arslanbek-ai-mentor');
  await expect(page.locator('#client-instructions')).toContainText('/hooks');
  await page.getByRole('button', { name: 'Скопировать: Первое сообщение наставнику' }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('$arslanbek-ai-mentor');
  await page.getByText('Скилл уже установлен. Как обновить?', { exact: true }).click();
  await expect(page.locator('#faq')).toContainText('--client codex --setup-only');
  await page.getByText('Как остановить передачу данных', { exact: true }).click();
  await expect(page.locator('#reporting')).toContainText('~/.agents/skills/arslanbek-ai-mentor/scripts/telemetry.py consent no');
  await page.getByRole('button', { name: 'Другое приложение С поддержкой локального MCP' }).click();
  await expect(page.locator('#client-instructions')).toContainText('python3 install.py --client mcp');
  await expect(page.locator('#client-instructions')).toContainText('mcp.json');
  await expect(page.locator('#reporting')).toContainText('~/.arslanbek/mcp/skills/arslanbek-ai-mentor/scripts/telemetry.py consent no');
});

test('mobile guide has no horizontal overflow and explains a blocked clipboard', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.addInitScript(() => { Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('Clipboard unavailable'); } } }); });
  await page.goto('/install');
  await page.evaluate(() => document.fonts.ready);
  await expect(page.getByRole('link', { name: 'Скачать скилл', exact: true }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '/private/tmp/arslanbek-install-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Скопировать: Первое сообщение наставнику' }).click();
  await expect(page.getByText('Браузер не разрешил копирование.', { exact: false })).toBeVisible();
  await page.setViewportSize({ width: 320, height: 720 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('desktop clients receive distinct downloads and native Windows instructions', async ({ page }, testInfo) => {
  await page.goto('/install');
  await page.getByLabel('Ваш компьютер', { exact: true }).selectOption('windows');
  await expect(page.locator('#client-instructions')).toContainText('%USERPROFILE%\\.claude\\skills');
  for (const [button, file] of [
    ['Codex Установка с помощью агента', 'arslanbek-codex.zip'],
    ['Claude Desktop Обычный чат · расширение', 'arslanbek-claude-desktop.mcpb'],
  ]) {
    await page.getByRole('button', { name: button, exact: true }).click();
    const downloaded = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Скачать скилл', exact: true }).first().click();
    const download = await downloaded;
    expect(download.suggestedFilename()).toBe(file);
    const output = testInfo.outputPath(file);
    await download.saveAs(output);
    expect(await readFile(output)).toEqual(await readFile(new URL(`../../public/downloads/${file}`, import.meta.url)));
  }
  await expect(page.locator('#client-instructions')).toContainText('Settings → Extensions → Advanced settings → Install Extension');
  await expect(page.locator('#client-instructions')).not.toContainText('python3 install.py');
  await expect(page.locator('#reporting')).toContainText('полного журнала всех сообщений нет');
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
