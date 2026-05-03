import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'allocations',
      component: () => import('./views/AllocationsView.vue'),
    },
    {
      path: '/fund-inflow',
      name: 'fund-inflow',
      component: () => import('./views/FundInflowView.vue'),
    },
    {
      path: '/order-confirm',
      name: 'order-confirm',
      component: () => import('./views/OrderConfirmView.vue'),
    },
    {
      path: '/order-list',
      name: 'order-list',
      component: () => import('./views/OrderListView.vue'),
    },
    {
      path: '/health',
      name: 'health',
      component: () => import('./views/MarketHealthView.vue'),
    },
    {
      path: '/backtest',
      name: 'backtest',
      component: () => import('./views/BacktestView.vue'),
    },
    {
      path: '/signals',
      name: 'signals',
      component: () => import('./views/SignalsView.vue'),
    },
    {
      path: '/signals/ctx-guide',
      name: 'signal-ctx-guide',
      component: () => import('./views/SignalCtxGuideView.vue'),
    },
  ],
});

export default router;
