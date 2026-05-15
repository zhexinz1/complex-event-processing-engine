<template>
  <div style="max-width:1200px; margin:0 auto; padding:24px;">
    <!-- View 1: Batch List -->
    <div v-if="!batchId" class="card" style="padding:32px;">
      <h2 style="font-size:22px; font-weight:700; margin-bottom:8px;">订单确认</h2>
      <p style="color:var(--text-muted); margin-bottom:20px;">选择一个批次查看详情并确认执行</p>

      <div v-if="batchLoading" style="text-align:center; padding:40px; color:var(--text-muted);">正在加载批次列表...</div>
      <div v-else-if="batches.length === 0" style="text-align:center; padding:40px; color:var(--text-muted);">
        <p>暂无净入金记录。</p>
        <router-link to="/fund-inflow" style="color:var(--primary); margin-top:12px; display:inline-block;">→ 去录入净入金</router-link>
      </div>
      <table v-else>
        <thead>
          <tr><th>批次ID</th><th>产品</th><th>净入金（元）</th><th>杠杆后金额</th><th>录入人</th><th>录入时间</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="inf in batches" :key="inf.batch_id" class="batch-row" @click="goToBatch(inf.batch_id)">
            <td style="font-family:monospace; font-size:12px; color:var(--text-muted);">{{ inf.batch_id.substring(0,8) }}...</td>
            <td><strong>{{ inf.product_name }}</strong></td>
            <td style="font-weight:600;">{{ fmtNum(inf.net_inflow) }}</td>
            <td style="font-weight:600;">{{ fmtNum(inf.leveraged_amount) }}</td>
            <td>{{ inf.input_by || '—' }}</td>
            <td><small>{{ fmtTime(inf.input_at) }}</small></td>
            <td><span :class="['status-badge', 'status-' + inf.status]">{{ statusLabel(inf.status) }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- View 2: Batch Detail -->
    <div v-else class="card" style="padding:32px;">
      <router-link to="/order-confirm" style="color:var(--primary); text-decoration:none; font-size:14px;">← 返回批次列表</router-link>
      <h2 style="font-size:22px; font-weight:700; margin:12px 0;">订单确认</h2>

      <div v-if="alertMsg" :class="['alert-box', alertType]" style="margin-bottom:16px;">{{ alertMsg }}</div>

      <div v-if="detailLoading" style="text-align:center; padding:40px; color:var(--text-muted);">正在加载订单数据...</div>

      <div v-else-if="batchInfo">
        <div class="info-panel" style="margin-bottom:20px;">
          <p><strong>批次ID:</strong> {{ batchInfo.batch_id }}</p>
          <p><strong>产品名称:</strong> {{ batchInfo.product_name }}</p>
          <p><strong>净入金:</strong> {{ fmtNum(batchInfo.net_inflow) }} 元</p>
          <p><strong>杠杆倍数:</strong> {{ batchInfo.leverage_ratio }}</p>
          <p><strong>杠杆后金额:</strong> {{ fmtNum(batchInfo.leveraged_amount) }} 元</p>
          <p><strong>录入人:</strong> {{ batchInfo.input_by || '-' }}</p>
          <p><strong>录入时间:</strong> {{ batchInfo.input_at || '-' }}</p>
        </div>

        <!-- Price Type Selector -->
        <div v-if="batchInfo.status !== 'confirmed'" class="price-type-bar">
          <label style="font-weight:600; color:#1e40af; font-size:14px;">下单方式：</label>
          <div class="price-type-options">
            <label v-for="pt in priceTypes" :key="pt.value" :class="{ active: priceType === pt.value }" @click="priceType = pt.value">
              {{ pt.label }}
            </label>
          </div>
          <span style="font-size:12px; color:var(--text-muted); margin-left:auto; font-style:italic;">{{ priceTypeHint }}</span>
        </div>

        <!-- Confirmed orders table (read-only) -->
        <table v-if="batchInfo.status === 'confirmed'">
          <thead>
            <tr>
              <th>资产代码</th><th>订单类型</th><th>方向</th><th>数量(股/手)</th><th>价格</th>
              <th>目标市值</th><th>迅投指令ID</th><th>迅投状态</th><th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id">
              <td><strong>{{ order.asset_code }}</strong></td>
              <td>{{ renderPriceType(order.order_price_type) }}</td>
              <td>
                <span class="dir-badge" :class="dirBadgeClass(order.direction)">
                  {{ dirLabel(order.direction) }}
                </span>
              </td>
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
              <td><small>{{ order.created_at ? order.created_at.replace('T', ' ') : '—' }}</small></td>
            </tr>
          </tbody>
        </table>

        <!-- Pending orders table (editable) -->
        <table v-else>
          <thead>
            <tr>
              <th>资产代码</th><th>目标市值（元）</th><th>实时价格</th>
              <th>合约乘数</th><th>理论股数/手数</th><th>四舍五入</th>
              <th>待调余量
                <span style="font-size:10px; color:#9ca3af; font-weight:400;">（可编辑上次余量）</span>
              </th>
              <th>开/平方向</th><th>最终股数/手数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id">
              <td>
                <strong>{{ order.asset_code }}</strong>
                <!-- 备注：点击展开公式 -->
                <div style="margin-top:4px;">
                  <span class="formula-toggle" @click="toggleFormula(order.id)"
                    :title="showFormula[order.id] ? '隐藏计算备注' : '查看计算备注'">
                    {{ showFormula[order.id] ? '▲ 隐藏备注' : '▼ 查看备注' }}
                  </span>
                </div>
                <div v-if="showFormula[order.id]" class="formula-box">
                  <div class="formula-title">📐 计算公式</div>
                  <div class="formula-line">理论 = 目标市值 ÷ (价格 × 乘数) + 上次余量</div>
                  <div class="formula-line formula-calc">
                    = {{ fmtNum(order.target_market_value) }} ÷ ({{ calcPrice(order).toFixed(2) }} × {{ isFuturesOrder(order) ? order.contract_multiplier : 1 }})
                    + {{ editableFractionals[order.id] !== undefined ? editableFractionals[order.id].toFixed(6) : parseFloat(order.previous_fractional).toFixed(6) }}
                  </div>
                  <div class="formula-line formula-result">
                    = {{ calcBaseLots(order).toFixed(6) }} + {{ (editableFractionals[order.id] !== undefined ? editableFractionals[order.id] : parseFloat(order.previous_fractional)).toFixed(6) }}
                    = <strong>{{ calcTheory(order).toFixed(6) }}</strong>
                  </div>
                </div>
              </td>
              <td>{{ fmtNum(order.target_market_value) }}</td>
              <td>
                <div v-if="priceType === 'limit'">
                  <input type="number" class="inp" style="width:90px; text-align:center; font-family:monospace; font-weight:700;"
                    v-model.number="order.user_limit_price" step="0.01" />
                </div>
                <div v-else style="font-family:monospace; font-weight:700; font-size:15px;" :style="{ color: priceColor(order) }">
                  {{ parseFloat(order.price).toFixed(2) }}
                </div>
                <div v-if="livePrices[order.asset_code]" style="font-size:11px; color:var(--text-muted); margin-top: 4px;">
                  <span style="color:#dc2626; cursor:pointer;" title="点击填入买1价"
                    @click="priceType === 'limit' && (order.user_limit_price = livePrices[order.asset_code].bid1)">
                    买1: {{ livePrices[order.asset_code].bid1 > 0 ? livePrices[order.asset_code].bid1.toFixed(2) : '—' }}
                  </span> /
                  <span style="color:#059669; cursor:pointer;" title="点击填入卖1价"
                    @click="priceType === 'limit' && (order.user_limit_price = livePrices[order.asset_code].ask1)">
                    卖1: {{ livePrices[order.asset_code].ask1 > 0 ? livePrices[order.asset_code].ask1.toFixed(2) : '—' }}
                  </span>
                </div>
              </td>
              <td>{{ isFuturesOrder(order) ? order.contract_multiplier : '-' }}</td>
              <!-- 理论股数/手数：已含上次待调余量 -->
              <td style="font-family:monospace; font-weight:600; color:#1d4ed8;">
                {{ calcTheory(order).toFixed(6) }}
              </td>
              <td>{{ Math.round(calcTheory(order)) }}</td>
              <!-- 待调余量列：只读展示上次余量，可编辑影响理论计算，修改余量请前往净入金录入页 -->
              <td>
                <div style="font-size:11px; color:#6b7280; margin-bottom:3px;">上次余量</div>
                <input type="number" class="inp frac-inp"
                  :value="editableFractionals[order.id] !== undefined ? editableFractionals[order.id] : parseFloat(order.previous_fractional)"
                  @input="onFractionalInput(order, $event)"
                  step="0.000001" />
                <div style="font-size:10px; color:#9ca3af; margin-top:3px;">
                  本次余量: {{ (calcTheory(order) - Math.round(calcTheory(order))).toFixed(6) }}
                </div>
                <div style="font-size:10px; color:#bfdbfe; margin-top:2px;">如需持久修改请至「净入金录入」页</div>
              </td>
              <td>
                <select class="inp dir-select" v-model="orderDirections[order.id]"
                  :class="dirSelectClass(orderDirections[order.id])">
                  <template v-if="isFuturesOrder(order)">
                    <option value="open_long">开多</option>
                    <option value="close_long">平多</option>
                    <option value="open_short">开空</option>
                    <option value="close_short">平空</option>
                  </template>
                  <template v-else>
                    <option value="buy">买入</option>
                    <option value="sell">卖出</option>
                  </template>
                </select>
              </td>
              <td>
                <input type="number" class="inp" style="width:80px; text-align:center;"
                  v-model.number="order.final_quantity" min="0" step="1" />
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="batchInfo.status !== 'confirmed'" style="display:flex; gap:16px; justify-content:center; margin-top:24px;">
          <button class="btn btn-primary" :disabled="confirming" @click="confirmAll">
            {{ confirming ? '正在执行...' : '确认并执行订单' }}
          </button>
          <button class="btn btn-default" @click="$router.push('/order-confirm')">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, watch, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { CepApi } from '../api';
import type { FundInflow, PendingOrder, RealtimePrice } from '../types';

const route = useRoute();
const router = useRouter();

const batchId = computed(() => (route.query.batch_id as string) || '');
const batches = ref<FundInflow[]>([]);
const batchLoading = ref(true);
const detailLoading = ref(true);
const batchInfo = ref<any>(null);
const orders = ref<PendingOrder[]>([]);
const livePrices = ref<Record<string, RealtimePrice>>({});
const priceType = ref('limit');
const confirming = ref(false);
const alertMsg = ref('');
const alertType = ref<'success' | 'error'>('success');
// per-order direction: { order_id -> direction_str }
const orderDirections = ref<Record<number, string>>({});
// 可编辑的上次待调余量：key=order.id, value=用户编辑后的数值
const editableFractionals = ref<Record<number, number>>({});
// 控制每行备注展开/收起
const showFormula = ref<Record<number, boolean>>({});
let priceTimer: ReturnType<typeof setInterval> | null = null;

/**
 * 判断是否为期货合约。
 * 股票代码带 .SH / .SZ 后缀，其余（纯代码如 TA609 或带期货交易所后缀如 TA609.CZCE）均视为期货。
 */
function isFuturesCode(assetCode: string): boolean {
  const upper = assetCode.toUpperCase();
  if (upper.endsWith('.SH') || upper.endsWith('.SZ')) return false;
  return true; // 无后缀或带期货交易所后缀，均为期货
}

function isFuturesOrder(order: any): boolean {
  return isFuturesCode(order.asset_code);
}

const DIR_LABELS: Record<string, string> = {
  open_long: '开多', close_long: '平多', open_short: '开空', close_short: '平空',
  buy: '买入', sell: '卖出',
};
function dirLabel(dir: string | undefined): string {
  return DIR_LABELS[dir || ''] || dir || '—';
}
function dirBadgeClass(dir: string | undefined): string {
  if (!dir) return 'dir-gray';
  if (dir === 'open_long' || dir === 'buy') return 'dir-green';
  if (dir === 'open_short') return 'dir-orange';
  return 'dir-red';
}
function dirSelectClass(dir: string | undefined): string {
  if (!dir) return '';
  if (dir === 'open_long' || dir === 'buy') return 'dir-sel-green';
  if (dir === 'open_short') return 'dir-sel-orange';
  return 'dir-sel-red';
}

const priceTypes = [
  { value: 'limit', label: '限价' },
  { value: 'market', label: '市价' },
  { value: 'best', label: '最优价' },
  { value: 'twap', label: 'TWAP' },
  { value: 'vwap', label: 'VWAP' },
];
const priceTypeHints: Record<string, string> = {
  limit: '限价: 以当前最新价挂单',
  market: '市价: 以当前对手价立即成交',
  best: '最优价: 以最优对手价挂单',
  twap: 'TWAP: 30分钟内按时间均匀拆单执行',
  vwap: 'VWAP: 30分钟内按成交量分布拆单执行',
};
const priceTypeHint = computed(() => priceTypeHints[priceType.value] || '');
const priceTypeLabels: Record<string, string> = { limit: '限价', market: '市价', best: '最优价', twap: 'TWAP', vwap: 'VWAP' };

function fmtNum(val: string | number) {
  return parseFloat(String(val)).toLocaleString('zh-CN', { minimumFractionDigits: 2 });
}
function fmtTime(val: string) {
  return val ? new Date(val).toLocaleString('zh-CN') : '—';
}
function statusLabel(s: string) {
  return { pending: '待确认', confirmed: '已确认', cancelled: '已取消' }[s] || s;
}
/** 获取当前使用的价格（限价时用用户输入价，其他用行情价）*/
function calcPrice(order: any): number {
  return (priceType.value === 'limit' && order.user_limit_price)
    ? parseFloat(order.user_limit_price)
    : parseFloat(order.price);
}
/** 仅基于目标市值的基础手数（不含上次余量），用于公式展示 */
function calcBaseLots(order: any): number {
  const p = calcPrice(order);
  const tmv = parseFloat(order.target_market_value);
  const m = parseInt(order.contract_multiplier) || 1;
  return p > 0 ? tmv / (p * m) : 0;
}
/** 理论股数/手数 = 基础手数 + 上次待调余量（含用户覆盖值）*/
function calcTheory(order: any): number {
  const base = calcBaseLots(order);
  const prevFrac = editableFractionals.value[order.id] !== undefined
    ? editableFractionals.value[order.id]
    : parseFloat(order.previous_fractional || '0');
  return base + prevFrac;
}
function toggleFormula(orderId: number) {
  showFormula.value[orderId] = !showFormula.value[orderId];
}
function onFractionalInput(order: any, event: Event) {
  const val = parseFloat((event.target as HTMLInputElement).value);
  if (!isNaN(val)) {
    editableFractionals.value[order.id] = val;
  }
}
function resetFractional(order: any) {
  editableFractionals.value[order.id] = parseFloat(order.previous_fractional || '0');
}
function priceColor(order: any) {
  const live = livePrices.value[order.asset_code];
  if (!live) return '#059669';
  const p = priceType.value === 'limit' && order.user_limit_price ? parseFloat(order.user_limit_price) : parseFloat(order.price);
  return live.last_price > p ? '#059669' : '#dc2626';
}
function goToBatch(id: string) {
  router.push({ path: '/order-confirm', query: { batch_id: id } });
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

async function loadBatchList() {
  batchLoading.value = true;
  try {
    const data = await CepApi.fetchFundInflows();
    if (data.success) batches.value = data.inflows || [];
  } catch { /* silent */ }
  batchLoading.value = false;
}

async function loadDetail() {
  detailLoading.value = true;
  try {
    const data = await CepApi.fetchPendingOrders(batchId.value);
    if (data.success) {
      batchInfo.value = data;
      const dirs: Record<number, string> = {};
      const fracs: Record<number, number> = {};
      for (const o of data.orders) {
        o.user_limit_price = parseFloat(o.price);
        // 默认方向: 期货→开多, 股票→买入
        dirs[o.id] = isFuturesCode(o.asset_code) ? 'open_long' : 'buy';
        // 初始化可编辑余量 = 上次余量（来自数据库，已随订单一起返回）
        fracs[o.id] = parseFloat(o.previous_fractional || '0');
      }
      orderDirections.value = dirs;
      editableFractionals.value = fracs;
      showFormula.value = {};
      orders.value = data.orders;
      if (data.status !== 'confirmed') startPricePolling();
    }
  } catch (e: any) {
    alertMsg.value = '加载失败: ' + e.message;
    alertType.value = 'error';
  }
  detailLoading.value = false;
}

function startPricePolling() {
  fetchPrices();
  priceTimer = setInterval(fetchPrices, 1000);
}

async function fetchPrices() {
  const symbols = orders.value.map(o => o.asset_code).join(',');
  if (!symbols) return;
  try {
    const data = await CepApi.fetchRealtimePrices(symbols);
    if (data.success && data.prices) {
      livePrices.value = data.prices;
      for (const order of orders.value) {
        const lp = data.prices[order.asset_code];
        if (lp) order.price = String(lp.last_price);
      }
    }
  } catch { /* silent */ }
}

async function confirmAll() {
  if (!confirm(`确定以「${priceTypeLabels[priceType.value]}」方式执行所有订单？`)) return;
  confirming.value = true;
  if (priceTimer) { clearInterval(priceTimer); priceTimer = null; }

  try {
    for (const order of orders.value) {
      const priceToSave = priceType.value === 'limit' && order.user_limit_price ? order.user_limit_price : parseFloat(order.price);
      await CepApi.updateOrder(order.id, order.final_quantity, priceToSave);
    }
    // 构建 order_directions: { "order_id": "direction" }
    const dirsPayload: Record<string, string> = {};
    for (const [id, dir] of Object.entries(orderDirections.value)) {
      dirsPayload[String(id)] = dir;
    }
    const data = await CepApi.confirmOrders(batchId.value, '交易员', priceType.value, dirsPayload);
    if (data.success) {
      alertMsg.value = `订单执行成功！（${priceTypeLabels[priceType.value]}）`;
      alertType.value = 'success';
      if (batchInfo.value) batchInfo.value.status = 'confirmed';
      // reload to get direction field from DB
      await loadDetail();
      confirming.value = false;
    } else {
      alertMsg.value = '订单执行失败: ' + (data.message || '');
      alertType.value = 'error';
      confirming.value = false;
      startPricePolling();
    }
  } catch (e: any) {
    alertMsg.value = '网络错误: ' + e.message;
    alertType.value = 'error';
    confirming.value = false;
    startPricePolling();
  }
}

watch(batchId, (val) => {
  if (priceTimer) { clearInterval(priceTimer); priceTimer = null; }
  if (val) loadDetail(); else loadBatchList();
}, { immediate: true });

onUnmounted(() => { if (priceTimer) clearInterval(priceTimer); });
</script>

<style scoped>
/* 待调余量输入框 */
.frac-inp { width: 100px; font-family: monospace; font-size: 12px; padding: 3px 6px; }
.frac-btn { border: none; border-radius: 4px; font-size: 11px; padding: 2px 6px; cursor: pointer; }
.frac-btn-reset { background: #f3f4f6; color: #6b7280; }
.frac-btn-reset:hover { background: #e5e7eb; }
.frac-btn-save { background: #dbeafe; color: #1d4ed8; }
.frac-btn-save:hover { background: #bfdbfe; }
.frac-btn-save:disabled { opacity: 0.5; cursor: default; }
/* 公式备注 */
.formula-toggle { font-size: 11px; color: #9333ea; cursor: pointer; user-select: none; }
.formula-toggle:hover { text-decoration: underline; }
.formula-box { background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 6px; padding: 8px 10px; margin-top: 6px; font-size: 11px; min-width: 280px; }
.formula-title { font-weight: 700; color: #7c3aed; margin-bottom: 4px; }
.formula-line { color: #4b5563; margin: 2px 0; font-family: monospace; }
.formula-calc { color: #6d28d9; }
.formula-result { color: #1d4ed8; font-weight: 600; }
.batch-row { cursor: pointer; transition: background 0.15s; }
.batch-row:hover { background: #eef2ff !important; }
.info-panel { background: #f0f4ff; border-left: 4px solid var(--primary); padding: 12px 16px; border-radius: 4px; }
.info-panel p { margin: 4px 0; font-size: 14px; color: var(--text-main); }
.alert-box { padding: 12px 16px; border-radius: 6px; font-size: 14px; }
.alert-box.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
.alert-box.error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.status-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; }
.status-pending { background: #fff3cd; color: #856404; }
.status-confirmed { background: #d4edda; color: #155724; }
.status-cancelled { background: #e2e3e5; color: #383d41; }
.st-green { background: #d4edda; color: #155724; }
.st-blue { background: #dbeafe; color: #1d4ed8; }
.st-yellow { background: #fef3c7; color: #92400e; }
.st-red { background: #fee2e2; color: #991b1b; }
.st-gray { background: #f3f4f6; color: #6b7280; }
.price-type-bar { background: #f0f4ff; border: 1px solid #dbe4ff; border-radius: 8px; padding: 14px 20px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.price-type-options { display: flex; gap: 6px; }
.price-type-options label { padding: 8px 18px; border-radius: 20px; font-size: 13px; font-weight: 500; cursor: pointer; border: 2px solid #dbe4ff; color: #1e40af; background: white; transition: all 0.15s; }
.price-type-options label.active { background: #2563eb; color: white; border-color: transparent; }
.price-type-options label:hover { border-color: #93a8f5; }
/* direction selector styles */
.dir-select { font-weight: 600; border-radius: 8px; padding: 4px 8px; }
.dir-sel-green { background: #dcfce7; color: #15803d; border-color: #86efac; }
.dir-sel-red   { background: #fee2e2; color: #b91c1c; border-color: #fca5a5; }
.dir-sel-orange{ background: #fff7ed; color: #c2410c; border-color: #fdba74; }
/* direction badge for confirmed view */
.dir-badge { display: inline-block; padding: 3px 10px; border-radius: 10px; font-size: 12px; font-weight: 600; }
.dir-green  { background: #dcfce7; color: #15803d; }
.dir-red    { background: #fee2e2; color: #b91c1c; }
.dir-orange { background: #fff7ed; color: #c2410c; }
.dir-gray   { background: #f3f4f6; color: #6b7280; }
</style>
