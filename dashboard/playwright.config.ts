import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5178', trace: 'retain-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {},
  },
  projects: [
    { name: 'demo', testMatch: '**/dashboard.spec.ts' },
    { name: 'auth', testMatch: '**/auth.spec.ts', use: { baseURL: 'http://127.0.0.1:5179' } },
  ],
  webServer: [
    { command: 'npm run dev -- --port 5178 --strictPort', url: 'http://127.0.0.1:5178', reuseExistingServer: !process.env.CI, env: { VITE_SUPABASE_URL: '', VITE_SUPABASE_ANON_KEY: '' } },
    { command: 'npm run dev -- --port 5179 --strictPort', url: 'http://127.0.0.1:5179', reuseExistingServer: !process.env.CI, env: { VITE_SUPABASE_URL: 'https://dashboard-test.supabase.co', VITE_SUPABASE_ANON_KEY: 'test-public-key' } },
  ],
});
