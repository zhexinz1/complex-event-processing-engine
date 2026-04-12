<template>
  <transition name="fade">
    <div class="modal-overlay" v-if="show" @click.self="$emit('close')">
      <div class="modal-box">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:24px;">
          <h2 style="font-size:18px; font-weight:600; color:var(--text-main); margin:0;">
            资产代码字典库
          </h2>
          <button class="btn-text" style="color:var(--text-muted); padding:4px;" @click="$emit('close')">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div style="display:flex; gap:8px; margin-bottom:20px;">
          <input type="text" :value="newAssetCode" class="inp" placeholder="输入资产代码，如 AU2606"
            style="flex:1; text-transform:uppercase;"
            @input="$emit('update:newAssetCode', ($event.target as HTMLInputElement).value)" @keyup.enter="$emit('add')" />
          <button class="btn btn-primary" @click="$emit('add')" :disabled="addingAsset">
            {{ addingAsset ? '添加中...' : '添加' }}
          </button>
        </div>

        <div style="max-height:320px; overflow-y:auto; border:1px solid var(--border); border-radius:6px;">
          <div v-if="allowedAssets.length === 0"
            style="padding:40px 20px; text-align:center; color:var(--text-muted); font-size:14px;">
            暂无资产代码，请先添加
          </div>
          <div v-for="asset in allowedAssets" :key="asset.asset_code"
            style="display:flex; align-items:center; justify-content:space-between; padding:12px 16px; border-bottom:1px solid var(--border);">
            <div>
              <div style="font-family:'Fira Code', monospace; font-size:14px; font-weight:500; color:var(--text-main);">
                {{ asset.asset_code }}
              </div>
              <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">
                添加于 {{ asset.created_at ? asset.created_at.slice(0, 16) : '-' }}
              </div>
            </div>
            <button class="btn btn-danger-text" @click="$emit('delete', asset.asset_code)">删除</button>
          </div>
        </div>

        <div
          style="margin-top:20px; padding:12px; background:#f9fafb; border-radius:6px; font-size:12px; color:var(--text-muted);">
          <strong style="color:var(--text-main);">提示：</strong>
          只有在此字典库中的资产代码才能用于配置目标仓位。未来将接入 CTP 接口自动校验品种有效性。
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import type { Asset } from '../types';

defineProps<{
  show: boolean;
  allowedAssets: Asset[];
  newAssetCode: string;
  addingAsset: boolean;
}>();

defineEmits<{
  close: [];
  'update:newAssetCode': [value: string];
  add: [];
  delete: [assetCode: string];
}>();
</script>
