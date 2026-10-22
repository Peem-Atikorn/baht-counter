import { expect, it } from 'vitest'
import { MAX_UPLOAD_BYTES, normalizeImage, validateImage } from './image'

it('ตรวจชนิดและขนาด HEIC/HEIF โดยไม่ยอมรับ MIME อื่นผ่านนามสกุล', () => {
  expect(validateImage(new File(['x'], 'photo.heic'))).toBeNull()
  expect(
    validateImage(new File(['x'], 'photo.HEIF', { type: 'application/octet-stream' })),
  ).toBeNull()
  expect(validateImage(new File(['x'], 'photo.heic', { type: 'text/plain' }))).not.toBeNull()
  expect(validateImage(new File(['x'], 'photo.gif', { type: 'image/gif' }))).not.toBeNull()
  expect(
    validateImage(new Blob([new Uint8Array(MAX_UPLOAD_BYTES)], { type: 'image/heic' })),
  ).toBeNull()
  expect(
    validateImage(new Blob([new Uint8Array(MAX_UPLOAD_BYTES + 1)], { type: 'image/heif' })),
  ).toBe('ไฟล์ใหญ่เกิน 15 MB')
})

it('เติม MIME โดยไม่เปลี่ยน bytes ชื่อ หรือวันแก้ไขไฟล์ต้นฉบับ', async () => {
  const file = new File(['original bytes'], 'photo.heic', { lastModified: 1234 })
  const normalized = normalizeImage(file) as File
  expect(normalized.type).toBe('image/heic')
  expect(normalized.name).toBe(file.name)
  expect(normalized.lastModified).toBe(file.lastModified)
  const read = (blob: Blob) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = reject
      reader.readAsArrayBuffer(blob)
    })
  expect(await read(normalized)).toEqual(await read(file))
  const jpeg = new File(['jpeg'], 'photo.jpg', { type: 'image/jpeg' })
  expect(normalizeImage(jpeg)).toBe(jpeg)
})
