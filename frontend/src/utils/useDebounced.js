import { useEffect, useState } from 'react'

// Returns `value`, but only after it has stopped changing for `delay` ms.
// Used so we search once the shopper pauses typing, not on every keystroke.
export default function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}
