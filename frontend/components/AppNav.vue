<template>
  <nav class="card"
    style="margin:0 24px; padding:0 24px; border-radius:0; display:flex; gap:28px; border-bottom:none;">
    <button class="tab-btn" :class="{ active: modelValue === 'allocations' }"
      @click="$emit('update:modelValue', 'allocations')">
      目标仓位配置
    </button>
    <button v-if="showBacktest" class="tab-btn" :class="{ active: modelValue === 'backtest' }"
      @click="$emit('update:modelValue', 'backtest')">
      策略回测
    </button>
  </nav>
</template>

<script setup lang="ts">
import type { AppTab } from '../types';

defineProps<{
  modelValue: AppTab;
  showBacktest: boolean;
}>();

defineEmits<{
  'update:modelValue': [value: AppTab];
}>();
</script>
