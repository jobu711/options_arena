import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../pages/DashboardPage.vue'),
  },
  {
    path: '/scan',
    name: 'scan',
    component: () => import('../pages/ScanPage.vue'),
  },
  {
    path: '/scan/:id',
    name: 'scan-results',
    component: () => import('../pages/ScanResultsPage.vue'),
  },
  {
    path: '/debate/:id',
    name: 'debate-result',
    component: () => import('../pages/DebateResultPage.vue'),
  },
  {
    path: '/ticker/:ticker',
    name: 'ticker-detail',
    component: () => import('../pages/TickerDetailPage.vue'),
  },
  {
    path: '/analytics',
    name: 'analytics',
    component: () => import('../pages/AnalyticsPage.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
