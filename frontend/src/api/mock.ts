// ข้อมูลจำลองที่หน้าตาเหมือน backend mock (backend/modules/*/mock_*) — ใช้ตอน VITE_USE_MOCK=1
import type { AnalysisResponse, Coin, CoinTypeInfo } from './client'

const COIN_TYPES: CoinTypeInfo[] = [
  { code: 'THB_0_25', name_th: '25 สตางค์', value_baht: 0.25, diameter_mm: 16, color_group: 'copper', display_color: '#b45309' },
  { code: 'THB_0_50', name_th: '50 สตางค์', value_baht: 0.5, diameter_mm: 18, color_group: 'copper', display_color: '#ea580c' },
  { code: 'THB_1', name_th: '1 บาท', value_baht: 1, diameter_mm: 20, color_group: 'silver', display_color: '#64748b' },
  { code: 'THB_2', name_th: '2 บาท', value_baht: 2, diameter_mm: 21.75, color_group: 'gold', display_color: '#ca8a04' },
  { code: 'THB_5', name_th: '5 บาท', value_baht: 5, diameter_mm: 24, color_group: 'silver', display_color: '#2563eb' },
  { code: 'THB_10', name_th: '10 บาท', value_baht: 10, diameter_mm: 26, color_group: 'bimetal', display_color: '#16a34a' },
]

const store = new Map<string, { response: AnalysisResponse; url: string }>()

function imageSize(blob: Blob): Promise<[number, number]> {
  return createImageBitmap(blob).then((b) => [b.width, b.height])
}

export async function getCoinTypes() {
  return COIN_TYPES
}

export async function createAnalysis(image: Blob): Promise<AnalysisResponse> {
  const [w, h] = await imageSize(image)
  const step = w / (COIN_TYPES.length + 1)
  const pxPerMm = (step * 0.8) / 26
  const coins: Coin[] = COIN_TYPES.map((t, i) => ({
    coin_id: i,
    center_xy: [step * (i + 1), h / 2],
    radius_px: (t.diameter_mm * pxPerMm) / 2,
    ellipse: null,
    color_group: t.color_group,
    coin_type: t.code,
    value_baht: t.value_baht,
    confidence: 0.9,
    source: 'estimated',
    status: 'ok',
    reason: null,
  }))
  const last = coins[coins.length - 1]
  Object.assign(last, { coin_type: null, value_baht: null, confidence: null, status: 'needs_confirmation', reason: 'ตัวอย่างจาก mock: ระบบไม่แน่ใจชนิดของเหรียญนี้' })

  const id = crypto.randomUUID()
  const response: AnalysisResponse = {
    analysis_id: id,
    result: {
      schema_version: '0.1.0',
      image_size: [w, h],
      coins,
      total_baht: null,
      scale_mm_per_px: null,
      scale_source: null,
      status: 'needs_confirmation',
      reason: 'กดเลือกชนิดของเหรียญที่มีเครื่องหมาย ? เพื่อให้ระบบคำนวณที่เหลือ',
      debug_images: {},
    },
  }
  store.set(id, { response, url: URL.createObjectURL(image) })
  await new Promise((r) => setTimeout(r, 400))
  return response
}

export async function getAnalysis(id: string): Promise<AnalysisResponse> {
  const item = store.get(id)
  if (!item) throw new Error('ไม่พบผลการนับนี้')
  return item.response
}

export function imageUrl(id: string): string {
  return store.get(id)?.url ?? ''
}
