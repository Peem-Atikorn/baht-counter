import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import {
  addCoin,
  deleteCoin,
  exportAnalysis,
  getAnalysis,
  getCoinTypes,
  updateCoin,
} from '../api/client'
import { saveDownload } from '../lib/download'
import { analysis, coin, types } from '../test/fixtures'
import Result from './Result'

vi.mock('../api/client', () => ({
  getAnalysis: vi.fn(),
  getCoinTypes: vi.fn(),
  updateCoin: vi.fn(),
  addCoin: vi.fn(),
  deleteCoin: vi.fn(),
  exportAnalysis: vi.fn(),
  imageUrl: () => '/sample.png',
}))
vi.mock('../lib/download', () => ({ saveDownload: vi.fn() }))
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getCoinTypes).mockResolvedValue(types)
  vi.mocked(getAnalysis).mockResolvedValue(analysis())
})
afterEach(cleanup)
function open() {
  return render(
    <MemoryRouter initialEntries={['/result/test']}>
      <Routes>
        <Route path="/result/:id" element={<Result />} />
      </Routes>
    </MemoryRouter>,
  )
}
async function selectFirst() {
  fireEvent.click(await screen.findByRole('button', { name: 'เหรียญ 1: หนึ่งบาทจาก API' }))
}

describe('ผลการนับและการแก้เหรียญ', () => {
  it('บอกวิธีรวมยอดเมื่อ backend ยืนยัน unknown เป็น ok แต่ยอดยังเป็น null', async () => {
    const data = analysis([{ ...coin(0, 'unknown'), status: 'ok', source: 'user_edited' }])
    data.result.status = 'ok'
    vi.mocked(getAnalysis).mockResolvedValue(data)
    open()
    expect(await screen.findByText('ยังรวมยอดไม่ได้')).toBeTruthy()
    expect(screen.getByText('มีวัตถุที่ไม่ใช่เหรียญไทย 1 ชิ้น ลบออกเพื่อรวมยอด')).toBeTruthy()
    expect(screen.queryByText('นับเรียบร้อย')).toBeNull()
  })
  it('ไม่เพิ่มเหรียญตรงมุมภาพโดยอัตโนมัติเมื่อยังไม่กรอกพิกัด', async () => {
    open()
    fireEvent.click(await screen.findByRole('button', { name: 'เพิ่มเหรียญที่ยังไม่ถูกนับ' }))
    expect((screen.getByLabelText('พิกัด X (พิกเซล)') as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText('พิกัด Y (พิกเซล)') as HTMLInputElement).value).toBe('')
    fireEvent.click(screen.getByRole('button', { name: 'เพิ่มที่พิกัดนี้' }))
    expect(addCoin).not.toHaveBeenCalled()
  })
  it('แสดง unknown แยกจากชนิดที่ยังไม่ทราบ และไม่แทนค่าด้วยศูนย์', async () => {
    vi.mocked(getAnalysis).mockResolvedValue(analysis([coin(0), coin(1, 'unknown'), coin(2, null)]))
    open()
    expect((await screen.findByRole('row', { name: /ไม่ใช่เหรียญไทย/ })).textContent).toContain(
      '1ระบุไม่ได้',
    )
    expect(screen.getByRole('row', { name: /ยังไม่ทราบชนิด/ }).textContent).toContain('1ระบุไม่ได้')
    expect(screen.queryByText('0 บาท')).toBeNull()
    expect(screen.getAllByRole('row')).toHaveLength(4)
  })
  it('เก็บผลเดิมเมื่อบันทึกล้มเหลว และอัปเดตทั้งภาพจากคำตอบ API เมื่อลองใหม่', async () => {
    const edited = { ...coin(0, 'THB_5'), source: 'user_edited' as const, status: 'ok' as const }
    vi.mocked(updateCoin)
      .mockRejectedValueOnce(new Error('บันทึกไม่สำเร็จ'))
      .mockResolvedValueOnce(analysis([edited]))
    open()
    await selectFirst()
    fireEvent.change(screen.getByLabelText('ชนิดเหรียญ'), { target: { value: 'THB_5' } })
    fireEvent.click(screen.getByRole('button', { name: 'ยืนยันชนิดเหรียญ' }))
    expect((await screen.findByRole('alert')).textContent).toContain('บันทึกไม่สำเร็จ')
    expect(screen.getByRole('row', { name: /หนึ่งบาทจาก API/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'ยืนยันชนิดเหรียญ' }))
    await waitFor(() =>
      expect(screen.getByRole('row', { name: /5 บาท/ }).textContent).toContain('15 บาท'),
    )
    expect(updateCoin).toHaveBeenLastCalledWith('test', 0, 'THB_5')
    expect(screen.getByText('แก้ไขแล้ว')).toBeTruthy()
  })
  it('ลบเหรียญสุดท้ายแล้วแสดงผลล้มเหลวและยอดระบุไม่ได้', async () => {
    vi.mocked(deleteCoin).mockResolvedValue(analysis([]))
    open()
    await selectFirst()
    fireEvent.click(screen.getByRole('button', { name: 'ลบเหรียญนี้' }))
    fireEvent.click(screen.getByRole('button', { name: 'ยืนยันลบเหรียญ' }))
    await waitFor(() => expect(deleteCoin).toHaveBeenCalledWith('test', 0))
    await screen.findByText('ประมวลผลไม่สำเร็จ')
    expect(screen.getByText('ระบุไม่ได้')).toBeTruthy()
    expect(screen.queryByText('0 บาท')).toBeNull()
  })
  it('เพิ่มเหรียญด้วยพิกัดต้นฉบับและเปิดให้เลือกชนิดเหรียญใหม่', async () => {
    vi.mocked(addCoin).mockResolvedValue(
      analysis([coin(0), { ...coin(1, null), source: 'user_added' }]),
    )
    open()
    await screen.findByText('ตรวจผลการนับ')
    fireEvent.click(screen.getByRole('button', { name: 'เพิ่มเหรียญที่ยังไม่ถูกนับ' }))
    fireEvent.change(screen.getByLabelText('พิกัด X (พิกเซล)'), { target: { value: '123' } })
    fireEvent.change(screen.getByLabelText('พิกัด Y (พิกเซล)'), { target: { value: '234' } })
    fireEvent.click(screen.getByRole('button', { name: 'เพิ่มที่พิกัดนี้' }))
    expect(await screen.findByRole('heading', { name: 'แก้เหรียญ 2' })).toBeTruthy()
    expect(addCoin).toHaveBeenCalledWith('test', [123, 234])
    expect(screen.getByText('เพิ่มเอง')).toBeTruthy()
  })
  it('ดาวน์โหลดผลล่าสุด และแสดงข้อผิดพลาดแทนการดาวน์โหลดไฟล์เสีย', async () => {
    const blob = new Blob(['test'])
    vi.mocked(exportAnalysis)
      .mockResolvedValueOnce(blob)
      .mockRejectedValueOnce(new Error('ดาวน์โหลดไม่สำเร็จ'))
    open()
    await screen.findByText('ตรวจผลการนับ')
    fireEvent.click(screen.getByRole('button', { name: 'ดาวน์โหลด JSON' }))
    await waitFor(() => expect(saveDownload).toHaveBeenCalledWith(blob, 'test.json'))
    fireEvent.click(screen.getByRole('button', { name: 'ดาวน์โหลด CSV' }))
    expect((await screen.findByRole('alert')).textContent).toContain('ดาวน์โหลดไม่สำเร็จ')
    expect(saveDownload).toHaveBeenCalledTimes(1)
  })
})
