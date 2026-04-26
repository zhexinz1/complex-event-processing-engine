<template>
  <BacktestPanel
    v-model:selected-strategy-id="selectedStrategyId"
    v-model:backtest-data-source="backtestDataSource"
    v-model:backtest-ts-code="backtestTsCode"
    v-model:backtest-start-date="backtestStartDate"
    v-model:backtest-end-date="backtestEndDate"
    v-model:stock-search-open="stockSearchOpen"
    :backtest-presets="backtestPresets"
    :backtest-result="backtestResult"
    :stock-search-results="stockSearchResults"
    :backtest-loading="backtestLoading"
    :stock-search-loading="stockSearchLoading"
    :selected-preset="selectedPreset"
    :selected-preset-parameters="selectedPresetParameters"
    :sampled-equity-curve="sampledEquityCurve"
    :equity-bar-height="equityBarHeight"
    @run="runBacktest"
    @search-stocks="searchStocks()"
    @select-stock="selectStock"
    @close-stock-search="closeStockSearchSoon"
  />
</template>

<script setup lang="ts">
import { CepApi } from '../api';
import BacktestPanel from '../components/BacktestPanel.vue';
import { useBacktest } from '../composables/useBacktest';
import { useToast } from '../composables/useToast';

const { showToast } = useToast();
const {
  backtestPresets,
  selectedStrategyId,
  backtestDataSource,
  backtestTsCode,
  backtestStartDate,
  backtestEndDate,
  backtestResult,
  stockSearchResults,
  stockSearchOpen,
  backtestLoading,
  stockSearchLoading,
  selectedPreset,
  selectedPresetParameters,
  sampledEquityCurve,
  runBacktest,
  searchStocks,
  selectStock,
  closeStockSearchSoon,
  equityBarHeight,
} = useBacktest(CepApi, showToast, { enabled: true });
</script>
