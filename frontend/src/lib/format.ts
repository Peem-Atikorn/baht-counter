export function baht(value: number | null | undefined) {
  return value == null
    ? 'ระบุไม่ได้'
    : `${value.toLocaleString('th-TH', { maximumFractionDigits: 2 })} บาท`
}

export const STATUS_TH = {
  ok: 'นับเรียบร้อย',
  needs_confirmation: 'รอยืนยันชนิดเหรียญ',
  failed: 'ประมวลผลไม่สำเร็จ',
} as const

export function thaiDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? 'ไม่ทราบวันที่'
    : date.toLocaleString('th-TH', {
        timeZone: 'Asia/Bangkok',
        dateStyle: 'medium',
        timeStyle: 'short',
      })
}
