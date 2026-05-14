<template>
  <div class="card" style="margin:0 24px 32px; overflow:hidden;">
    <div style="overflow-x:auto;">
      <table>
        <thead>
          <tr>
            <th style="width: 140px;">生效日期</th>
            <th>产品组合名称</th>
            <th style="width: 120px;">资产代码</th>
            <th style="width: 240px;">分配比例</th>
            <th style="width: 160px;">最后更新</th>
            <th style="width: 140px; text-align:right;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="6" style="text-align:center; padding:60px 0; color:var(--text-muted);">
              <svg class="animate-spin"
                style="animation: spin 1s linear infinite; display:inline-block; margin-right:8px; vertical-align:middle; width:20px; height:20px; color:var(--primary);"
                xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z">
                </path>
              </svg>
              正在加载配置数据...
            </td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="6" style="text-align:center; padding:60px 0; color:var(--text-muted);">暂无匹配的数据记录</td>
          </tr>
          <tr v-for="row in rows" :key="row.id">
            <td style="color:#4b5563;">{{ row.target_date }}</td>
            <td style="font-weight:500;">{{ row.product_name }}</td>
            <td style="font-family:'Fira Code', monospace; font-size:13px; font-weight:500;">{{ row.asset_code }}</td>
            <td>
              <div style="display:flex; align-items:center; gap:12px;">
                <div class="weight-bar-bg" style="flex:1;">
                  <div class="weight-bar-fill" :style="weightBarStyle(row.weight_ratio)"></div>
                </div>
                <span style="font-size:13px; font-weight:600; min-width:56px; text-align:right; color:var(--text-main);">
                  {{ (row.weight_ratio * 100).toFixed(2) }}%
                </span>
              </div>
            </td>
            <td style="font-size:13px; color:var(--text-muted);">{{ row.updated_at ? row.updated_at.slice(0,16) : '-' }}</td>
            <td style="text-align:right;">
              <button class="btn btn-text" @click="$emit('edit', row)">编辑</button>
              <button class="btn btn-danger-text" @click="$emit('delete', row)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AllocationRow } from '../types';
import { weightBarStyle } from '../utils';

defineProps<{
  rows: AllocationRow[];
  loading: boolean;
}>();

defineEmits<{
  edit: [row: AllocationRow];
  delete: [row: AllocationRow];
}>();
</script>
