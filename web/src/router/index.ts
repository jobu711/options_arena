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
    path: '/universe',
    name: 'universe',
    component: () => import('../pages/UniversePage.vue'),
  },
  {
    path: '/health',
    name: 'health',
    component: () => import('../pages/HealthPage.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
