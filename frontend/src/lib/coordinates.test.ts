import { describe, expect, it } from 'vitest'
import { imageCoordinates } from './coordinates'
describe('พิกัดเหรียญบนภาพที่ถูกย่อ', () => {
  it('หักตำแหน่งกรอบแล้วแปลงกลับเป็นพิกัดภาพต้นฉบับ', () => {
    expect(
      imageCoordinates(
        { x: 150, y: 125 },
        { left: 50, top: 50, width: 400, height: 300 },
        [1600, 1200],
      ),
    ).toEqual([400, 300])
  })
  it('ไม่ส่งพิกัดนอกภาพหรือกรอบที่ไม่มีขนาด', () => {
    const bounds = { left: 50, top: 50, width: 400, height: 300 }
    expect(imageCoordinates({ x: 49, y: 50 }, bounds, [800, 600])).toBeNull()
    expect(imageCoordinates({ x: 450, y: 350 }, bounds, [800, 600])).toBeNull()
    expect(imageCoordinates({ x: 50, y: 50 }, { ...bounds, width: 0 }, [800, 600])).toBeNull()
  })
})
