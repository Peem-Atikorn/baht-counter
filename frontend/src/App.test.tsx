import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import App from './App'
afterEach(cleanup)
it.each(['/missing', '/result', '/result/a/extra'])('หน้า %s ใช้หัวข้อไม่พบหน้านี้', (path) => {
  window.history.replaceState(null, '', path)
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'ไม่พบหน้านี้' })).toBeTruthy()
  expect(screen.queryByRole('heading', { level: 1, name: 'ผลการนับเหรียญ' })).toBeNull()
})
