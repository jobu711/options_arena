import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'trading-desk',
    component: () => import('../pages/TradingDeskPage.vue'),
  },
  {
    path: '/desks',
    name: 'desks',
    component: () => import('../pages/DesksPage.vue'),
  },
  {
    path: '/analytics',
    name: 'analytics',
    component: () => import('../pages/AnalyticsPage.vue'),
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('../pages/HistoryPage.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../pages/SettingsPage.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
