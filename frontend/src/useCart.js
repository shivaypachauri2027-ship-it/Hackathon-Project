import { useEffect, useMemo, useState } from 'react'

// The shopping cart lives in the browser (and in localStorage, so a page refresh
// keeps it). Stock is only checked for real by the server at checkout.
const KEY = 'instastock.cart'
const MAX_PER_ITEM = 10

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || []
  } catch {
    return []
  }
}

export default function useCart() {
  const [items, setItems] = useState(load)

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(items))
    } catch {
      // storage full or private mode: the cart still works for this visit
    }
  }, [items])

  function add(product) {
    setItems((prev) => {
      const max = Math.min(MAX_PER_ITEM, product.stock_in_city)
      const existing = prev.find((i) => i.id === product.id)
      if (existing) {
        return prev.map((i) => (i.id === product.id ? { ...i, max, quantity: Math.min(i.quantity + 1, max) } : i))
      }
      const { id, name, brand, price, mrp, image_url } = product
      return [...prev, { id, name, brand, price, mrp, image_url, max, quantity: 1 }]
    })
  }

  function setQuantity(id, quantity) {
    setItems((prev) =>
      quantity <= 0
        ? prev.filter((i) => i.id !== id)
        : prev.map((i) => (i.id === id ? { ...i, quantity: Math.min(quantity, i.max ?? MAX_PER_ITEM) } : i)),
    )
  }

  // After a 409 "not enough stock": shrink each line to what is really available
  function applyAvailability(problems) {
    setItems((prev) =>
      prev
        .map((i) => {
          const p = problems.find((x) => x.product_id === i.id)
          return p ? { ...i, quantity: Math.min(i.quantity, p.available), max: p.available } : i
        })
        .filter((i) => i.quantity > 0),
    )
  }

  const remove = (id) => setItems((prev) => prev.filter((i) => i.id !== id))
  const clear = () => setItems([])

  const summary = useMemo(() => {
    const quantities = {}
    let count = 0
    let subtotal = 0
    let mrpTotal = 0
    for (const i of items) {
      quantities[i.id] = i.quantity
      count += i.quantity
      subtotal += i.price * i.quantity
      mrpTotal += i.mrp * i.quantity
    }
    return { quantities, count, subtotal, savings: mrpTotal - subtotal }
  }, [items])

  return { items, add, setQuantity, applyAvailability, remove, clear, ...summary }
}
