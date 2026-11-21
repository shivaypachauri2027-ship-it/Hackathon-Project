const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

// 129999 -> "₹1,29,999" (Indian digit grouping)
export const formatINR = (value) => inr.format(value)

// 45210 -> "45.2k"
export function formatCount(n) {
  if (n >= 100000) return `${(n / 100000).toFixed(1).replace(/\.0$/, '')}L`
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`
  return String(n)
}

// Friendly names for where the results came from (the backend sends `source`)
const SOURCES = {
  'json-file': 'JSON file',
  postgres: 'PostgreSQL',
  opensearch: 'OpenSearch',
}
export const sourceLabel = (source) => SOURCES[source] || source
