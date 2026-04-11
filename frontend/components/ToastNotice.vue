<template>
  <transition name="fade">
    <div class="toast" :class="toast.type === 'success' ? 'toast-success' : 'toast-error'" v-if="toast.show">
      <svg v-if="toast.type === 'success'" width="18" height="18" viewBox="0 0 24 24" fill="none"
        stroke="var(--success)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>
      <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="15" y1="9" x2="9" y2="15"></line>
        <line x1="9" y1="9" x2="15" y2="15"></line>
      </svg>
      {{ toast.message }}
    </div>
  </transition>
</template>

<script setup lang="ts">
import type { ToastType } from '../types';

defineProps<{
  toast: {
    show: boolean;
    message: string;
    type: ToastType;
  };
}>();
</script>
