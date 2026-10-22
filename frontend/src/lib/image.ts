export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024
export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif']
export const IMAGE_ACCEPT = [...ACCEPTED_TYPES, '.heic', '.heif'].join(',')

/** บางเครื่องไม่ระบุ MIME ของ HEIC จึงใช้ชื่อไฟล์เฉพาะเมื่อ MIME ว่างหรือเป็น binary */
function imageType(file: Blob): string {
  if ((!file.type || file.type === 'application/octet-stream') && file instanceof File) {
    if (/\.heic$/i.test(file.name)) return 'image/heic'
    if (/\.heif$/i.test(file.name)) return 'image/heif'
  }
  return file.type
}

/** คงชื่อและ bytes ต้นฉบับ เปลี่ยนเฉพาะ MIME ที่ส่งให้ backend */
export function normalizeImage(file: Blob): Blob {
  const type = imageType(file)
  return type !== file.type && file instanceof File
    ? new File([file], file.name, { type, lastModified: file.lastModified })
    : file
}

/** คืนข้อความภาษาไทยถ้าไฟล์ใช้ไม่ได้ */
export function validateImage(file: Blob): string | null {
  if (!ACCEPTED_TYPES.includes(imageType(file))) {
    return 'รองรับเฉพาะไฟล์ภาพ JPEG, PNG, WebP, HEIC หรือ HEIF'
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
