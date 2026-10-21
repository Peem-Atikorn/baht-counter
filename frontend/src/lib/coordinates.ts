/** ภาพและ SVG ใช้อัตราส่วนเดียวกัน จึงแปลงจากกรอบ SVG เป็นพิกัดภาพต้นฉบับได้โดยตรง */
export function imageCoordinates(
  point: { x: number; y: number },
  bounds: { left: number; top: number; width: number; height: number },
  imageSize: [number, number],
): [number, number] | null {
  if (bounds.width <= 0 || bounds.height <= 0) return null
  const x = ((point.x - bounds.left) / bounds.width) * imageSize[0]
  const y = ((point.y - bounds.top) / bounds.height) * imageSize[1]
  if (x < 0 || y < 0 || x >= imageSize[0] || y >= imageSize[1]) return null
  return [x, y]
}
