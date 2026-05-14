<template>
  <transition name="fade">
    <div class="modal-overlay" v-if="show" @click.self="$emit('close')">
      <div class="modal-box">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:24px;">
          <h2 style="font-size:18px; font-weight:600; color:var(--text-main); margin:0;">
            {{ editingRow ? '修改仓位配置' : '新增仓位配置' }}
          </h2>
          <button class="btn-text" style="color:var(--text-muted); padding:4px;" @click="$emit('close')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div style="display:flex; flex-direction:column; gap:16px;">
          <div>
            <label
              style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">生效日期</label>
            <input type="date" v-model="form.target_date" class="inp" />
          </div>
          <div>
            <label
              style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">产品组合名称</label>
            <select v-model="form.product_name" class="inp">
              <option value="" disabled>请选择产品组合</option>
              <option v-for="p in products" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
          <div>
            <label
              style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">资产代码</label>
            <select v-model="form.asset_code" class="inp" :disabled="allowedAssets.length === 0">
              <option value="" disabled>{{ allowedAssets.length === 0 ? '请先在目标资产库中添加品种' : '请选择资产代码' }}</option>
              <option v-for="a in allowedAssets" :key="a.asset_code" :value="a.asset_code">{{ a.asset_code }}</option>
            </select>
            <div v-if="allowedAssets.length === 0"
              style="margin-top:6px; font-size:12px; color:var(--text-muted); display:flex; align-items:center; gap:4px;">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
                <line x1="12" y1="16" x2="12.01" y2="16"></line>
              </svg>
              请先点击右上角「目标资产库」添加可交易品种
            </div>
          </div>
          <div>
            <label
              style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">分配比例
              (%)</label>
            <div style="position:relative;">
              <input type="number" v-model="form.weight_pct" class="inp" placeholder="0.00" step="0.01" min="0"
                max="100" style="padding-right:30px;" />
              <span style="position:absolute; right:12px; top:10px; color:var(--text-muted); font-size:14px;">%</span>
            </div>
            <div v-if="totalWarning"
              style="margin-top:6px; font-size:12px; color:var(--warning); display:flex; align-items:center; gap:4px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z">
                </path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
              提醒：当前产品合计比例已达 {{ totalPct.toFixed(2) }}%
            </div>
          </div>
        </div>

        <div style="display:flex; justify-content:flex-end; gap:12px; margin-top:32px;">
          <button class="btn btn-default" @click="$emit('close')">取消本次编辑</button>
          <button class="btn btn-primary" @click="$emit('save')" :disabled="saving">
            {{ saving ? '正在提交...' : '确认保存配置' }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import type { AllocationForm, AllocationRow, Asset } from '../types';

defineProps<{
  show: boolean;
  editingRow: AllocationRow | null;
  form: AllocationForm;
  allowedAssets: Asset[];
  products: string[];
  totalWarning: boolean;
  totalPct: number;
  saving: boolean;
}>();

defineEmits<{
  close: [];
  save: [];
}>();
</script>
