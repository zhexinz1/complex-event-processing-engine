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
};

declare global {
  interface Window {
    CepApi: CepApiClient;
  }
}

window.CepApi = CepApi;
