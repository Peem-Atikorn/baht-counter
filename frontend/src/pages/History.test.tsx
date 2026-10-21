import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { getHistory } from '../api/client'
import History from './History'
vi.mock('../api/client', () => ({ getHistory: vi.fn(), USE_MOCK: false }))
beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)
it('แสดงประวัติว่างและลองใหม่ได้เมื่อ API ล้มเหลว', async () => {
  vi.mocked(getHistory)
    .mockRejectedValueOnce(new Error('โหลดไม่สำเร็จ'))
    .mockResolvedValueOnce({ items: [], total: 0 })
  render(
    <MemoryRouter>
      <History />
    </MemoryRouter>,
  )
  fireEvent.click(await screen.findByRole('button', { name: 'ลองอีกครั้ง' }))
  expect(await screen.findByText('ยังไม่มีภาพที่นับ')).toBeTruthy()
})
it('เปลี่ยนหน้าประวัติและคงยอด null เป็นระบุไม่ได้', async () => {
  const items = Array.from({ length: 13 }, (_, i) => ({
    analysis_id: `item-${i}`,
    created_at: '2026-10-21T10:00:00Z',
    coin_count: 1,
    total_baht: null,
    status: 'needs_confirmation' as const,
  }))
  vi.mocked(getHistory).mockImplementation(async (limit = 12, offset = 0) => ({
    items: items.slice(offset, offset + limit),
    total: 13,
  }))
  render(
    <MemoryRouter>
      <History />
    </MemoryRouter>,
  )
  await screen.findByText('ทั้งหมด 13 รายการ')
  expect(screen.getAllByText('ระบุไม่ได้')).toHaveLength(12)
  fireEvent.click(screen.getByRole('button', { name: 'ถัดไป' }))
  await screen.findByText('หน้า 2 / 2')
  expect(getHistory).toHaveBeenLastCalledWith(12, 12)
  expect(screen.getByRole('link', { name: /ดูผล/ }).getAttribute('href')).toBe('/result/item-12')
  expect((screen.getByRole('button', { name: 'ถัดไป' }) as HTMLButtonElement).disabled).toBe(true)
})
