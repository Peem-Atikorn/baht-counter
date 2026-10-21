import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { getCoinTypes } from '../api/client'
import { coinType } from '../test/fixtures'
import Home from './Home'
vi.mock('../api/client', () => ({ getCoinTypes: vi.fn() }))
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getCoinTypes).mockResolvedValue([coinType])
})
afterEach(cleanup)
describe('ข้อมูลเหรียญหน้าแรก', () => {
  it('หน้าแรกใช้ชื่อและขนาดจาก API และลองใหม่ได้เมื่อโหลดไม่สำเร็จ', async () => {
    vi.mocked(getCoinTypes).mockRejectedValueOnce(new Error('offline'))
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'ลองอีกครั้ง' }))
    expect(await screen.findByText('หนึ่งบาทจาก API')).toBeTruthy()
    expect(screen.getByText('สีเงิน · 20.1 มม.')).toBeTruthy()
    expect(screen.getByText('1 ชนิด')).toBeTruthy()
    expect(screen.getByRole('link', { name: /อัปโหลดรูป เลือกรูป/ }).getAttribute('href')).toBe(
      '/count',
    )
  })
})
