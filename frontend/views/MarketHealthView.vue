<template>
  <div style="max-width:1200px; margin:0 auto; padding:24px;">
    <!-- Header -->
    <div class="card" style="padding:16px 20px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
      <h2 style="font-size:20px; font-weight:700;">行情健康检查</h2>
      <div style="display:flex; gap:12px; align-items:center;">
        <label style="font-size:13px; color:var(--text-muted); display:flex; align-items:center; gap:6px; cursor:pointer;">
          自动刷新
          <input type="checkbox" v-model="autoRefresh" style="width:16px; height:16px; cursor:pointer;" />
        </label>
        <button class="btn btn-primary" @click="checkHealth">立即刷新</button>
      </div>
    </div>

    <!-- Status Cards -->
    <div class="health-cards">
      <div :class="['card', 'h-card', overallClass]">
        <div class="h-title">总体状态</div>
        <div :class="['h-value', overallClass]">
          <span :class="['pulse', healthData?.healthy ? 'green' : 'red']" v-if="healthData"></span>
          {{ healthData ? (healthData.healthy ? '健康' : '异常') : '检查中...' }}
        </div>
        <div class="h-sub">{{ overallSub }}</div>
      </div>
      <div :class="['card', 'h-card', subscriberClass]">
        <div class="h-title">Redis 订阅线程</div>
        <div :class="['h-value', subscriberClass]">{{ healthData?.subscriber_alive ? '运行中' : '—' }}</div>
        <div class="h-sub">行情数据接收通道</div>
      </div>
      <div :class="['card', 'h-card', coverageClass]">
        <div class="h-title">行情覆盖率</div>
        <div :class="['h-value', coverageClass]">{{ coverageText }}</div>
        <div class="h-sub">缓存中共 {{ healthData?.cached_count || 0 }} 个合约</div>
      </div>
    </div>

    <!-- Missing alert -->
    <div v-if="missingSymbols.length > 0" class="missing-alert">
      <h3 style="font-size:14px; font-weight:600;">以下合约缺少行情数据</h3>
      <p>
        <span v-for="s in missingSymbols" :key="s" class="code-tag">{{ s }}</span>
      </p>
      <p style="margin-top:8px; font-size:13px; color:#7f1d1d;">请检查 Market Node 是否已订阅这些合约，或 CTP 合约代码是否正确。</p>
    </div>

    <!-- Tick table -->
    <div class="card" style="padding:20px; margin-bottom:16px;">
      <h3 style="font-size:16px; font-weight:600; margin-bottom:12px;">实时行情缓存明细</h3>
      <div v-if="loading" style="text-align:center; padding:30px; color:var(--text-muted);">加载中...</div>
      <div v-else-if="tickKeys.length === 0" style="text-align:center; padding:30px; color:var(--text-muted);">暂无行情数据。请检查 Market Node 是否已启动。</div>
      <table v-else>
        <thead>
          <tr><th>合约代码</th><th>最新价</th><th>买1价</th><th>买1量</th><th>卖1价</th><th>卖1量</th><th>成交量</th><th>行情时间</th><th>交易日</th><th>来源状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="sym in tickKeys" :key="sym">
            <td><strong>{{ sym }}</strong></td>
            <td style="font-family:monospace; font-weight:600;">{{ symbols[sym]?.last_price?.toFixed(2) }}</td>
            <td style="font-family:monospace; color:#059669;">{{ symbols[sym]?.bid1 > 0 ? symbols[sym].bid1.toFixed(2) : '—' }}</td>
            <td>{{ symbols[sym]?.bid1_vol || '—' }}</td>
            <td style="font-family:monospace; color:#dc2626;">{{ symbols[sym]?.ask1 > 0 ? symbols[sym].ask1.toFixed(2) : '—' }}</td>
            <td>{{ symbols[sym]?.ask1_vol || '—' }}</td>
            <td>{{ symbols[sym]?.volume || '—' }}</td>
            <td style="font-family:monospace; font-size:12px;">{{ symbols[sym]?.update_time || '—' }}</td>
            <td>{{ symbols[sym]?.trading_day || '—' }}</td>
            <td>
              <span v-if="expectedSymbols.includes(sym)" style="color:#059669;">已配置</span>
              <span v-else style="color:#9ca3af;">额外</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Expected symbols -->
    <div class="card" style="padding:20px;">
      <h3 style="font-size:16px; font-weight:600; margin-bottom:12px;">数据库配置的目标合约</h3>
      <div v-if="expectedSymbols.length === 0" style="color:#9ca3af;">数据库中未配置任何目标合约</div>
      <div v-else>
        <span v-for="s in expectedSymbols" :key="s"
          :style="{ display:'inline-block', margin:'4px 8px 4px 0', padding:'4px 12px', borderRadius:'16px', fontSize:'13px', fontWeight:500,
            background: symbols[s] ? '#d1fae5' : '#fee2e2', color: symbols[s] ? '#065f46' : '#991b1b' }">
          {{ symbols[s] ? '✓' : '✗' }} {{ s }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { CepApi } from '../api';

const loading = ref(true);
const autoRefresh = ref(true);
const healthData = ref<any>(null);
let timer: ReturnType<typeof setInterval> | null = null;

const symbols = computed(() => healthData.value?.symbols || {});
const tickKeys = computed(() => Object.keys(symbols.value).sort());
const expectedSymbols = computed<string[]>(() => healthData.value?.expected_symbols || []);
const missingSymbols = computed<string[]>(() => healthData.value?.missing_symbols || []);

const overallClass = computed(() => {
  if (!healthData.value) return '';
  return healthData.value.healthy ? 'ok' : 'err';
});
const overallSub = computed(() => {
  if (!healthData.value) return '—';
  if (healthData.value.healthy) return '所有合约行情正常';
  if (missingSymbols.value.length > 0) return `${missingSymbols.value.length} 个合约缺少行情`;
  if (!healthData.value.subscriber_alive) return 'Redis 订阅线程已断开';
  return '无行情数据';
});
const subscriberClass = computed(() => {
  if (!healthData.value) return '';
  return healthData.value.subscriber_alive ? 'ok' : 'err';
});
const coverageText = computed(() => {
  if (!healthData.value) return '—';
  const exp = expectedSymbols.value.length;
  const received = exp - missingSymbols.value.length;
  return `${received} / ${exp}`;
});
const coverageClass = computed(() => {
  if (!healthData.value) return '';
  if (missingSymbols.value.length === 0 && expectedSymbols.value.length > 0) return 'ok';
  if (missingSymbols.value.length > 0) return 'warn';
  return '';
});

async function checkHealth() {
  try {
    const data: any = await CepApi.fetchMarketHealth();
    if (data.success) healthData.value = data;
  } catch { /* silent */ }
  loading.value = false;
}

function startTimer() { stopTimer(); timer = setInterval(checkHealth, 3000); }
function stopTimer() { if (timer) { clearInterval(timer); timer = null; } }

watch(autoRefresh, (v) => { if (v) startTimer(); else stopTimer(); }, { immediate: true });

checkHealth();
onUnmounted(stopTimer);
</script>

<style scoped>
.health-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px; }
.h-card { padding: 20px; }
.h-title { font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 8px; }
.h-value { font-size: 28px; font-weight: 700; }
.h-value.ok { color: #059669; }
.h-value.warn { color: #d97706; }
.h-value.err { color: #dc2626; }
.h-sub { font-size: 12px; color: #9ca3af; margin-top: 4px; }
.pulse { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; animation: pulse-anim 1.5s infinite; }
.pulse.green { background: #10b981; }
.pulse.red { background: #ef4444; }
@keyframes pulse-anim { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.missing-alert { background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
.code-tag { display: inline-block; padding: 2px 8px; background: #fee2e2; color: #991b1b; border-radius: 4px; font-family: monospace; font-size: 13px; margin: 2px 4px; }
@media (max-width:768px) { .health-cards { grid-template-columns: 1fr; } }
</style>
