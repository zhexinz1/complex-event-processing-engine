export type ToastType = 'success' | 'error';

export type AppTab = 'allocations' | 'backtest';

export type ShowToast = (message: string, type?: ToastType) => void;

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
  total?: number;
  id?: number;
}

export interface AllocationRow {
  id: number;
  target_date: string;
  product_name: string;
  asset_code: string;
  weight_ratio: number;
  algo_type: string;
  created_at?: string;
  updated_at?: string;
}

export interface Asset {
  asset_code: string;
  created_at?: string;
}

export interface AllocationForm {
  target_date: string;
  product_name: string;
  asset_code: string;
  weight_pct: string;
  algo_type: string;
}

export interface SaveWeightPayload {
  target_date: string;
  product_name: string;
  asset_code: string;
  weight_ratio: number;
  algo_type: string;
}

export interface PresetParameter {
  label: string;
  value: unknown;
}

export interface BacktestPreset {
  id: string;
  name: string;
  description: string;
  dataset: string;
  symbol?: string;
  symbols?: string[];
  data_sources?: string[];
  parameter_summary?: PresetParameter[];
  parameters?: Record<string, unknown>;
}

export interface EquityPoint {
  timestamp?: string;
  equity: number;
}

export interface BacktestSignalPayload {
  bar_time?: string;
  side?: string;
  close?: number;
  price?: number;
  score?: number;
  pbx1?: number;
  ma1?: number;
  winner?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface BacktestSignal {
  timestamp: string;
  symbol: string;
  payload: BacktestSignalPayload;
}

export interface BacktestTrade {
  [key: string]: unknown;
}

export interface BacktestResult {
  final_equity: number;
  realized_pnl: number;
  equity_curve: EquityPoint[];
  signals: BacktestSignal[];
  trades: BacktestTrade[];
}

export interface StockSearchResult {
  ts_code: string;
  name: string;
  exchange?: string;
  board?: string;
  industry?: string;
  full_name?: string;
  english_name?: string;
}

export interface BacktestRequest {
  strategy_id: string;
  data_source: string;
  ts_code?: string;
  start_date?: string;
  end_date?: string;
}

export interface CepApiClient {
  requestJson<T = unknown>(url: string, options?: RequestInit): Promise<T>;
  fetchWeights(): Promise<ApiResponse<AllocationRow[]>>;
  fetchProducts(): Promise<ApiResponse<string[]>>;
  fetchAssets(): Promise<ApiResponse<Asset[]>>;
  createAsset(assetCode: string): Promise<ApiResponse>;
  deleteAsset(assetCode: string): Promise<ApiResponse>;
  saveWeight(payload: SaveWeightPayload): Promise<ApiResponse>;
  deleteWeight(recordId: number): Promise<ApiResponse>;
  fetchBacktestPresets(): Promise<ApiResponse<BacktestPreset[]>>;
  searchStocks(keyword: string, limit?: number): Promise<ApiResponse<StockSearchResult[]>>;
  runBacktest(payload: BacktestRequest): Promise<ApiResponse<BacktestResult>>;
}
