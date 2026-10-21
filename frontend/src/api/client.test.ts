import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { analysis } from '../test/fixtures'

const fetchMock = vi.fn()
beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('VITE_USE_MOCK', '0')
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

it('ส่งชนิดเหรียญและพิกัดต้นฉบับตามสัญญา API และคืนผลทั้งภาพ', async () => {
  const api = await import('./client')
  fetchMock.mockImplementation(
    async () => new Response(JSON.stringify(analysis()), { status: 200 }),
  )
  await api.updateCoin('test', 7, 'THB_5')
  expect(fetchMock).toHaveBeenLastCalledWith('/api/analyses/test/coins/7', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ coin_type: 'THB_5' }),
  })
  await api.addCoin('test', [123.5, 234.5])
  expect(fetchMock).toHaveBeenLastCalledWith('/api/analyses/test/coins', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ xy: [123.5, 234.5] }),
  })
  await api.deleteCoin('test', 7)
  expect(fetchMock).toHaveBeenLastCalledWith('/api/analyses/test/coins/7', { method: 'DELETE' })
})

it('ส่ง limit และ offset ให้ประวัติ และคง null ของยอดรวม', async () => {
  const api = await import('./client')
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0 })))
  expect(await api.getHistory(12, 24)).toEqual({ items: [], total: 0 })
  expect(fetchMock).toHaveBeenCalledWith('/api/history?limit=12&offset=24', undefined)
})

it('คืนไฟล์ export เป็น blob และเก็บข้อความภาษาไทยเมื่อ API ปฏิเสธ', async () => {
  const api = await import('./client')
  fetchMock.mockResolvedValueOnce(
    new Response('coin_id,coin_type\n1,THB_1', { headers: { 'content-type': 'text/csv' } }),
  )
  const blob = await api.exportAnalysis('test', 'csv')
  expect(blob.type).toBe('text/csv')
  expect(await blob.text()).toContain('THB_1')
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: 'ไม่พบผลการนับนี้' }), { status: 404 }),
  )
  await expect(api.exportAnalysis('missing', 'json')).rejects.toThrow('ไม่พบผลการนับนี้')
})

it('รายงานการเชื่อมต่อล้มเหลวและข้อผิดพลาดที่ไม่ใช่ JSON อย่างอ่านได้', async () => {
  const api = await import('./client')
  fetchMock.mockRejectedValueOnce(new TypeError('network'))
  await expect(api.updateCoin('test', 1, 'THB_1')).rejects.toThrow('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้')
  fetchMock.mockResolvedValueOnce(new Response('<html>error</html>', { status: 502 }))
  await expect(api.exportAnalysis('test', 'json')).rejects.toThrow('ดาวน์โหลดผลไม่สำเร็จ')
})
