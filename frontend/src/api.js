// All calls to the FastAPI backend live here.
// In development BASE is '' and Vite forwards /api/... to http://127.0.0.1:8000.
const BASE = import.meta.env.VITE_API_URL || ''

const OFFLINE_MESSAGE =
  "Can't reach the InstaStock API. Make sure the backend is running: python -m uvicorn app.main:app --reload --port 8000"

// Turns any error body from FastAPI into one readable sentence
function readableDetail(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors (422): [{loc: [..., 'phone'], msg: '...'}]
    return detail.map((d) => `${d.loc?.[d.loc.length - 1] ?? 'field'}: ${d.msg.replace(/^Value error, /, '')}`).join('; ')
  }
  return null
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error(OFFLINE_MESSAGE)
  }

  if (!res.ok) {
    let body = null
    try {
      body = await res.json()
    } catch {
      // The Vite proxy answers with an empty 5xx when the backend is down
    }
    const message = readableDetail(body?.detail)
    if (!message && res.status >= 500) throw new Error(OFFLINE_MESSAGE)
    const error = new Error(message || `Request failed (${res.status})`)
    error.status = res.status
    error.problems = body?.problems || [] // out-of-stock details from checkout
    throw error
  }
  return res.json()
}

// Drops empty values so the URL stays clean: /api/products?city=Pune&q=boat
function toQuery(params) {
  const clean = Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false)
  return new URLSearchParams(clean).toString()
}

const postJSON = (path, body) =>
  request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  health: () => request('/api/health'),
  meta: () => request('/api/meta'),
  products: (params, signal) => request(`/api/products?${toQuery(params)}`, { signal }),
  product: (id, city) => request(`/api/products/${id}?${toQuery({ city })}`),
  placeOrder: (order) => postJSON('/api/orders', order),
  order: (orderNumber) => request(`/api/orders/${encodeURIComponent(orderNumber)}`),
  recentOrders: (limit = 20) => request(`/api/orders?limit=${limit}`),
  events: (limit = 25) => request(`/api/events?limit=${limit}`),
  // Phase 6 demo tools
  changeStock: (change) => postJSON('/api/admin/stock', change),
  syncStatus: (productId, city) => request(`/api/admin/sync-status/${productId}?${toQuery({ city })}`),
}
