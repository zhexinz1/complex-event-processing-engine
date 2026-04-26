import type { BacktestPreset, BacktestSignal } from './types';

export function weightBarStyle(ratio: number): { width: string; background: string } {
  const pct = Math.min(ratio * 100, 100);
  return {
    width: `${pct}%`,
    background: 'linear-gradient(90deg, #3b82f6, #2563eb)',
  };
}

export function formatMoney(value: number | string | null | undefined): string {
  return Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatPresetSymbols(preset: BacktestPreset | null): string {
  if (!preset) return '';
  if (Array.isArray(preset.symbols)) return preset.symbols.join(', ');
  return preset.symbol || '';
}

export function presetSupportsDataSource(
  preset: BacktestPreset | null,
  dataSource: string,
): boolean {
  if (!preset || !Array.isArray(preset.data_sources)) return true;
  return preset.data_sources.includes(dataSource);
}

export function signalPrice(signal: BacktestSignal): string {
  return Number(signal.payload.close || signal.payload.price || 0).toFixed(2);
}

export function signalMetric(signal: BacktestSignal): string {
  const payload = signal.payload || {};
  if (payload.score !== undefined) return Number(payload.score).toFixed(4);
  if (payload.pbx1 !== undefined) return Number(payload.pbx1).toFixed(2);
  return '-';
}

export function signalReference(signal: BacktestSignal): string {
  const payload = signal.payload || {};
  if (payload.winner) return payload.winner;
  if (payload.ma1 !== undefined) return Number(payload.ma1).toFixed(2);
  return payload.reason || '-';
}

export function isTushareCode(value: string): boolean {
  return /^(\d{6}|\d{6}\.(SZ|SH|BJ))$/i.test(value.trim());
}

export function toTushareDate(value: string): string {
  return String(value || '').replaceAll('-', '');
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
