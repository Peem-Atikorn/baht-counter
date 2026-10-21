import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import Capture from './Capture'

vi.mock('../api/client', () => ({ createAnalysis: vi.fn() }))
vi.mock('../components/Camera', () => ({
  default: ({ onCancel }: { onCancel: () => void }) => (
    <button onClick={onCancel}>ยกเลิกกล้อง</button>
  ),
}))
let sequence = 0
const createUrl = vi.fn(() => `blob:preview-${++sequence}`)
const revokeUrl = vi.fn()
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
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
describe('ถ่ายและอัปโหลดภาพ', () => {
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
})
