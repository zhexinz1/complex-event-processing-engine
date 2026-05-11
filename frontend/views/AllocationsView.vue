<template>
  <div>
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
    <AllocationModal
      :show="showModal"
      :editing-row="editingRow"
      :form="form"
      :allowed-assets="allowedAssets"
      :products="products"
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
  </div>
</template>

<script setup lang="ts">
import { CepApi } from '../api';
import AllocationModal from '../components/AllocationModal.vue';
import AllocationTable from '../components/AllocationTable.vue';
import AllocationToolbar from '../components/AllocationToolbar.vue';
import AssetDictionaryModal from '../components/AssetDictionaryModal.vue';
import { useAllocations } from '../composables/useAllocations';
import { useToast } from '../composables/useToast';

const { showToast } = useToast();
const {
  rows, products, allowedAssets, loading,
  filterDate, filterProduct,
  showModal, showAssetModal,
  editingRow, saving, addingAsset, newAssetCode, form,
  filteredRows, productCount, latestDate, totalPct, totalWarning,
  fetchData, addAsset, deleteAsset,
  openModal, closeModal, saveRow, deleteRow,
} = useAllocations(CepApi, showToast);
</script>
