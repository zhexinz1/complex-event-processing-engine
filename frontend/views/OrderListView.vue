<template>
  <div style="max-width:1400px; margin:0 auto; padding:24px;">
    <!-- Header -->
    <div class="card" style="padding:16px 20px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
      <h2 style="font-size:20px; font-weight:700;">订单列表</h2>
      <div style="display:flex; gap:10px;">
        <button class="btn btn-default" @click="refreshOrders">刷新</button>
      </div>
    </div>

    <div class="card" style="padding:20px;">
      <div v-if="alertMsg" :class="['alert-box', alertType]" style="margin-bottom:16px;">{{ alertMsg }}</div>

      <!-- Reconciliation panel -->
      <div class="reconcile-panel">
        <h3 style="font-size:14px; font-weight:600; margin-bottom:8px;">对账</h3>
        <div style="display:flex; gap:12px; align-items:end; flex-wrap:wrap;">
          <div>
            <label style="font-size:12px; color:var(--text-muted);">产品 *</label>
            <select v-model="selectedProduct" class="inp" style="width:200px;">
              <option value="">请选择产品</option>
              <option v-for="p in products" :key="p.product_name" :value="p.product_name">{{ p.product_name }}</option>
            </select>
          </div>
          <button class="btn btn-primary" :disabled="reconciling" @click="doReconcile" style="background:#059669;">
            {{ reconciling ? '对账中...' : '对账' }}
          </button>
        </div>
        <div v-if="reconcileSummary" style="margin-top:8px; font-size:13px; color:var(--text-main);">
          对账完成！迅投指令: <strong>{{ reconcileSummary.xt_instructions_count }}</strong> 条，
          待对账: <strong>{{ reconcileSummary.pending_orders_count }}</strong> 笔，
          更新: <strong>{{ reconcileSummary.updated }}</strong>，
          一致: <strong>{{ reconcileSummary.already_ok }}</strong>，
          未找到: {{ reconcileSummary.not_found }}
        </div>
        <div style="font-size:11px; color:#9ca3af; margin-top:6px;">
          提示：订单状态正常由回调函数自动更新，此用于重启后补充与迅投之间订单对账
        </div>
      </div>

      <!-- Filter -->
      <div style="margin:16px 0;">
        <label style="font-size:12px; color:var(--text-muted);">合约代码筛选</label>
        <input v-model="assetFilter" type="text" class="inp" style="width:220px;" placeholder="输入合约代码" />
      </div>

      <!-- Loading -->
      <div v-if="loading" style="text-align:center; padding:40px; color:var(--text-muted);">加载中...</div>

      <!-- Table -->
      <div v-else>
        <div v-if="filteredOrders.length === 0" style="text-align:center; padding:40px; color:var(--text-muted);">暂无订单数据</div>
        <table v-else>
          <thead>
            <tr>
              <th>批次ID</th><th>产品</th><th>合约代码</th><th>订单类型</th><th>数量</th><th>价格</th>
              <th>目标市值</th><th>迅投指令ID</th><th>迅投状态</th><th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in filteredOrders" :key="order.id">
              <td><small>{{ order.batch_id.substring(0, 8) }}...</small></td>
              <td>{{ order.product_name }}</td>
              <td><strong>{{ order.asset_code }}</strong></td>
              <td>{{ renderPriceType(order.order_price_type) }}</td>
              <td>{{ order.final_quantity }}</td>
              <td>{{ priceDisplay(order) }}</td>
              <td>{{ fmtNum(order.target_market_value) }}</td>
              <td>
                <code v-if="order.xt_order_id">{{ order.xt_order_id }}</code>
                <span v-else style="color:#9ca3af;">—</span>
              </td>
              <td>
                <span :class="['status-badge', xtStatusClass(order)]">{{ xtStatusText(order) }}</span>
                <br v-if="order.xt_error_msg"><small v-if="order.xt_error_msg" style="color:#ef4444; font-size:11px;">{{ order.xt_error_msg }}</small>
                <br v-if="order.xt_traded_volume > 0">
                <small v-if="order.xt_traded_volume > 0" style="color:#059669; font-size:11px;">
                  成交: {{ order.xt_traded_volume }}手 @ {{ parseFloat(order.xt_traded_price || 0).toFixed(2) }}
                </small>
              </td>
              <td><small>{{ order.created_at }}</small></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { CepApi } from '../api';
import type { ProductInfo } from '../types';

const loading = ref(true);
const allOrders = ref<any[]>([]);
const products = ref<ProductInfo[]>([]);
const selectedProduct = ref('');
const reconciling = ref(false);
const reconcileSummary = ref<any>(null);
const assetFilter = ref('');
const alertMsg = ref('');
const alertType = ref<'success' | 'error'>('success');

const filteredOrders = computed(() => {
  const f = assetFilter.value.toLowerCase();
  if (!f) return allOrders.value;
  return allOrders.value.filter(o => o.asset_code.toLowerCase().includes(f));
});

function fmtNum(val: string | number) {
  return parseFloat(String(val)).toLocaleString('zh-CN', { minimumFractionDigits: 2 });
}

const statusConfig: Record<string, { cls: string; text: string }> = {
  not_sent: { cls: 'st-gray', text: '未发送' },
  send_failed: { cls: 'st-red', text: '发送失败' },
  sent: { cls: 'st-blue', text: '已发送' },
  running: { cls: 'st-blue', text: '运行中' },
  rejected: { cls: 'st-red', text: '已驳回' },
  filled: { cls: 'st-green', text: '已完成' },
  partial: { cls: 'st-yellow', text: '部分成交' },
  cancelled: { cls: 'st-gray', text: '已撤单' },
  stopped: { cls: 'st-red', text: '已停止' },
};
function xtStatusClass(order: any) { return (statusConfig[order.xt_status] || { cls: 'st-gray' }).cls; }
function xtStatusText(order: any) { return (statusConfig[order.xt_status] || { text: order.xt_status || '未发送' }).text; }

function renderPriceType(type: string) {
  return { limit: '限价', market: '市价', best: '最优价', twap: 'TWAP', vwap: 'VWAP' }[type] || type || '限价';
}
function priceDisplay(order: any) {
  const pt = order.order_price_type || 'limit';
  return (pt === 'market' || pt === 'best') ? '-1' : parseFloat(order.price).toFixed(2);
}

async function loadProducts() {
  try {
    const data = await CepApi.fetchProductList();
    if (data.success) products.value = data.products || [];
  } catch { /* silent */ }
}

async function loadOrders() {
  loading.value = true;
  try {
    const data = await CepApi.fetchAllOrders();
    if (data.success) allOrders.value = (data as any).orders || [];
  } catch (e: any) {
    alertMsg.value = '加载失败: ' + e.message;
    alertType.value = 'error';
  }
  loading.value = false;
}

function refreshOrders() {
  reconcileSummary.value = null;
  loadOrders();
}

async function doReconcile() {
  if (!selectedProduct.value) { alertMsg.value = '请先选择产品'; alertType.value = 'error'; return; }
  reconciling.value = true;
  try {
    const params = new URLSearchParams({ product_name: selectedProduct.value });
    const data: any = await CepApi.requestJson(`/api/xt/orders?${params}`);
    if (data.success) {
      reconcileSummary.value = data.reconcile_summary;
      alertMsg.value = data.message;
      alertType.value = 'success';
      await loadOrders();
    } else {
      alertMsg.value = '对账失败: ' + data.message;
      alertType.value = 'error';
    }
  } catch (e: any) {
    alertMsg.value = '对账错误: ' + e.message;
    alertType.value = 'error';
  }
  reconciling.value = false;
}

loadProducts();
loadOrders();
</script>

<style scoped>
.alert-box { padding: 12px 16px; border-radius: 6px; font-size: 14px; }
.alert-box.success { background: #d4edda; color: #155724; }
.alert-box.error { background: #fef2f2; color: #991b1b; }
.reconcile-panel { background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.status-badge { display: inline-block; padding: 3px 10px; border-radius: 10px; font-size: 12px; font-weight: 500; }
.st-green { background: #d4edda; color: #155724; }
.st-blue { background: #dbeafe; color: #1d4ed8; }
.st-yellow { background: #fef3c7; color: #92400e; }
.st-red { background: #fee2e2; color: #991b1b; }
.st-gray { background: #f3f4f6; color: #6b7280; }
</style>
