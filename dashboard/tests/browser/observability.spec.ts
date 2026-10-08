import { test, expect } from '@playwright/test';
import { loginWithFixtures } from './mock-supabase';

test('knowledge map opens sourced evidence, filters tagged prompts and distinguishes available tools from use', async ({ page }) => {
  await loginWithFixtures(page);
  await page.getByRole('button', { name: 'Открыть профиль: Айдана Абдылдаева' }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading', { name: 'Что ученик осваивает' })).toBeVisible();
  await expect(dialog.locator('.knowledge-node')).toHaveCount(11);
  await expect(dialog.getByText('Самостоятельно сформулировал цель корзины')).toBeVisible();
  await dialog.locator('.knowledge-node').filter({ hasText: 'Контекст' }).click();
  await expect(dialog.getByText('За этот период нет подтверждений.', { exact: false })).toBeVisible();
  await dialog.getByRole('button', { name: /^Промпт-инжиниринг:/ }).focus();
  await page.keyboard.press('Enter');
  await dialog.getByRole('button', { name: 'Открыть исходную сводку' }).first().click();
  await expect(dialog.getByRole('heading', { name: 'Исходная сводка наблюдения' })).toBeVisible();
  await dialog.getByLabel('Период развития ученика').selectOption('90');
  await expect(dialog.locator('.observability-heading').getByText('За 90 дней.', { exact: false })).toBeVisible();
  await dialog.locator('.topic-tags').getByRole('button', { name: 'Тесты', exact: false }).click();
  await expect(dialog.getByLabel('Тег промптов ученика')).toHaveValue('testing');
  await expect(dialog.locator('.history-card')).not.toHaveCount(0);
  await expect(dialog.locator('.history-card').filter({ hasNot: page.getByText('Тесты', { exact: true }) })).toHaveCount(0);
  await dialog.getByRole('tab', { name: 'Инструменты', exact: true }).click();
  await expect(dialog.getByRole('heading', { name: 'Доступно в среде' })).toBeVisible();
  await expect(dialog.getByText('example-skill', { exact: false })).toBeVisible();
  await expect(dialog.getByText('Выполнил агент', { exact: false }).first()).toBeVisible();
  await dialog.getByRole('tab', { name: 'Развитие', exact: true }).click();
  await page.setViewportSize({ width: 1366, height: 1500 });
  await dialog.locator('.learning-map').screenshot({ path: '/private/tmp/arslanbek-matrix-desktop.png' });
});

test('teacher notification opens an alert; false positive review updates the audit state and badge', async ({ page }) => {
  await loginWithFixtures(page);
  await page.locator('.security-notice').click();
  await expect(page.getByRole('heading', { name: 'Сигналы для проверки' })).toBeVisible();
  await expect(page.getByText('Передача конкретному сервису не подтверждена.', { exact: false })).toBeVisible();
  await expect(page.getByText('Признаки API-ключа или токена', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Ложное срабатывание' }).click();
  await expect(page.getByText('Сигналов для проверки нет', { exact: true })).toBeVisible();
  await page.getByLabel('Фильтр сигналов').selectOption('all');
  await expect(page.getByText('Отмечено как ложное срабатывание', { exact: false })).toBeVisible();
});

test('student skill map fits a mobile screen and remains usable', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await loginWithFixtures(page);
  await page.getByRole('button', { name: 'Открыть профиль: Айдана Абдылдаева' }).click();
  await expect(page.getByRole('heading', { name: 'Что ученик осваивает' })).toBeVisible();
  const dialog = page.getByRole('dialog');
  const matrix = dialog.getByRole('region', { name: 'Матрица компетенций' });
  const box = await matrix.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(375);
  const cards = await matrix.getByRole('button').all();
  expect(cards).toHaveLength(11);
  for (const card of cards) {
    const bounds = await card.boundingBox();
    expect(bounds!.width).toBeGreaterThan(100);
    expect(bounds!.height).toBeGreaterThanOrEqual(44);
    expect(bounds!.x).toBeGreaterThanOrEqual(box!.x);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(box!.x + box!.width);
    expect(await card.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  }
  await matrix.getByRole('button', { name: /^Контекст-инжиниринг:/ }).click();
  await expect(dialog.locator('.competency-detail').getByRole('heading', { name: 'Контекст-инжиниринг' })).toBeInViewport();
  await expect(matrix.getByRole('button', { name: /^Контекст-инжиниринг:/ })).toHaveAttribute('aria-pressed', 'true');
  await page.setViewportSize({ width: 375, height: 2400 });
  await matrix.evaluate(el => el.scrollIntoView({ block: 'start' }));
  await matrix.screenshot({ path: '/private/tmp/arslanbek-matrix-mobile.png' });
});
