<template>
  <section style="margin:0 24px 32px;">
    <div class="card" style="padding:24px; border-radius:0 0 8px 8px;">
      <div style="display:flex; justify-content:space-between; gap:24px; flex-wrap:wrap;">
        <div style="max-width:640px;">
          <h2 style="font-size:18px; font-weight:700; margin:0 0 6px;">策略回测</h2>
          <p style="font-size:13px; color:var(--text-muted); line-height:1.6; margin:0;">
            选择一个预设策略，使用 mock、Tushare 或主连历史库运行事件驱动回测。
          </p>
        </div>
        <button class="btn btn-primary" @click="$emit('run')" :disabled="backtestLoading || !selectedStrategyId">
          {{ backtestLoading ? '回测运行中...' : '运行回测' }}
        </button>
      </div>

      <div class="backtest-grid">
        <div>
          <label
            style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">预设策略</label>
          <select :value="selectedStrategyId" class="inp"
            @change="$emit('update:selectedStrategyId', ($event.target as HTMLSelectElement).value)">
            <option v-for="preset in backtestPresets" :key="preset.id" :value="preset.id">
              {{ preset.name }}
            </option>
          </select>
          <div v-if="selectedPreset"
            style="margin-top:16px; padding:16px; background:#f9fafb; border:1px solid var(--border); border-radius:8px;">
            <div style="font-size:13px; color:var(--text-muted); line-height:1.6;">
              {{ selectedPreset.description }}
            </div>
            <div style="margin-top:14px; display:grid; grid-template-columns:1fr 1fr; gap:10px;">
              <div>
                <div class="stat-label">数据集</div>
                <div style="font-size:14px; font-weight:600;">{{ selectedPreset.dataset }}</div>
              </div>
              <div>
                <div class="stat-label">标的</div>
                <div style="font-size:14px; font-weight:600;">{{ formatPresetSymbols(selectedPreset) }}</div>
              </div>
              <div v-for="param in selectedPresetParameters" :key="param.label">
                <div class="stat-label">{{ param.label }}</div>
                <div style="font-size:14px; font-weight:600;">{{ param.value }}</div>
              </div>
            </div>
          </div>

          <div style="margin-top:18px; display:flex; flex-direction:column; gap:14px;">
            <div>
              <label
                style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">行情数据源</label>
              <select :value="backtestDataSource" class="inp"
                @change="$emit('update:backtestDataSource', ($event.target as HTMLSelectElement).value)">
                <option value="mock">内置 mock 数据</option>
                <option value="tushare" :disabled="!presetSupportsDataSource(selectedPreset, 'tushare')">
                  Tushare A股日线
                </option>
                <option value="adjusted_main_contract" :disabled="!presetSupportsDataSource(selectedPreset, 'adjusted_main_contract')">
                  复权主连 1 分钟库
                </option>
              </select>
            </div>

            <div v-if="backtestDataSource === 'tushare' || backtestDataSource === 'adjusted_main_contract'" style="display:flex; flex-direction:column; gap:14px;">
              <div>
                <label
                  style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">{{ backtestDataSource === 'tushare' ? '股票代码' : '主连代码' }}</label>
                <div class="stock-combobox">
                  <input type="text" :value="backtestTsCode" class="inp" placeholder="输入代码、简称或公司名"
                    style="text-transform:uppercase;"
                    @input="$emit('update:backtestTsCode', ($event.target as HTMLInputElement).value)"
                    @focus="backtestDataSource === 'tushare' && $emit('update:stockSearchOpen', stockSearchResults.length > 0)" @blur="$emit('close-stock-search')"
                    @keyup.enter="backtestDataSource === 'tushare' && $emit('search-stocks')" />
                  <div v-if="stockSearchLoading" class="stock-combobox-status">搜索中...</div>
                  <div v-if="backtestDataSource === 'tushare' && stockSearchOpen" class="stock-combobox-menu">
                    <button v-for="stock in stockSearchResults" :key="stock.ts_code" type="button"
                      class="stock-combobox-option" @mousedown.prevent="$emit('select-stock', stock)">
                      <span class="stock-combobox-row">
                        <span class="stock-combobox-title">{{ stock.ts_code }} · {{ stock.name }}</span>
                        <span class="stock-combobox-meta">{{ stock.exchange }} {{ stock.board }}</span>
                      </span>
                      <span class="stock-combobox-detail">
                        {{ stock.industry || stock.full_name || stock.english_name || '暂无详情' }}
                      </span>
                    </button>
                  </div>
                </div>
              </div>
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                <div>
                  <label
                    style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">开始日期</label>
                  <input type="date" :value="backtestStartDate" class="inp"
                    @input="$emit('update:backtestStartDate', ($event.target as HTMLInputElement).value)" />
                </div>
                <div>
                  <label
                    style="font-size:13px; font-weight:500; color:var(--text-main); display:block; margin-bottom:6px;">结束日期</label>
                  <input type="date" :value="backtestEndDate" class="inp"
                    @input="$emit('update:backtestEndDate', ($event.target as HTMLInputElement).value)" />
                </div>
              </div>
              <div style="font-size:12px; color:var(--text-muted); line-height:1.6;">
                {{ backtestDataSource === 'tushare'
                  ? '使用 Tushare daily 未复权日线。需要本机已配置可访问 daily 接口的 token。'
                  : '直接读取本地 adjusted_main_contract CSV 历史数据，代码示例：AU9999.XSGE、IF9999.CCFX。' }}
              </div>
            </div>
          </div>
        </div>

        <div>
          <div v-if="!backtestResult"
            style="height:100%; min-height:220px; display:flex; align-items:center; justify-content:center; color:var(--text-muted); background:#f9fafb; border:1px dashed #d1d5db; border-radius:8px;">
            运行回测后查看信号、成交和权益结果
          </div>

          <div v-else style="display:flex; flex-direction:column; gap:20px;">
            <div class="metric-grid">
              <div class="stat-block">
                <span class="stat-label">最终权益</span>
                <span class="stat-value">{{ formatMoney(backtestResult.final_equity) }}</span>
              </div>
              <div class="stat-block">
                <span class="stat-label">已实现盈亏</span>
                <span class="stat-value"
                  :style="{ color: backtestResult.realized_pnl >= 0 ? 'var(--success)' : 'var(--danger)' }">
                  {{ formatMoney(backtestResult.realized_pnl) }}
                </span>
              </div>
              <div class="stat-block">
                <span class="stat-label">信号数</span>
                <span class="stat-value">{{ backtestResult.signals.length }}</span>
              </div>
              <div class="stat-block">
                <span class="stat-label">成交数</span>
                <span class="stat-value">{{ backtestResult.trades.length }}</span>
              </div>
            </div>

            <div class="mini-chart">
              <div v-for="(point, idx) in sampledEquityCurve" :key="idx" class="chart-bar"
                :style="{ height: equityBarHeight(point.equity) + '%' }" :title="formatMoney(point.equity)">
              </div>
            </div>

            <div style="overflow-x:auto; border:1px solid var(--border); border-radius:8px;">
              <table>
                <thead>
                  <tr>
                    <th style="width:120px;">类型</th>
                    <th>时间</th>
                    <th>标的</th>
                    <th>方向</th>
                    <th>价格</th>
                    <th>指标</th>
                    <th>参考</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="signal in backtestResult.signals" :key="signal.timestamp + signal.payload.side">
                    <td>Signal</td>
                    <td style="font-size:13px; color:var(--text-muted);">{{ signal.payload.bar_time }}</td>
                    <td>{{ signal.symbol }}</td>
                    <td>
                      <span class="badge" :class="signal.payload.side === 'BUY' ? 'badge-vwap' : 'badge-twap'">
                        {{ signal.payload.side }}
                      </span>
                    </td>
                    <td>{{ signalPrice(signal) }}</td>
                    <td>{{ signalMetric(signal) }}</td>
                    <td>{{ signalReference(signal) }}</td>
                  </tr>
                  <tr v-if="backtestResult.signals.length === 0">
                    <td colspan="7" style="text-align:center; color:var(--text-muted);">没有触发信号</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {
  BacktestPreset,
  BacktestResult,
  EquityPoint,
  PresetParameter,
  StockSearchResult,
} from '../types';
import {
  formatMoney,
  formatPresetSymbols,
  presetSupportsDataSource,
  signalMetric,
  signalPrice,
  signalReference,
} from '../utils';

defineProps<{
  backtestPresets: BacktestPreset[];
  selectedStrategyId: string;
  backtestDataSource: string;
  backtestTsCode: string;
  backtestStartDate: string;
  backtestEndDate: string;
  backtestResult: BacktestResult | null;
  stockSearchResults: StockSearchResult[];
  stockSearchOpen: boolean;
  backtestLoading: boolean;
  stockSearchLoading: boolean;
  selectedPreset: BacktestPreset | null;
  selectedPresetParameters: PresetParameter[];
  sampledEquityCurve: EquityPoint[];
  equityBarHeight: (equity: number) => number;
}>();

defineEmits<{
  'update:selectedStrategyId': [value: string];
  'update:backtestDataSource': [value: string];
  'update:backtestTsCode': [value: string];
  'update:backtestStartDate': [value: string];
  'update:backtestEndDate': [value: string];
  'update:stockSearchOpen': [value: boolean];
  run: [];
  'search-stocks': [];
  'select-stock': [stock: StockSearchResult];
  'close-stock-search': [];
}>();
</script>
