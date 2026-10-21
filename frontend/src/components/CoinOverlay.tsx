import type { Coin, CoinTypeInfo, CountResult } from '../api/client'
import { imageCoordinates } from '../lib/coordinates'

type Props = {
  result: CountResult
  types: CoinTypeInfo[]
  selectedId: number | null
  adding: boolean
  busy: boolean
  onSelect: (coin: Coin) => void
  onAdd: (xy: [number, number]) => void
}

export default function CoinOverlay({
  result,
  types,
  selectedId,
  adding,
  busy,
  onSelect,
  onAdd,
}: Props) {
  const [w, h] = result.image_size
  return (
    <svg
      className={`coin-overlay ${adding ? 'is-adding' : ''}`}
      viewBox={`0 0 ${w} ${h}`}
      aria-label={
        adding
          ? 'กดตำแหน่งในภาพเพื่อเพิ่มเหรียญ หรือใช้ช่องพิกัดด้านล่าง'
          : 'ตำแหน่งเหรียญ เลือกเหรียญเพื่อแก้ผล'
      }
      onClick={(event) => {
        if (!adding || busy) return
        const point = imageCoordinates(
          { x: event.clientX, y: event.clientY },
          event.currentTarget.getBoundingClientRect(),
          [w, h],
        )
        if (point) onAdd(point)
      }}
    >
      {result.coins.map((coin, index) => {
        const type = types.find((t) => t.code === coin.coin_type)
        const label =
          type?.name_th ?? (coin.coin_type === 'unknown' ? 'ไม่ใช่เหรียญไทย' : 'ยังไม่ทราบชนิด')
        const [x, y] = coin.center_xy
        const ellipse = coin.ellipse
        return (
          <g
            key={coin.coin_id}
            role="button"
            tabIndex={busy ? -1 : 0}
            aria-label={`เหรียญ ${index + 1}: ${label}`}
            aria-pressed={selectedId === coin.coin_id}
            aria-disabled={busy}
            className="coin-target"
            onClick={(event) => {
              if (adding) return
              event.stopPropagation()
              if (!busy) onSelect(coin)
            }}
            onKeyDown={(event) => {
              if ((event.key === 'Enter' || event.key === ' ') && !busy) {
                event.preventDefault()
                onSelect(coin)
              }
            }}
          >
            <ellipse
              cx={x}
              cy={y}
              rx={ellipse ? ellipse[0] / 2 : coin.radius_px}
              ry={ellipse ? ellipse[1] / 2 : coin.radius_px}
              transform={ellipse ? `rotate(${ellipse[2]} ${x} ${y})` : undefined}
              fill={selectedId === coin.coin_id ? '#fff4c566' : '#ffffff12'}
              stroke={selectedId === coin.coin_id ? '#3c2920' : (type?.display_color ?? '#93432d')}
              strokeWidth={selectedId === coin.coin_id ? 4 : 2.5}
              strokeDasharray={coin.value_baht == null ? '5 3' : undefined}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={Math.max(14, w * 0.025)}
              fill="#fff"
              stroke="#3c2920"
              strokeWidth={Math.max(2, w * 0.003)}
              paintOrder="stroke"
              aria-hidden="true"
            >
              {coin.value_baht == null ? '?' : `฿${coin.value_baht}`}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
