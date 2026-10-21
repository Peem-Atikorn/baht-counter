// ข้อมูลจำลองที่หน้าตาเหมือน backend mock (backend/modules/*/mock_*) — ใช้ตอน VITE_USE_MOCK=1
import type {
  AnalysisResponse,
  Coin,
  CoinTypeInfo,
  CoinCode,
  HistoryPage,
  ExportFormat,
} from './client'

const COIN_TYPES: CoinTypeInfo[] = [
  {
    code: 'THB_0_25',
    name_th: '25 สตางค์',
    value_baht: 0.25,
    diameter_mm: 16,
    color_group: 'copper',
    display_color: '#b45309',
  },
  {
    code: 'THB_0_50',
    name_th: '50 สตางค์',
    value_baht: 0.5,
    diameter_mm: 18,
    color_group: 'copper',
    display_color: '#ea580c',
  },
  {
    code: 'THB_1',
    name_th: '1 บาท',
    value_baht: 1,
    diameter_mm: 20,
    color_group: 'silver',
    display_color: '#64748b',
  },
  {
    code: 'THB_2',
    name_th: '2 บาท',
    value_baht: 2,
    diameter_mm: 21.75,
    color_group: 'gold',
    display_color: '#ca8a04',
  },
  {
    code: 'THB_5',
    name_th: '5 บาท',
    value_baht: 5,
    diameter_mm: 24,
    color_group: 'silver',
    display_color: '#2563eb',
  },
  {
    code: 'THB_10',
    name_th: '10 บาท',
    value_baht: 10,
    diameter_mm: 26,
    color_group: 'bimetal',
    display_color: '#16a34a',
  },
]

const store = new Map<string, { response: AnalysisResponse; url: string; createdAt: string }>()

async function imageSize(blob: Blob): Promise<[number, number]> {
  const bitmap = await createImageBitmap(blob)
  const size: [number, number] = [bitmap.width, bitmap.height]
  bitmap.close()
  return size
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
  Object.assign(last, {
    coin_type: null,
    value_baht: null,
    confidence: null,
    status: 'needs_confirmation',
    reason: 'ตัวอย่างจาก mock: ระบบไม่แน่ใจชนิดของเหรียญนี้',
  })

  const id = crypto.randomUUID()
  const response: AnalysisResponse = {
    analysis_id: id,
    result: {
      schema_version: '0.2.0',
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
  store.set(id, { response, url: URL.createObjectURL(image), createdAt: new Date().toISOString() })
  await new Promise((r) => setTimeout(r, 400))
  return structuredClone(response)
}

export async function getAnalysis(id: string): Promise<AnalysisResponse> {
  const item = store.get(id)
  if (!item) throw new Error('ไม่พบผลการนับนี้ ข้อมูลทดลองจะหายเมื่อรีเฟรชหน้า')
  return structuredClone(item.response)
}

export function imageUrl(id: string): string {
  return store.get(id)?.url ?? ''
}

function commitResult(id: string, coins: Coin[]): AnalysisResponse {
  const item = store.get(id)
  if (!item) throw new Error('ไม่พบผลการนับนี้')
  const needs = coins.some((c) => c.value_baht == null)
  const empty = coins.length === 0
  const result = item.response.result
  item.response = {
    analysis_id: id,
    result: {
      ...result,
      coins,
      total_baht:
        needs || empty
          ? null
          : Math.round(coins.reduce((sum, c) => sum + c.value_baht!, 0) * 100) / 100,
      status: empty ? 'failed' : needs ? 'needs_confirmation' : 'ok',
      reason: empty ? 'ไม่พบเหรียญในภาพ' : needs ? 'เลือกชนิดของเหรียญที่ยังระบุไม่ได้' : null,
    },
  }
  return structuredClone(item.response)
}

export async function updateCoin(id: string, coinId: number, code: CoinCode) {
  const data = await getAnalysis(id)
  const target = data.result.coins.find((c) => c.coin_id === coinId)
  if (!target) throw new Error('ไม่พบเหรียญนี้')
  const type = COIN_TYPES.find((t) => t.code === code)
  const coins = data.result.coins.map((c) =>
    c.coin_id === coinId
      ? ({
          ...c,
          coin_type: code,
          color_group: type?.color_group ?? 'unknown',
          value_baht: type?.value_baht ?? null,
          source: c.source === 'user_added' ? 'user_added' : 'user_edited',
          status: code === 'unknown' ? 'needs_confirmation' : 'ok',
          reason: code === 'unknown' ? 'ไม่ใช่เหรียญไทยที่รองรับ' : null,
        } as Coin)
      : c,
  )
  return commitResult(id, coins)
}

export async function addCoin(id: string, xy: [number, number]) {
  const data = await getAnalysis(id)
  const [w, h] = data.result.image_size
  if (xy.some((v) => !Number.isFinite(v)) || xy[0] < 0 || xy[1] < 0 || xy[0] >= w || xy[1] >= h)
    throw new Error('ตำแหน่งต้องอยู่ในภาพ')
  const coins = data.result.coins
  const coin: Coin = {
    coin_id: Math.max(-1, ...coins.map((c) => c.coin_id)) + 1,
    center_xy: xy,
    radius_px: Math.min(w, h) * 0.05,
    ellipse: null,
    color_group: 'unknown',
    coin_type: null,
    value_baht: null,
    confidence: null,
    source: 'user_added',
    status: 'needs_confirmation',
    reason: 'กรุณาเลือกชนิดเหรียญที่เพิ่ม',
  }
  return commitResult(id, [...coins, coin])
}

export async function deleteCoin(id: string, coinId: number) {
  const data = await getAnalysis(id)
  if (!data.result.coins.some((c) => c.coin_id === coinId)) throw new Error('ไม่พบเหรียญนี้')
  return commitResult(
    id,
    data.result.coins.filter((c) => c.coin_id !== coinId),
  )
}

export async function getHistory(limit = 20, offset = 0): Promise<HistoryPage> {
  const items = [...store.values()].reverse().map(({ response, createdAt }) => ({
    analysis_id: response.analysis_id,
    created_at: createdAt,
    status: response.result.status,
    total_baht: response.result.total_baht,
    coin_count: response.result.coins.length,
  }))
  return { items: items.slice(offset, offset + limit), total: items.length }
}

export async function exportAnalysis(id: string, format: ExportFormat): Promise<Blob> {
  const data = await getAnalysis(id)
  if (format === 'json')
    return new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const header =
    'coin_id,coin_type,value_baht,color_group,source,status,center_x,center_y,radius_px'
  const rows = data.result.coins.map((c) =>
    [
      c.coin_id,
      c.coin_type ?? '',
      c.value_baht ?? '',
      c.color_group,
      c.source,
      c.status,
      ...c.center_xy,
      c.radius_px,
    ].join(','),
  )
  return new Blob(['\ufeff', [header, ...rows].join('\n'), '\n'], {
    type: 'text/csv;charset=utf-8',
  })
}
