import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:5179', trace: 'retain-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {},
  },
  projects: [
    { name: 'dashboard', testMatch: '**/dashboard.spec.ts' },
    { name: 'auth', testMatch: '**/auth.spec.ts', use: { baseURL: 'http://127.0.0.1:5179' } },
    { name: 'setup', testMatch: '**/setup.spec.ts', use: { baseURL: 'http://127.0.0.1:5181' } },
    { name: 'install', testMatch: '**/install.spec.ts' },
    { name: 'observability', testMatch: '**/observability.spec.ts' },
  ],
  webServer: [
    { command: 'npm run dev -- --port 5179 --strictPort', url: 'http://127.0.0.1:5179', reuseExistingServer: !process.env.CI, env: { VITE_SUPABASE_URL: 'https://dashboard-test.supabase.co', VITE_SUPABASE_ANON_KEY: 'test-public-key' } },
    // An old opt-in flag must no longer enable fake data or bypass authentication.
    { command: 'npm run dev -- --port 5181 --strictPort', url: 'http://127.0.0.1:5181', reuseExistingServer: !process.env.CI, env: { VITE_SUPABASE_URL: '', VITE_SUPABASE_ANON_KEY: '', VITE_DEMO_MODE: 'true' } },
  ],
});
