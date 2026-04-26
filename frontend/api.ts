import type {
  ApiResponse,
  Asset,
  AllocationRow,
  BacktestRequest,
  BacktestResult,
  CepApiClient,
  SaveWeightPayload,
  StockSearchResult,
  BacktestPreset,
  ProductInfo,
  FundInflow,
  PendingOrdersResponse,
  RealtimePrice,
  MarketHealthData,
} from './types';

export const CepApi: CepApiClient = {
  async requestJson<T = unknown>(url: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(url, options);
    return response.json() as Promise<T>;
  },

  fetchWeights(): Promise<ApiResponse<AllocationRow[]>> {
    return this.requestJson('/api/weights');
  },

  fetchProducts(): Promise<ApiResponse<string[]>> {
    return this.requestJson('/api/products');
  },

  fetchAssets(): Promise<ApiResponse<Asset[]>> {
    return this.requestJson('/api/assets');
  },

  createAsset(assetCode: string): Promise<ApiResponse> {
    return this.requestJson('/api/assets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_code: assetCode }),
    });
  },

  deleteAsset(assetCode: string): Promise<ApiResponse> {
    return this.requestJson(`/api/assets/${assetCode}`, { method: 'DELETE' });
  },

  saveWeight(payload: SaveWeightPayload): Promise<ApiResponse> {
    return this.requestJson('/api/weights', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  deleteWeight(recordId: number): Promise<ApiResponse> {
    return this.requestJson(`/api/weights/${recordId}`, { method: 'DELETE' });
  },

  fetchBacktestPresets(): Promise<ApiResponse<BacktestPreset[]>> {
    return this.requestJson('/api/backtests/presets');
  },

  searchStocks(keyword: string, limit = 20): Promise<ApiResponse<StockSearchResult[]>> {
    const params = new URLSearchParams({ q: keyword, limit: String(limit) });
    return this.requestJson(`/api/stocks/search?${params.toString()}`);
  },

  runBacktest(payload: BacktestRequest): Promise<ApiResponse<BacktestResult>> {
    return this.requestJson('/api/backtests/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  // ---- Fund Inflow ----

  fetchProductList(): Promise<ApiResponse & { products: ProductInfo[] }> {
    return this.requestJson('/api/products/list');
  },

  submitFundInflow(payload: { product_name: string; net_inflow: number; input_by: string }): Promise<ApiResponse & { batch_id: string }> {
    return this.requestJson('/api/fund/inflow', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  fetchFundInflows(): Promise<ApiResponse & { inflows: FundInflow[] }> {
    return this.requestJson('/api/fund/inflows');
  },

  // ---- Orders ----

  fetchPendingOrders(batchId: string): Promise<PendingOrdersResponse> {
    return this.requestJson(`/api/orders/pending?batch_id=${batchId}`);
  },

  fetchAllOrders(params?: Record<string, string>): Promise<ApiResponse> {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return this.requestJson(`/api/orders/all${qs}`);
  },

  updateOrder(orderId: number, finalQuantity: number): Promise<ApiResponse> {
    return this.requestJson('/api/orders/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: orderId, final_quantity: finalQuantity }),
    });
  },

  confirmOrders(batchId: string, confirmedBy: string, priceType: string): Promise<ApiResponse> {
    return this.requestJson('/api/orders/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: batchId, confirmed_by: confirmedBy, price_type: priceType }),
    });
  },

  reconcileOrders(): Promise<ApiResponse> {
    return this.requestJson('/api/orders/reconcile', { method: 'POST' });
  },

  fetchXtCache(): Promise<ApiResponse> {
    return this.requestJson('/api/xuntou/cache');
  },

  // ---- Prices ----

  fetchRealtimePrices(symbols: string): Promise<ApiResponse & { prices: Record<string, RealtimePrice> }> {
    return this.requestJson(`/api/prices/realtime?symbols=${symbols}`);
  },

  // ---- Market Health ----

  fetchMarketHealth(): Promise<ApiResponse & MarketHealthData> {
    return this.requestJson('/api/market/health');
  },
};

declare global {
  interface Window {
    CepApi: CepApiClient;
  }
}

window.CepApi = CepApi;
