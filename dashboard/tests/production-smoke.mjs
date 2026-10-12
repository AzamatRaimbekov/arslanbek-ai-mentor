// Explicit manual smoke check against the deployed school; never prints credentials.
import { chromium } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const settings = JSON.parse(await readFile(new URL('../../backend/.env.railway.json', import.meta.url), 'utf8'));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => console.error('Browser request failed:', request.method(), new URL(request.url()).pathname, request.failure()?.errorText));
  page.on('console', message => { if (message.type() === 'error') console.error('Browser:', message.text()); });
  const publicApiRequests = [];
  const recordPublicRequest = request => { if (/\/(auth|rest)\/v1\//.test(new URL(request.url()).pathname)) publicApiRequests.push(request.url()); };
  page.on('request', recordPublicRequest);
  await page.goto(settings.FRONTEND_URL + '/install', { waitUntil: 'networkidle', timeout: 60000 });
  await page.getByRole('heading', { level: 1 }).waitFor();
  assert.match(await page.getByRole('heading', { level: 1 }).innerText(), /Установите Arslanbek/);
  assert.equal(await page.getByRole('button', { name: 'Войти в кабинет' }).count(), 0);
  assert.equal(await page.locator('meta[property="og:title"]').getAttribute('content'), 'Установить Arslanbek — инструкция для учеников');
  assert.equal(await page.getByRole('link', { name: 'Скачать скилл', exact: true }).first().getAttribute('href'), '/downloads/arslanbek-ai-mentor.zip');
  await page.getByRole('button', { name: 'Codex Установка с помощью агента' }).click();
  assert.match(await page.locator('#client-instructions').innerText(), /python3 install.py --client codex/);
  assert.equal(await page.getByRole('link', { name: 'Скачать скилл', exact: true }).first().getAttribute('href'), '/downloads/arslanbek-codex.zip');
  await page.getByRole('button', { name: 'Claude Desktop Обычный чат · расширение' }).click();
  assert.match(await page.locator('#client-instructions').innerText(), /Install Extension/);
  assert.equal(await page.getByRole('link', { name: 'Скачать скилл', exact: true }).first().getAttribute('href'), '/downloads/arslanbek-claude-desktop.mcpb');
  await page.getByRole('button', { name: 'Claude Code Обычная установка скилла' }).click();
  await page.screenshot({ path: '/private/tmp/arslanbek-install-production.png' });
  await page.reload({ waitUntil: 'networkidle' });
  assert.deepEqual(publicApiRequests, []);
  page.off('request', recordPublicRequest);
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
  await page.getByText('~/.claude/skills/arslanbek-ai-mentor/', { exact: true }).waitFor();
  assert.equal(await page.getByText('python3 install.py --client claude-code', { exact: true }).count(), 0);
  await page.getByLabel('Приложение участника').selectOption('codex');
  await page.getByText('python3 install.py --client codex', { exact: true }).waitFor();
  await page.getByLabel('Приложение участника').selectOption('mcp');
  await page.getByText('python3 install.py --client mcp', { exact: true }).waitFor();
  const archive = await page.request.get(settings.FRONTEND_URL + '/downloads/arslanbek-ai-mentor.zip');
  assert.equal(archive.status(), 200);
  const hash = value => createHash('sha256').update(value).digest('hex');
  assert.equal(hash(await archive.body()), hash(await readFile(process.argv[2] || process.env.ARSLANBEK_RELEASE_ARCHIVE || new URL('../public/downloads/arslanbek-ai-mentor.zip', import.meta.url))));
  const releaseResponse = await page.request.get(settings.FRONTEND_URL + '/downloads/release.json');
  assert.equal(releaseResponse.status(), 200);
  const release = await releaseResponse.json();
  assert.equal(release.version, '9.2.0');
  assert.equal(release.windows_runtime_bundled, true);
  for (const filename of ['arslanbek-codex.zip', 'arslanbek-claude-desktop.mcpb']) {
    const download = await page.request.get(settings.FRONTEND_URL + '/downloads/' + filename);
    assert.equal(download.status(), 200);
    const checksum = hash(await download.body());
    assert.equal(checksum, release.files[filename].sha256);
    assert.equal(checksum, hash(await readFile(new URL('../public/downloads/' + filename, import.meta.url))));
  }
  await page.getByRole('button', { name: 'Обзор', exact: true }).click();
  await page.screenshot({ path: '/private/tmp/arslanbek-production.png', fullPage: true });
  if (await page.locator('.student-button').count()) {
    await page.locator('.student-button').first().click();
    await page.getByRole('dialog').locator('.work-report').waitFor();
    await page.getByRole('dialog').getByRole('heading', { name: 'Что ученик осваивает' }).waitFor();
    assert.equal(await page.getByRole('dialog').locator('.knowledge-node').count(), 11);
    const matrix = page.getByRole('dialog').getByRole('region', { name: 'Матрица компетенций' });
    assert.equal(await matrix.getByRole('button').count(), 11);
    for (const name of ['Работа с ИИ', 'Инструменты и автоматизация', 'Разработка продукта']) {
      assert.equal(await matrix.getByRole('heading', { name, exact: true }).count(), 1);
    }
    const firstCompetency = matrix.getByRole('button').first();
    await firstCompetency.click();
    assert.equal(await firstCompetency.getAttribute('aria-pressed'), 'true');
    assert.equal(await page.getByRole('dialog').locator('.competency-detail').getAttribute('id'), await firstCompetency.getAttribute('aria-controls'));
    assert.equal(await page.getByRole('dialog').getByRole('alert').count(), 0);
    await page.getByRole('dialog').getByRole('tab', { name: 'Инструменты', exact: true }).click();
    await page.getByRole('dialog').getByRole('heading', { name: 'Инструменты и способы работы' }).waitFor();
    await page.getByRole('dialog').getByRole('tab', { name: 'Защита данных', exact: true }).click();
    await page.getByRole('dialog').getByRole('heading', { name: 'Сигналы для проверки' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('.security-panel .loading'));
    assert.equal(await page.getByRole('dialog').getByRole('alert').count(), 0);
    await page.setViewportSize({ width: 375, height: 900 });
    await page.getByRole('dialog').getByRole('tab', { name: 'Развитие', exact: true }).click();
    for (const card of await matrix.getByRole('button').all()) {
      const bounds = await card.boundingBox();
      assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 375, 'Competency card fits a mobile viewport');
      assert.ok(bounds.width > 100 && bounds.height >= 44, 'Competency card remains readable and tappable');
      assert.ok(await card.evaluate(el => el.scrollWidth <= el.clientWidth), 'Competency text does not overflow');
    }
    await matrix.getByRole('button').first().click();
    const detail = await page.getByRole('dialog').locator('.competency-detail').boundingBox();
    assert.ok(detail && detail.y >= 50 && detail.y < 900, 'Selecting a competency reveals its evidence below the sticky header');
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.getByRole('button', { name: 'Закрыть', exact: true }).click();
  }
  await page.getByRole('button', { name: 'Выйти из аккаунта' }).click();
  await page.getByRole('button', { name: 'Войти в кабинет' }).waitFor();
  assert.deepEqual(errors, []);
  console.info('PASS: public install guide, all release checksums, share link, login, summaries, interactive competency matrix, tools, privacy tabs, logout, no JavaScript errors.');
} finally { await browser.close(); }
