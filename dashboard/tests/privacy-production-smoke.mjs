// Read-only check of the published privacy ZIP. No synthetic school records.
import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const expected = process.argv[2];
assert.ok(expected, 'Pass the exact reviewed release ZIP');
const settings = JSON.parse(await readFile(new URL('../../backend/.env.railway.json', import.meta.url), 'utf8'));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.name));
  const publicRequests = [];
  const recordRequest = request => {
    if (/\/(auth|rest)\/v1\//.test(new URL(request.url()).pathname)) publicRequests.push(new URL(request.url()).pathname);
  };
  page.on('request', recordRequest);
  await page.goto(settings.FRONTEND_URL + '/install', { waitUntil: 'networkidle', timeout: 60000 });
  assert.match(await page.getByRole('heading', { level: 1 }).innerText(), /Установите Arslanbek/);
  assert.equal(await page.locator('meta[property="og:title"]').getAttribute('content'), 'Установить Arslanbek — инструкция для учеников');
  assert.equal(await page.getByRole('link', { name: 'Скачать скилл', exact: true }).first().getAttribute('href'), '/downloads/arslanbek-ai-mentor.zip');
  assert.match(await page.locator('.guide-reporting-body').innerText(), /Таблица обратных замен остаётся на компьютере/);
  assert.match(await page.locator('.guide-reporting-body').innerText(), /не изменяет исходные сообщения/);
  await page.getByRole('button', { name: 'Codex Установка с помощью агента' }).click();
  assert.match(await page.locator('#client-instructions').innerText(), /python3 install.py --client codex/);
  await page.getByRole('button', { name: 'Claude Code Обычная установка скилла' }).click();
  await page.screenshot({ path: '/private/tmp/arslanbek-privacy-install-production.png' });
  await page.reload({ waitUntil: 'networkidle' });
  assert.deepEqual(publicRequests, []);
  page.off('request', recordRequest);
  const archive = await page.request.get(settings.FRONTEND_URL + '/downloads/arslanbek-ai-mentor.zip');
  assert.equal(archive.status(), 200);
  const hash = value => createHash('sha256').update(value).digest('hex');
  const downloaded = await archive.body();
  assert.equal(hash(downloaded), hash(await readFile(expected)));
  await writeFile('/private/tmp/arslanbek-privacy-downloaded.zip', downloaded, { mode: 0o600 });

  await page.goto(settings.FRONTEND_URL, { waitUntil: 'networkidle', timeout: 60000 });
  await page.getByLabel('Email', { exact: true }).fill(settings.ADMIN_EMAIL);
  await page.getByLabel('Пароль', { exact: true }).fill(settings.ADMIN_PASSWORD);
  await page.getByRole('button', { name: 'Войти в кабинет' }).click();
  await page.getByRole('heading', { name: 'Каждый ученик — на виду.' }).waitFor({ timeout: 30000 });
  await page.getByRole('button', { name: 'Сводки', exact: true }).click();
  await page.getByRole('heading', { name: 'Как продвигается работа.' }).waitFor();
  await page.waitForFunction(() => !document.querySelector('.feed-card .loading'));
  assert.equal(await page.getByRole('alert').count(), 0);
  await page.getByRole('button', { name: 'Подключение', exact: true }).click();
  await page.getByRole('heading', { name: 'База данных подключена' }).waitFor();
  assert.equal(await page.getByRole('link', { name: 'Открыть инструкцию' }).getAttribute('href'), '/install');
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.getByRole('button', { name: 'Скопировать ссылку', exact: true }).click();
  await page.getByText('Ссылка скопирована', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), settings.FRONTEND_URL.replace(/\/$/, '') + '/install');
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  if (await page.locator('.student-button').count()) {
    await page.locator('.student-button').first().click();
    await page.getByRole('dialog').locator('.work-report').waitFor();
    assert.equal(await page.getByRole('dialog').getByRole('alert').count(), 0);
    await page.getByRole('button', { name: 'Закрыть', exact: true }).click();
  }
  await page.getByRole('button', { name: 'Выйти из аккаунта' }).click();
  await page.getByRole('button', { name: 'Войти в кабинет' }).waitFor();
  assert.deepEqual(errors, []);
  console.info('PASS: published privacy disclosure, exact ZIP checksum, no public student API requests, teacher login, summaries, profile, share link, logout.');
} finally {
  await browser.close();
}
