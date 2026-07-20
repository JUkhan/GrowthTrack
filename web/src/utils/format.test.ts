import { describe, expect, it } from 'vitest'
import { formatCrBdt, formatPercent } from './format'

describe('formatCrBdt', () => {
  it('formats a positive amount in Cr BDT', () => {
    expect(formatCrBdt('12000000.00')).toBe('1.2 Cr')
  })

  it('formats a negative amount (e.g. a refund/correction) in Cr BDT', () => {
    expect(formatCrBdt('-5000000.00')).toBe('-0.5 Cr')
  })

  it('returns an em dash for a malformed/non-numeric value instead of "NaN Cr"', () => {
    expect(formatCrBdt('not-a-number')).toBe('—')
  })
})

describe('formatPercent', () => {
  it('rounds a positive percentage to the nearest whole number', () => {
    expect(formatPercent('45.00')).toBe('45%')
  })

  it('rounds a negative percentage (growth can decline) to the nearest whole number', () => {
    expect(formatPercent('-12.60')).toBe('-13%')
  })

  it('returns an em dash for a malformed/non-numeric value instead of "NaN%"', () => {
    expect(formatPercent('not-a-number')).toBe('—')
  })
})
