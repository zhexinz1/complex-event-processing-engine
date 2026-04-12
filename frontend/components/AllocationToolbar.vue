<template>
  <div class="card"
    style="margin:0 24px 20px; padding:20px 24px; border-radius:0 0 8px 8px; display:flex; flex-direction:column; gap:20px;">
    <div
      style="display:grid; grid-template-columns:repeat(3, 1fr); gap:20px; padding-bottom:20px; border-bottom:1px solid var(--border);">
      <div class="stat-block">
        <span class="stat-label">总记录数</span>
        <span class="stat-value">{{ rowCount }}</span>
      </div>
      <div class="stat-block">
        <span class="stat-label">涉及产品数量</span>
        <span class="stat-value" style="color:var(--primary);">{{ productCount }}</span>
      </div>
      <div class="stat-block">
        <span class="stat-label">最新交易日配置</span>
        <span class="stat-value" style="color:#4b5563;">{{ latestDate || '暂无数据' }}</span>
      </div>
    </div>

    <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px;">
      <div style="display:flex; align-items:center; gap:12px;">
        <div style="position:relative;">
          <input type="date" :value="filterDate" class="inp" title="按日期筛选" style="width:180px;"
            @input="$emit('update:filterDate', ($event.target as HTMLInputElement).value)" />
        </div>
        <div style="position:relative;">
          <select :value="filterProduct" class="inp" style="width:200px;"
            @change="$emit('update:filterProduct', ($event.target as HTMLSelectElement).value)">
            <option value="">所有产品组合</option>
            <option v-for="p in products" :key="p" :value="p">{{ p }}</option>
          </select>
        </div>
        <button class="btn btn-default" @click="$emit('refresh')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;">
            <polyline points="23 4 23 10 17 10"></polyline>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
          </svg>
          刷新数据
        </button>
      </div>
      <button class="btn btn-primary" @click="$emit('add')">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;">
          <line x1="12" y1="5" x2="12" y2="19"></line>
          <line x1="5" y1="12" x2="19" y2="12"></line>
        </svg>
        添加新配置
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  rowCount: number;
  productCount: number;
  latestDate: string | null;
  products: string[];
  filterDate: string;
  filterProduct: string;
}>();

defineEmits<{
  'update:filterDate': [value: string];
  'update:filterProduct': [value: string];
  refresh: [];
  add: [];
}>();
</script>
