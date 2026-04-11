<template>
  <div>
    <AppHeader :current-time="currentTime" :db-ok="dbOk" @open-assets="showAssetModal = true" />
    <AppNav v-model="activeTab" :show-backtest="showBacktest" />

    <template v-if="activeTab === 'allocations'">
      <AllocationToolbar
        v-model:filter-date="filterDate"
        v-model:filter-product="filterProduct"
        :row-count="rows.length"
        :product-count="productCount"
        :latest-date="latestDate"
        :products="products"
        @refresh="fetchData"
        @add="openModal(null)"
      />
      <AllocationTable
        :rows="filteredRows"
        :loading="loading"
        @edit="openModal"
        @delete="deleteRow"
      />
    </template>

    <BacktestPanel
      v-if="showBacktest && activeTab === 'backtest'"
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

    <AllocationModal
      :show="showModal"
      :editing-row="editingRow"
      :form="form"
      :allowed-assets="allowedAssets"
      :total-warning="totalWarning"
      :total-pct="totalPct"
      :saving="saving"
      @close="closeModal"
      @save="saveRow"
    />

    <AssetDictionaryModal
      v-model:new-asset-code="newAssetCode"
      :show="showAssetModal"
      :allowed-assets="allowedAssets"
      :adding-asset="addingAsset"
      @close="showAssetModal = false"
      @add="addAsset"
      @delete="deleteAsset"
    />

    <ToastNotice :toast="toast" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { CepApi } from './api';
import AllocationModal from './components/AllocationModal.vue';
import AllocationTable from './components/AllocationTable.vue';
import AllocationToolbar from './components/AllocationToolbar.vue';
import AppHeader from './components/AppHeader.vue';
import AppNav from './components/AppNav.vue';
import AssetDictionaryModal from './components/AssetDictionaryModal.vue';
import BacktestPanel from './components/BacktestPanel.vue';
import ToastNotice from './components/ToastNotice.vue';
import { useAllocations } from './composables/useAllocations';
import { useBacktest } from './composables/useBacktest';
import { useClock } from './composables/useClock';
import { useToast } from './composables/useToast';
import type { AppTab } from './types';

const activeTab = ref<AppTab>('allocations');
const showBacktest = import.meta.env.VITE_SHOW_BACKTEST === 'true';
const { toast, showToast } = useToast();
const { currentTime } = useClock();
const {
  rows,
  products,
  allowedAssets,
  loading,
  dbOk,
  filterDate,
  filterProduct,
  showModal,
  showAssetModal,
  editingRow,
  saving,
  addingAsset,
  newAssetCode,
  form,
  filteredRows,
  productCount,
  latestDate,
  totalPct,
  totalWarning,
  fetchData,
  addAsset,
  deleteAsset,
  openModal,
  closeModal,
  saveRow,
  deleteRow,
} = useAllocations(CepApi, showToast);
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
} = useBacktest(CepApi, showToast, { enabled: showBacktest });
</script>
