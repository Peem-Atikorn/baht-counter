import type { AnalysisResponse, Coin, CoinTypeInfo } from '../api/client'

export const coinType: CoinTypeInfo = {
  code: 'THB_1',
  name_th: 'หนึ่งบาทจาก API',
  value_baht: 1,
  diameter_mm: 20.1,
  color_group: 'silver',
  display_color: '#64748b',
}
export const types: CoinTypeInfo[] = [
  coinType,
  { ...coinType, code: 'THB_5', name_th: '5 บาท', value_baht: 5, diameter_mm: 24 },
]
export function coin(id: number, type: Coin['coin_type'] = 'THB_1'): Coin {
  return {
    coin_id: id,
    center_xy: [200, 150],
    radius_px: 50,
    ellipse: null,
    color_group: 'silver',
    coin_type: type,
    value_baht: type === 'THB_1' ? 1 : type === 'THB_5' ? 5 : null,
    confidence: null,
    source: 'estimated',
    status: type === 'THB_1' ? 'ok' : 'needs_confirmation',
    reason: null,
  }
}
export function analysis(coins = [coin(0)]): AnalysisResponse {
  const needs = coins.some((c) => c.value_baht == null)
  return {
    analysis_id: 'test',
    result: {
      schema_version: '0.2.1',
      image_size: [800, 600],
      coins,
      total_baht: !coins.length || needs ? null : coins.reduce((sum, c) => sum + c.value_baht!, 0),
      scale_mm_per_px: null,
      scale_source: null,
      status: !coins.length ? 'failed' : needs ? 'needs_confirmation' : 'ok',
      reason: null,
      debug_images: {},
    },
  }
}
