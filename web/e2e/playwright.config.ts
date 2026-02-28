import { defineConfig, devices } from '@playwright/test'

const BASE_PORT = 8001

export default defineConfig({
  testDir: './suites',
  timeout: 60_000,
  retries: 2,
  workers: 4,
  fullyParallel: true,

  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },

  reporter: [
    ['html', { outputFolder: './reports', open: 'never' }],
    ['json', { outputFile: './reports/results.json' }],
    ['list'],
  ],

  use: {
    baseURL: `http://127.0.0.1:${BASE_PORT}`,
    colorScheme: 'dark',
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
    video: 'on-first-retry',
    actionTimeout: 10_000,
    viewport: { width: 1280, height: 720 },
  },

  projects: [
    {
      name: 'scan-workflows',
      testDir: './suites/scan',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${BASE_PORT}`,
      },
    },
    {
      name: 'debate-workflows',
      testDir: './suites/debate',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${BASE_PORT + 1}`,
      },
    },
    {
      name: 'navigation',
      testDir: './suites/navigation',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${BASE_PORT + 2}`,
      },
    },
    {
      name: 'edge-cases',
      testDir: './suites/edge',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${BASE_PORT + 3}`,
      },
    },
    {
      name: 'watchlist-workflows',
      testDir: './suites/watchlist',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${BASE_PORT + 4}`,
      },
    },
    {
      name: 'score-history',
      testDir: './suites/score-history',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: `http://127.0.0.1:${BASE_PORT + 5}`,
      },
    },
  ],

  webServer: Array.from({ length: 6 }, (_, i) => ({
    command: `uv run uvicorn options_arena.api:create_app --factory --port ${BASE_PORT + i} --host 127.0.0.1`,
    port: BASE_PORT + i,
    reuseExistingServer: !process.env.CI,
    env: { ARENA_DATA__DB_PATH: `.e2e-test-${i + 1}.db` },
    timeout: 30_000,
    cwd: '../../',
  })),
})
