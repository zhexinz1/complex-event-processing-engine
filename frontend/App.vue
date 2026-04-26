<template>
  <div>
    <AppHeader :current-time="currentTime" :db-ok="dbOk" @open-assets="showAssetModal = true" />
    <AppNav />

    <router-view />

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
import AppHeader from './components/AppHeader.vue';
import AppNav from './components/AppNav.vue';
import AssetDictionaryModal from './components/AssetDictionaryModal.vue';
import ToastNotice from './components/ToastNotice.vue';
import { useAllocations } from './composables/useAllocations';
import { useClock } from './composables/useClock';
import { useToast } from './composables/useToast';

const { toast, showToast } = useToast();
const { currentTime } = useClock();
const showAssetModal = ref(false);

const {
  allowedAssets,
  dbOk,
  addingAsset,
  newAssetCode,
  addAsset,
  deleteAsset,
} = useAllocations(CepApi, showToast);
</script>
