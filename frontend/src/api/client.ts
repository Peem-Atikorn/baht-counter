import type { components } from './schema'
import * as mock from './mock'

export type Coin = components['schemas']['Coin']
export type CountResult = components['schemas']['CountResult']
export type CoinTypeInfo = components['schemas']['CoinTypeInfo']
export type AnalysisResponse = components['schemas']['AnalysisResponse']

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
  return USE_MOCK ? mock.getAnalysis(id) : request(`/api/analyses/${id}`)
}

export function imageUrl(id: string, name: string): string {
  return USE_MOCK ? mock.imageUrl(id) : `/api/analyses/${id}/images/${name}`
}
