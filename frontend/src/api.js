// All calls to the FastAPI backend live here.
// In development BASE is '' and Vite forwards /api/... to http://127.0.0.1:8000.
const BASE = import.meta.env.VITE_API_URL || ''

const OFFLINE_MESSAGE =
  "Can't reach the InstaStock API. Make sure the backend is running: uvicorn app.main:app --reload --port 8000"

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error(OFFLINE_MESSAGE)
  }

  if (!res.ok) {
    let detail = null
    try {
      detail = (await res.json()).detail
    } catch {
      // The Vite proxy answers with an empty 5xx when the backend is down
    }
    if (!detail && res.status >= 500) throw new Error(OFFLINE_MESSAGE)
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
  return res.json()
}

// Drops empty values so the URL stays clean: /api/products?city=Pune&q=boat
function toQuery(params) {
  const clean = Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false)
  return new URLSearchParams(clean).toString()
}

export const api = {
  health: () => request('/api/health'),
  meta: () => request('/api/meta'),
  products: (params, signal) => request(`/api/products?${toQuery(params)}`, { signal }),
  product: (id, city) => request(`/api/products/${id}?${toQuery({ city })}`),
}
