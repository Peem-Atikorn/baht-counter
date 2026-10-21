import type { components } from './schema'
import * as mock from './mock'

export type Coin = components['schemas']['Coin']
export type CountResult = components['schemas']['CountResult']
export type CoinTypeInfo = components['schemas']['CoinTypeInfo']
export type AnalysisResponse = components['schemas']['AnalysisResponse']
export type HistoryPage = components['schemas']['HistoryPage']
export type CoinCode = NonNullable<Coin['coin_type']>
export type ExportFormat = 'json' | 'csv'

// VITE_USE_MOCK=1 ใช้ข้อมูลจำลองฝั่งเว็บ ไม่ต้องรัน backend
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === '1'

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองใหม่')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(
      typeof body?.detail === 'string' ? body.detail : `เกิดข้อผิดพลาด (${res.status})`,
    )
  }
  return res.json()
}

export function getCoinTypes(): Promise<CoinTypeInfo[]> {
  return USE_MOCK ? mock.getCoinTypes() : request('/api/coin-types')
}

export function createAnalysis(image: Blob): Promise<AnalysisResponse> {
  if (USE_MOCK) return mock.createAnalysis(image)
  const form = new FormData()
  form.append('file', image, image instanceof File ? image.name : 'capture.jpg')
  return request('/api/analyses', { method: 'POST', body: form })
}

export function getAnalysis(id: string): Promise<AnalysisResponse> {
  return USE_MOCK ? mock.getAnalysis(id) : request(`/api/analyses/${encodeURIComponent(id)}`)
}

export function imageUrl(id: string, name: string): string {
  return USE_MOCK
    ? mock.imageUrl(id)
    : `/api/analyses/${encodeURIComponent(id)}/images/${encodeURIComponent(name)}`
}

export function updateCoin(
  id: string,
  coinId: number,
  coinType: CoinCode,
): Promise<AnalysisResponse> {
  return USE_MOCK
    ? mock.updateCoin(id, coinId, coinType)
    : request(`/api/analyses/${encodeURIComponent(id)}/coins/${coinId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ coin_type: coinType }),
      })
}

export function addCoin(id: string, xy: [number, number]): Promise<AnalysisResponse> {
  return USE_MOCK
    ? mock.addCoin(id, xy)
    : request(`/api/analyses/${encodeURIComponent(id)}/coins`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ xy }),
      })
}

export function deleteCoin(id: string, coinId: number): Promise<AnalysisResponse> {
  return USE_MOCK
    ? mock.deleteCoin(id, coinId)
    : request(`/api/analyses/${encodeURIComponent(id)}/coins/${coinId}`, { method: 'DELETE' })
}

export function getHistory(limit = 20, offset = 0): Promise<HistoryPage> {
  return USE_MOCK
    ? mock.getHistory(limit, offset)
    : request(`/api/history?limit=${limit}&offset=${offset}`)
}

export async function exportAnalysis(id: string, format: ExportFormat): Promise<Blob> {
  if (USE_MOCK) return mock.exportAnalysis(id, format)
  let response: Response
  try {
    response = await fetch(`/api/analyses/${encodeURIComponent(id)}/export?format=${format}`)
  } catch {
    throw new ApiError('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาลองใหม่')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(
      typeof body?.detail === 'string' ? body.detail : 'ดาวน์โหลดผลไม่สำเร็จ กรุณาลองใหม่',
    )
  }
  return response.blob()
}
