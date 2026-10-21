export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024
// ไม่รับ HEIC: backend ยังอ่านไม่ได้ และเมื่อไม่ระบุ HEIC ใน accept, Safari บน iPhone จะแปลงเป็น JPEG ให้เอง
export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** คืนข้อความภาษาไทยถ้าไฟล์ใช้ไม่ได้ */
export function validateImage(file: Blob): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return file.type === 'image/heic' || file.type === 'image/heif'
      ? 'ยังไม่รองรับไฟล์ HEIC กรุณาแปลงเป็น JPEG หรือถ่ายผ่านปุ่ม "ถ่ายรูป"'
      : 'รองรับเฉพาะไฟล์ภาพ JPEG, PNG หรือ WebP'
  }
  if (file.size > MAX_UPLOAD_BYTES) return 'ไฟล์ใหญ่เกิน 15 MB'
  return null
}

/** จับภาพจาก <video> ที่ความละเอียดเต็มของกล้อง ภาพที่ได้หันตามที่แสดงอยู่แล้ว ไม่ต้องอ่าน EXIF */
export function captureFrame(video: HTMLVideoElement): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  canvas.getContext('2d')!.drawImage(video, 0, 0)
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('จับภาพไม่สำเร็จ'))),
      'image/jpeg',
      0.95,
    ),
  )
}
