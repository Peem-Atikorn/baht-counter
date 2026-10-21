type Name =
  'home' | 'scan' | 'book' | 'help' | 'arrow' | 'camera' | 'upload' | 'check' | 'sun' | 'layers'
const paths: Record<Name, string> = {
  home: 'm3 10 9-7 9 7M5 9v12h5v-7h4v7h5V9',
  scan: 'M8 3H4a1 1 0 0 0-1 1v4m13-5h4a1 1 0 0 1 1 1v4M3 16v4a1 1 0 0 0 1 1h4m8 0h4a1 1 0 0 0 1-1v-4M8 12h8m-4-4v8',
  book: 'M12 6c-3-2-6-2-9-1v15c3-1 6-1 9 1m0-15c3-2 6-2 9-1v15c-3-1-6-1-9 1V6',
  help: 'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4m0 3h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  arrow: 'M5 12h14m-6-6 6 6-6 6',
  camera: 'M8 5 6 8H3v12h18V8h-3l-2-3H8m8 9a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  upload: 'M12 16V3m-5 5 5-5 5 5M3 15v5a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-5',
  check: 'm5 12 4 4L19 6',
  sun: 'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5m-2 7a5 5 0 1 1-10 0 5 5 0 0 1 10 0',
  layers: 'm12 3 10 5-10 5L2 8l10-5M2 12l10 5 10-5M2 16l10 5 10-5',
}
export default function Icon({ name, className = '' }: { name: Name; className?: string }) {
  return (
    <svg
      className={`icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  )
}
