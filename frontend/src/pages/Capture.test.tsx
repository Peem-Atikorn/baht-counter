import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import Capture from './Capture'
import { createAnalysis } from '../api/client'

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

it.each([
  ['coins.heic', 'image/heic', 'image/heic'],
  ['coins.heif', 'image/heif', 'image/heif'],
  ['COINS.HEIC', '', 'image/heic'],
  ['coins.heif', 'application/octet-stream', 'image/heif'],
])('ส่งไฟล์ %s ต้นฉบับได้แม้พรีวิวไม่ได้ (%s)', async (name, type, expectedType) => {
  const file = new File(['original bytes'], name, { type })
  vi.mocked(createAnalysis)
    .mockRejectedValueOnce(new Error('ลองใหม่อีกครั้ง'))
    .mockResolvedValueOnce({ analysis_id: 'heic-result' } as Awaited<
      ReturnType<typeof createAnalysis>
    >)
  const view = render(
    <MemoryRouter>
      <Capture />
      <Location />
    </MemoryRouter>,
  )
  const input = view.container.querySelector('input[type="file"]')!
  expect(input.getAttribute('accept')).toContain('.heic')
  expect(input.getAttribute('accept')).toContain('image/heif')
  fireEvent.change(input, { target: { files: [file] } })
  fireEvent.error(screen.getByAltText('ภาพที่เลือก'))
  expect(screen.getByText(/กด “ใช้รูปนี้” เพื่อส่งไฟล์ต้นฉบับ/)).toBeTruthy()
  expect(screen.queryByAltText('ภาพที่เลือก')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'ใช้รูปนี้' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('alert').textContent).toContain('ลองใหม่อีกครั้ง')
  const sent = vi.mocked(createAnalysis).mock.calls[0][0] as File
  expect(sent.name).toBe(name)
  expect(sent.type).toBe(expectedType)
  expect(sent.size).toBe(file.size)
  // ข้อผิดพลาดจาก backend ต้องเก็บไฟล์ไว้ให้ลองใหม่ได้
  fireEvent.click(screen.getByRole('button', { name: 'ใช้รูปนี้' }))
  await waitFor(() =>
    expect(screen.getByLabelText('ที่อยู่ปัจจุบัน').textContent).toBe('/result/heic-result'),
  )
  expect(vi.mocked(createAnalysis).mock.calls[1][0]).toBe(sent)
})

it('เลือก JPEG ใหม่หลังพรีวิว HEIC ไม่ได้แล้วแสดงภาพใหม่ตามปกติ', () => {
  const view = render(
    <MemoryRouter>
      <Capture />
    </MemoryRouter>,
  )
  const input = view.container.querySelector('input[type="file"]')!
  fireEvent.change(input, {
    target: { files: [new File(['heic'], 'a.heic', { type: 'image/heic' })] },
  })
  fireEvent.error(screen.getByAltText('ภาพที่เลือก'))
  fireEvent.change(input, {
    target: { files: [new File(['jpeg'], 'b.jpg', { type: 'image/jpeg' })] },
  })
  expect(screen.queryByRole('status')).toBeNull()
  expect(screen.getByAltText('ภาพที่เลือก')).toBeTruthy()
})
