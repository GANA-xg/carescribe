import { defineConfig, devices } from '@playwright/test';

const FRONTEND = process.env.E2E_FRONTEND_URL ?? 'http://localhost:3000';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: FRONTEND,
    trace: 'on-first-retry',
    viewport: { width: 375, height: 812 }, // mobile first
  },
  projects: [
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 7'] },
    },
  ],
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : {
        command: 'npm run dev',
        url: FRONTEND,
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
