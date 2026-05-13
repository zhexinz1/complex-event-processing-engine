<template>
  <header class="card"
    style="margin:20px 24px 0; padding:16px 24px; display:flex; align-items:center; justify-content:space-between; border-radius:8px 8px 0 0; border-bottom:none;">
    <div style="display:flex; align-items:center; gap:16px;">
      <div style="width:40px; height:40px; display:flex; align-items:center; justify-content:center; overflow:hidden;">
        <img src="../logo.png" alt="Logo" style="width:100%; height:100%; object-fit:contain;" />
      </div>
      <div>
        <h1 style="font-size:18px; font-weight:700; color:var(--text-main); margin:0;">目标仓位配置</h1>
        <div style="font-size:13px; color:var(--text-muted); margin-top:2px;">Target Allocation Management</div>
      </div>
    </div>
    <div style="display:flex; align-items:center; gap:24px;">
      <div style="display:flex; gap:12px;">
        <router-link to="/products" class="btn btn-default" style="font-size:13px; padding:6px 12px; text-decoration:none; display:flex; align-items:center;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
            <line x1="12" y1="22.08" x2="12" y2="12"></line>
          </svg>
          产品配置
        </router-link>
        <button class="btn btn-default" @click="$emit('open-assets')" style="font-size:13px; padding:6px 12px; display:flex; align-items:center;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M12 1v6m0 6v6m5.2-13.2l-4.2 4.2m0 6l-4.2 4.2m13.2-5.2h-6m-6 0H1m13.2 5.2l-4.2-4.2m0-6l-4.2-4.2">
            </path>
          </svg>
          目标资产库
        </button>
      </div>
      <div style="text-align:right;">
        <div style="font-size:13px; font-weight:500; color:var(--text-main);">{{ currentTime }}</div>
        <div
          style="display:flex; align-items:center; gap:6px; font-size:12px; margin-top:2px; justify-content:flex-end;">
          <div
            :style="{ width:'8px', height:'8px', borderRadius:'50%', backgroundColor: dbOk ? 'var(--success)' : 'var(--danger)' }">
          </div>
          <span :style="{ color: 'var(--text-muted)' }">{{ dbOk ? '数据库已连接' : '失去连接' }}</span>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  currentTime: string;
  dbOk: boolean;
}>();

defineEmits<{
  'open-assets': [];
}>();
</script>
