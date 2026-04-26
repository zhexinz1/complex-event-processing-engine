<template>
  <div style="max-width:800px; margin:0 auto; padding:24px;">
    <div class="card" style="padding:32px;">
      <h2 style="font-size:22px; font-weight:700; color:var(--text-main); margin-bottom:24px;">净入金录入</h2>

      <div v-if="alertMsg" :class="['alert-box', alertType]" style="margin-bottom:16px;">{{ alertMsg }}</div>

      <form @submit.prevent="handleSubmit">
        <div class="form-row">
          <label>选择产品 *</label>
          <select v-model="selectedProduct" class="inp" required>
            <option value="">-- 请选择产品 --</option>
            <option v-for="p in products" :key="p.product_name" :value="p.product_name">{{ p.product_name }}</option>
          </select>
        </div>

        <div v-if="selectedProductInfo" class="info-panel" style="margin:16px 0;">
          <p><strong>杠杆倍数:</strong> {{ selectedProductInfo.leverage_ratio }}倍</p>
          <p><strong>关联账号:</strong> {{ selectedProductInfo.account_id }}</p>
        </div>

        <div class="form-row">
          <label>净入金金额（元）*</label>
          <input v-model.number="netInflow" type="number" class="inp" step="0.01" min="0" placeholder="例如: 1000000" required />
        </div>

        <div class="form-row">
          <label>录入人</label>
          <input v-model="inputBy" type="text" class="inp" placeholder="例如: 张三" maxlength="50" />
        </div>

        <button type="submit" class="btn btn-primary" style="width:100%; margin-top:12px;" :disabled="submitting">
          {{ submitting ? '计算中...' : '计算订单' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { CepApi } from '../api';
import type { ProductInfo } from '../types';

const router = useRouter();
const products = ref<ProductInfo[]>([]);
const selectedProduct = ref('');
const netInflow = ref<number | null>(null);
const inputBy = ref('');
const submitting = ref(false);
const alertMsg = ref('');
const alertType = ref<'success' | 'error'>('success');

const selectedProductInfo = computed(() =>
  products.value.find(p => p.product_name === selectedProduct.value) || null
);

async function loadProducts() {
  try {
    const data = await CepApi.fetchProductList();
    if (data.success) products.value = data.products;
  } catch (e: any) {
    alertMsg.value = '加载产品列表失败: ' + e.message;
    alertType.value = 'error';
  }
}

async function handleSubmit() {
  if (!selectedProduct.value || !netInflow.value || netInflow.value <= 0) {
    alertMsg.value = '请填写完整信息';
    alertType.value = 'error';
    return;
  }
  submitting.value = true;
  try {
    const data = await CepApi.submitFundInflow({
      product_name: selectedProduct.value,
      net_inflow: netInflow.value,
      input_by: inputBy.value.trim(),
    });
    if (data.success) {
      alertMsg.value = '订单计算成功！正在跳转到确认页面...';
      alertType.value = 'success';
      setTimeout(() => {
        router.push({ path: '/order-confirm', query: { batch_id: data.batch_id } });
      }, 1000);
    } else {
      alertMsg.value = '计算失败: ' + (data.message || '');
      alertType.value = 'error';
      submitting.value = false;
    }
  } catch (e: any) {
    alertMsg.value = '网络错误: ' + e.message;
    alertType.value = 'error';
    submitting.value = false;
  }
}

loadProducts();
</script>

<style scoped>
.form-row { margin-bottom: 20px; }
.form-row label { display: block; margin-bottom: 6px; font-size: 14px; font-weight: 500; color: var(--text-muted); }
.info-panel { background: #f0f4ff; border-left: 4px solid var(--primary); padding: 12px 16px; border-radius: 4px; }
.info-panel p { margin: 4px 0; font-size: 14px; color: var(--text-main); }
.alert-box { padding: 12px 16px; border-radius: 6px; font-size: 14px; }
.alert-box.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.alert-box.error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
</style>
