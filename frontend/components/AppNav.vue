<template>
  <nav class="card"
    style="margin:0 24px; padding:0 24px; border-radius:0; display:flex; gap:0; border-bottom:none; overflow-x:auto;">
    <router-link v-for="tab in tabs" :key="tab.to" :to="tab.to" class="tab-btn"
      :class="{ active: route.path === tab.to }">
      {{ tab.label }}
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';

const route = useRoute();

const tabs = [
  { to: '/', label: '目标仓位配置' },
  { to: '/fund-inflow', label: '净入金录入' },
  { to: '/order-confirm', label: '订单确认' },
  { to: '/order-list', label: '订单列表' },
  { to: '/health', label: '行情健康检查' },
  { to: '/signals', label: '信号与回测' },
];
</script>

<style scoped>
.tab-btn {
  text-decoration: none;
  white-space: nowrap;
}
</style>
