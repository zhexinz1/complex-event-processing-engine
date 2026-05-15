<template>
  <div style="max-width:860px; margin:0 auto; padding:24px;">
    <!-- 净入金录入卡片 -->
    <div class="card" style="padding:32px; margin-bottom:20px;">
      <h2 style="font-size:22px; font-weight:700; color:var(--text-main); margin-bottom:24px;">净入金录入</h2>

      <div v-if="alertMsg" :class="['alert-box', alertType]" style="margin-bottom:16px;">{{ alertMsg }}</div>

      <form @submit.prevent="handleSubmit">
        <div class="form-row">
          <label>选择产品 *</label>
          <select v-model="selectedProduct" class="inp" required @change="onProductChange">
            <option value="">-- 请选择产品 --</option>
            <option v-for="p in products" :key="p.product_name" :value="p.product_name">{{ p.product_name }}</option>
          </select>
        </div>

        <div v-if="selectedProductInfo" class="info-panel" style="margin:16px 0;">
          <p><strong>杠杆倍数:</strong> {{ selectedProductInfo.leverage_ratio }}倍</p>
          <p><strong>迅投用户名:</strong> {{ selectedProductInfo.xt_username }}</p>
        </div>

        <div class="form-row">
          <label>净入金/净出金金额（元）*</label>
          <input v-model.number="netInflow" type="number" class="inp" step="0.01" placeholder="入金填正数，如 1000000；出金填负数，如 -500000" required />
          <!-- 出金提示 -->
          <div v-if="netInflow !== null && netInflow < 0" class="outflow-tip">
            ⚠️ <strong>出金模式</strong>：将按各资产权重比例计算减仓订单，历史欠买余量会自动抵减卖出数量。请在执行前确认每笔订单的开/平方向。
          </div>
        </div>

        <div class="form-row">
          <label>录入人</label>
          <input v-model="inputBy" type="text" class="inp" placeholder="例如: 周哲鑫" maxlength="50" />
        </div>

        <button type="submit" class="btn btn-primary" style="width:100%; margin-top:12px;" :disabled="submitting">
          {{ submitting ? '计算中...' : '计算订单' }}
        </button>
      </form>
    </div>

    <!-- 历史待调余量管理卡片（选产品后展开） -->
    <div v-if="selectedProduct" class="card" style="padding:24px;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
        <div>
          <h3 style="font-size:17px; font-weight:700; margin:0;">历史待调余量管理</h3>
          <p style="font-size:12px; color:var(--text-muted); margin:4px 0 0;">
            本区域显示上一批次执行后遗留的余量，下次计算订单时将自动纳入。如有异常可在此手动修正后再提交净入金。
          </p>
        </div>
        <button class="btn btn-default" style="font-size:12px; padding:5px 12px;" @click="loadFractionals" :disabled="fracsLoading">
          {{ fracsLoading ? '加载中...' : '⟳ 刷新' }}
        </button>
      </div>

      <div v-if="fracsLoading" style="text-align:center; padding:20px; color:var(--text-muted);">加载中...</div>

      <div v-else-if="fractionals.length === 0" style="text-align:center; padding:20px; color:var(--text-muted); font-size:14px;">
        该产品暂无历史待调余量记录（首次入金时余量为 0）
      </div>

      <table v-else>
        <thead>
          <tr>
            <th>资产代码</th>
            <th>当前待调余量</th>
            <th>最后更新时间</th>
            <th style="width:220px;">手动修正</th>
            <th style="width:80px; text-align:center;">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in fractionals" :key="f.asset_code">
            <td><strong>{{ f.asset_code }}</strong></td>
            <td>
              <span :class="f.fractional_amount > 0 ? 'frac-pos' : f.fractional_amount < 0 ? 'frac-neg' : 'frac-zero'">
                {{ f.fractional_amount.toFixed(6) }}
              </span>
              <span style="font-size:11px; color:#9ca3af; margin-left:6px;">
                {{ f.fractional_amount > 0 ? '（欠买）' : f.fractional_amount < 0 ? '（多买）' : '（无偏差）' }}
              </span>
            </td>
            <td><small>{{ f.last_updated ? f.last_updated.replace('T', ' ').substring(0, 16) : '—' }}</small></td>
            <td>
              <input type="number" class="inp" style="width:130px; font-family:monospace; font-size:13px;"
                v-model.number="editBuffer[f.asset_code]" step="0.000001"
                :placeholder="String(f.fractional_amount)" />
            </td>
            <td style="text-align:center;">
              <button class="frac-save-btn"
                @click="saveFractional(f.asset_code)"
                :disabled="savingCode === f.asset_code">
                {{ savingCode === f.asset_code ? '…' : '💾 存库' }}
              </button>
              <button class="frac-reset-btn" @click="editBuffer[f.asset_code] = 0; saveFractional(f.asset_code)"
                :disabled="savingCode === f.asset_code" title="将余量清零">
                归零
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="fracMsg" :class="['alert-box', fracMsgType]" style="margin-top:12px;">{{ fracMsg }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
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

// 待调余量管理
const fractionals = ref<any[]>([]);
const fracsLoading = ref(false);
const editBuffer = ref<Record<string, number>>({});
const savingCode = ref<string | null>(null);
const fracMsg = ref('');
const fracMsgType = ref<'success' | 'error'>('success');

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

async function loadFractionals() {
  if (!selectedProduct.value) return;
  fracsLoading.value = true;
  fracMsg.value = '';
  try {
    const resp = await fetch(`/api/fractional-shares?product_name=${encodeURIComponent(selectedProduct.value)}`);
    const data = await resp.json();
    if (data.success) {
      fractionals.value = data.fractionals;
      // 初始化编辑缓冲区
      const buf: Record<string, number> = {};
      for (const f of data.fractionals) {
        buf[f.asset_code] = f.fractional_amount;
      }
      editBuffer.value = buf;
    }
  } catch (e: any) {
    fracMsg.value = '加载失败: ' + e.message;
    fracMsgType.value = 'error';
  }
  fracsLoading.value = false;
}

async function saveFractional(assetCode: string) {
  savingCode.value = assetCode;
  fracMsg.value = '';
  try {
    const amount = editBuffer.value[assetCode] ?? 0;
    const resp = await fetch('/api/fractional-shares', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_name: selectedProduct.value,
        asset_code: assetCode,
        fractional_amount: amount,
      }),
    });
    const data = await resp.json();
    if (data.success) {
      fracMsg.value = `✓ ${assetCode} 的待调余量已更新为 ${Number(amount).toFixed(6)}`;
      fracMsgType.value = 'success';
      // 刷新列表
      await loadFractionals();
    } else {
      fracMsg.value = '保存失败: ' + data.message;
      fracMsgType.value = 'error';
    }
  } catch (e: any) {
    fracMsg.value = '网络错误: ' + e.message;
    fracMsgType.value = 'error';
  }
  savingCode.value = null;
}

function onProductChange() {
  fractionals.value = [];
  editBuffer.value = {};
  fracMsg.value = '';
  loadFractionals();
}

async function handleSubmit() {
  if (!selectedProduct.value || netInflow.value === null || netInflow.value === undefined || netInflow.value === 0) {
    alertMsg.value = '请填写完整信息（金额不能为零）';
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

/* 余量颜色 */
.frac-pos  { font-family: monospace; font-weight: 600; color: #059669; }
.frac-neg  { font-family: monospace; font-weight: 600; color: #dc2626; }
.frac-zero { font-family: monospace; color: #9ca3af; }

/* 操作按钮 */
.frac-save-btn {
  background: #dbeafe; color: #1d4ed8; border: none; border-radius: 4px;
  font-size: 12px; padding: 3px 8px; cursor: pointer; margin-bottom: 4px;
}
.frac-save-btn:hover { background: #bfdbfe; }
.frac-save-btn:disabled { opacity: 0.5; cursor: default; }
.frac-reset-btn {
  background: #f3f4f6; color: #6b7280; border: none; border-radius: 4px;
  font-size: 12px; padding: 3px 8px; cursor: pointer; display: block; margin-top: 2px;
}
.frac-reset-btn:hover { background: #e5e7eb; }
.frac-reset-btn:disabled { opacity: 0.5; cursor: default; }
.outflow-tip {
  margin-top: 8px; padding: 10px 14px; border-radius: 6px;
  background: #fff7ed; border: 1px solid #fdba74;
  color: #92400e; font-size: 13px; line-height: 1.5;
}
</style>
