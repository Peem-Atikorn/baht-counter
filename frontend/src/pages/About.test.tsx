import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { getAnalysis } from '../api/client'
import { analysis } from '../test/fixtures'
import About from './About'
vi.mock('../api/client', () => ({
  getAnalysis: vi.fn(),
  imageUrl: () => '/original.png',
  USE_MOCK: false,
}))
beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)
it('แสดงภาพกลางทางจากผลเดียวกัน และรองรับภาพที่โหลดไม่ได้', async () => {
  const data = analysis()
  data.result.debug_images = {
    detection_result: '/detected.png',
    enhanced: '/enhanced.png',
    gray: '/gray.png',
    he: '/he.png',
  }
  vi.mocked(getAnalysis).mockResolvedValue(data)
  render(
    <MemoryRouter initialEntries={['/about?analysis=test']}>
      <About />
    </MemoryRouter>,
  )
  const gray = await screen.findByAltText('ภาพระดับสีเทา')
  expect(screen.getAllByRole('img').map((img) => img.getAttribute('alt'))).toEqual([
    'ภาพต้นฉบับ',
    'ภาพระดับสีเทา',
    'ปรับความต่างระดับแสงทั้งภาพ',
    'ภาพหลังลดจุดรบกวน',
    'ตำแหน่งเหรียญที่ตรวจพบ',
  ])
  expect(gray.getAttribute('src')).toBe('/gray.png')
  expect(screen.getByAltText('ภาพต้นฉบับ').getAttribute('src')).toBe('/original.png')
  fireEvent.error(gray)
  expect(screen.getByText('โหลดภาพนี้ไม่ได้ กรุณาเปิดผลการนับใหม่')).toBeTruthy()
})
