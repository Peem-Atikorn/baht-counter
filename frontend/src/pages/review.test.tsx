import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { getAnalysis, getCoinTypes, type Coin, type CoinTypeInfo } from '../api/client'
import Capture from './Capture'
import Home from './Home'
import Result from './Result'

vi.mock('../api/client', () => ({
  createAnalysis: vi.fn(),
  getAnalysis: vi.fn(),
  getCoinTypes: vi.fn(),
  imageUrl: () => '/sample.png',
}))
vi.mock('../components/Camera', () => ({
  default: ({ onCancel }: { onCancel: () => void }) => (
    <button onClick={onCancel}>ยกเลิกกล้อง</button>
  ),
}))

let urlSequence = 0
const createUrl = vi.fn(() => `blob:preview-${++urlSequence}`)
const revokeUrl = vi.fn()
const coinType: CoinTypeInfo = {
  code: 'THB_1',
  name_th: 'หนึ่งบาทจาก API',
  value_baht: 1,
  diameter_mm: 20.1,
  color_group: 'silver',
  display_color: '#ccc',
}

function Location() {
  const location = useLocation()
  return (
    <output aria-label="ที่อยู่ปัจจุบัน">
      {location.pathname}
      {location.search}
    </output>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal(
    'URL',
    class extends URL {
      static createObjectURL = createUrl
      static revokeObjectURL = revokeUrl
    },
  )
  vi.mocked(getCoinTypes).mockResolvedValue([coinType])
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ข้อแก้ไขจากรีวิว', () => {
  it('สร้าง URL ครั้งเดียวต่อภาพ และคืน URL เมื่อเปลี่ยนภาพหรือออกจากหน้าใน StrictMode', () => {
    const view = render(
      <StrictMode>
        <MemoryRouter>
          <Capture />
        </MemoryRouter>
      </StrictMode>,
    )
    const input = view.container.querySelector('input[type="file"]')!
    const select = (name: string) =>
      fireEvent.change(input, {
        target: { files: [new File(['sample'], name, { type: 'image/png' })] },
      })
    select('first.png')
    expect(createUrl).toHaveBeenCalledTimes(1)
    expect(revokeUrl).not.toHaveBeenCalled()
    const first = screen.getByAltText('ภาพที่เลือก').getAttribute('src')
    select('second.png')
    expect(createUrl).toHaveBeenCalledTimes(2)
    expect(revokeUrl).toHaveBeenCalledTimes(1)
    expect(revokeUrl).toHaveBeenLastCalledWith(first)
    const second = screen.getByAltText('ภาพที่เลือก').getAttribute('src')
    view.unmount()
    expect(revokeUrl).toHaveBeenCalledTimes(2)
    expect(revokeUrl).toHaveBeenLastCalledWith(second)
  })

  it('ใช้ source เปิดกล้องครั้งเดียวแล้วล้างจาก URL โดยเก็บพารามิเตอร์อื่น', async () => {
    render(
      <StrictMode>
        <MemoryRouter initialEntries={['/count?source=camera&keep=1']}>
          <Capture />
          <Location />
        </MemoryRouter>
      </StrictMode>,
    )
    expect(screen.getByRole('button', { name: 'ยกเลิกกล้อง' })).toBeTruthy()
    await waitFor(() =>
      expect(screen.getByLabelText('ที่อยู่ปัจจุบัน').textContent).toBe('/count?keep=1'),
    )
    fireEvent.click(screen.getByRole('button', { name: 'ยกเลิกกล้อง' }))
    expect(screen.queryByRole('button', { name: 'ยกเลิกกล้อง' })).toBeNull()
  })

  it('แยก unknown จากเหรียญที่ยังไม่ทราบชนิด โดยไม่แสดงมูลค่าเป็นศูนย์', async () => {
    const coin = (id: number, type: Coin['coin_type']): Coin => ({
      coin_id: id,
      center_xy: [50, 50],
      radius_px: 20,
      ellipse: null,
      color_group: 'unknown',
      coin_type: type,
      value_baht: type === 'THB_1' ? 1 : null,
      confidence: null,
      source: 'estimated',
      status: 'needs_confirmation',
      reason: null,
    })
    vi.mocked(getAnalysis).mockResolvedValue({
      analysis_id: 'test',
      result: {
        schema_version: '0.1.0',
        image_size: [100, 100],
        coins: [coin(0, 'THB_1'), coin(1, 'unknown'), coin(2, null)],
        total_baht: null,
        scale_mm_per_px: null,
        scale_source: null,
        status: 'needs_confirmation',
        reason: null,
        debug_images: {},
      },
    })
    render(
      <MemoryRouter>
        <Result />
      </MemoryRouter>,
    )
    const unknown = await screen.findByRole('row', { name: /ไม่ใช่เหรียญไทย/ })
    expect(unknown.textContent).toContain('1ระบุไม่ได้')
    expect(screen.getByRole('row', { name: /ยังไม่ทราบชนิด/ }).textContent).toContain('1ระบุไม่ได้')
    expect(screen.queryByText('0 บาท')).toBeNull()
    expect(screen.getAllByRole('row')).toHaveLength(4)
  })

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
