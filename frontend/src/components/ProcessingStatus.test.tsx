import { StrictMode } from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ProcessingStatus from './ProcessingStatus'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

it('บอกเหตุผลเมื่อรอนาน โดยไม่อ้างเปอร์เซ็นต์หรือขั้นตอนจากเซิร์ฟเวอร์', () => {
  vi.useFakeTimers()
  render(
    <StrictMode>
      <ProcessingStatus />
    </StrictMode>,
  )
  const status = screen.getByRole('status', { name: 'สถานะการนับเหรียญ' })
  expect(status.textContent).toContain('กำลังส่งภาพและรอผลการนับ')
  act(() => vi.advanceTimersByTime(15_000))
  expect(status.textContent).toContain('ใช้เวลานานกว่าปกติ')
  act(() => vi.advanceTimersByTime(30_000))
  expect(status.textContent).toContain('ระบบอาจกำลังเริ่มทำงานหลังพัก')
  expect(status.textContent).toContain('ไม่ต้องกดส่งซ้ำ')
  expect(status.textContent).not.toContain('%')
})

it('ล้างตัวจับเวลาเมื่อจบการรอ และเริ่มข้อความใหม่เมื่อส่งครั้งถัดไป', () => {
  vi.useFakeTimers()
  const first = render(<ProcessingStatus />)
  act(() => vi.advanceTimersByTime(45_000))
  first.unmount()
  expect(vi.getTimerCount()).toBe(0)
  const next = render(<ProcessingStatus />)
  expect(screen.getByRole('status').textContent).toContain('กำลังส่งภาพและรอผลการนับ')
  next.unmount()
  expect(vi.getTimerCount()).toBe(0)
})
