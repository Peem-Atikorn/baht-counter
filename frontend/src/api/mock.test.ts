import { afterEach, expect, it, vi } from 'vitest'
import * as mock from './mock'

afterEach(() => vi.unstubAllGlobals())
it('โหมดทดลองเพิ่ม แก้ ลบ และเรียกประวัติได้ โดยไม่แทน unknown หรือภาพว่างด้วยศูนย์', async () => {
  const close = vi.fn()
  vi.stubGlobal(
    'createImageBitmap',
    vi.fn(async () => ({ width: 800, height: 600, close })),
  )
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = () => 'blob:sample'
    },
  )
  const data = await mock.createAnalysis(new Blob(['sample']))
  const id = data.analysis_id
  expect(close).toHaveBeenCalledOnce()
  expect(data.result.total_baht).toBeNull()
  // ผลที่คืนให้หน้าเว็บต้องไม่เป็น reference ของข้อมูลภายใน
  data.result.coins.length = 0
  expect((await mock.getAnalysis(id)).result.coins).toHaveLength(6)
  const added = await mock.addCoin(id, [500, 300])
  const newCoin = added.result.coins.at(-1)!
  expect(newCoin.source).toBe('user_added')
  expect(newCoin.coin_type).toBeNull()
  const edited = await mock.updateCoin(id, newCoin.coin_id, 'THB_5')
  expect(edited.result.coins.at(-1)?.value_baht).toBe(5)
  expect(edited.result.coins.at(-1)?.source).toBe('user_edited')
  const withUnknown = await mock.updateCoin(id, 0, 'unknown')
  const unknown = withUnknown.result.coins[0]
  expect(unknown.status).toBe('ok')
  expect(unknown.color_group).toBe('copper')
  expect(unknown.source).toBe('user_edited')
  expect(unknown.confidence).toBeNull()
  expect(unknown.reason).toBe('ไม่ใช่เหรียญไทย ลบเหรียญนี้ออกเพื่อให้รวมยอดได้')
  const confirmed = await mock.updateCoin(id, 5, 'THB_10')
  expect(confirmed.result.status).toBe('ok')
  expect(confirmed.result.total_baht).toBeNull()
  await expect(mock.addCoin(id, [900, 600])).rejects.toThrow('ตำแหน่งต้องอยู่ในภาพ')
  for (const coin of edited.result.coins) await mock.deleteCoin(id, coin.coin_id)
  const empty = await mock.getAnalysis(id)
  expect(empty.result.status).toBe('failed')
  expect(empty.result.total_baht).toBeNull()
  expect((await mock.getHistory()).items.find((item) => item.analysis_id === id)?.coin_count).toBe(
    0,
  )
})
