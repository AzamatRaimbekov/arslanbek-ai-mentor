import { test, expect } from '@playwright/test';

test('missing production configuration never silently displays fictional people', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Подключим вашу команду.' })).toBeVisible();
  await expect(page.getByText('База ещё не подключена.', { exact: false })).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(0);
  await expect(page.getByText('Демо-режим')).toHaveCount(0);
  await expect(page.getByRole('alert')).toContainText('URL проекта');
});
