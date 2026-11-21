// Plain-words search: turns "earphones under 2000 in Pune" into filters.
// This is a small RULE-BASED parser (regular expressions), not AI:
// it looks for prices, cities, categories, "in stock" and sort words,
// and whatever is left becomes the search text for OpenSearch.

const CITIES = {
  bengaluru: 'Bengaluru', bangalore: 'Bengaluru', blr: 'Bengaluru',
  mumbai: 'Mumbai', bombay: 'Mumbai',
  delhi: 'Delhi', 'new delhi': 'Delhi',
  pune: 'Pune',
  hyderabad: 'Hyderabad', hyd: 'Hyderabad',
  chennai: 'Chennai', madras: 'Chennai',
}

const CATEGORIES = {
  audio: 'Audio',
  mobiles: 'Mobiles', mobile: 'Mobiles', phones: 'Mobiles', phone: 'Mobiles', smartphones: 'Mobiles',
  electronics: 'Electronics',
  fashion: 'Fashion', clothes: 'Fashion',
  kitchen: 'Home & Kitchen', home: 'Home & Kitchen',
  grocery: 'Grocery', groceries: 'Grocery',
  beauty: 'Beauty', makeup: 'Beauty',
  sports: 'Sports', fitness: 'Sports',
}

const SORTS = [
  [/\b(cheapest|lowest price|low to high)\b/, 'price_asc', 'Cheapest first'],
  [/\b(costliest|most expensive|high to low)\b/, 'price_desc', 'Most expensive first'],
  [/\b(best rated|top rated|highest rated)\b/, 'rating', 'Best rated first'],
  [/\b(best deals?|biggest discounts?|on sale|offers?)\b/, 'discount', 'Biggest discount first'],
]

const FILLER = /\b(show|me|find|i|want|need|buy|get|for|the|a|an|some|please|with|of|rs|rupees|inr|products?|items?|in|at|near|from|and|on)\b/g

const MONEY = String.raw`(?:₹|rs\.?|inr)?\s*(\d[\d,]*)\s*(k)?`
const toRupees = (digits, k) => Number(digits.replace(/,/g, '')) * (k ? 1000 : 1)

export function parseQuery(input) {
  let text = ` ${input.toLowerCase()} `
  const result = { text: '', city: null, category: null, min: null, max: null, inStock: false, sort: null, understood: [] }

  const take = (re, fn) => {
    const m = text.match(re)
    if (m) {
      fn(m)
      text = text.replace(m[0], ' ')
    }
  }

  // Prices: "between 500 and 2000", "under 2k", "above ₹10,000"
  take(new RegExp(String.raw`\bbetween\s*${MONEY}\s*(?:and|to|-)\s*${MONEY}`), (m) => {
    result.min = toRupees(m[1], m[2])
    result.max = toRupees(m[3], m[4])
  })
  take(new RegExp(String.raw`\b(?:under|below|less than|upto|up to|within|max|cheaper than)\s*${MONEY}`), (m) => {
    result.max = toRupees(m[1], m[2])
  })
  take(new RegExp(String.raw`\b(?:above|over|more than|min|at least)\s*${MONEY}`), (m) => {
    result.min = toRupees(m[1], m[2])
  })

  // Availability and sort words
  take(/\b(in stock|available)\b/, () => {
    result.inStock = true
  })
  for (const [re, sort, label] of SORTS) {
    take(re, () => {
      result.sort = sort
      result.understood.push(label)
    })
  }

  // City (longest names first so "new delhi" wins over "delhi")
  for (const name of Object.keys(CITIES).sort((a, b) => b.length - a.length)) {
    take(new RegExp(String.raw`\b(?:in|at|near|from)?\s*${name}\b`), () => {
      result.city = CITIES[name]
      result.inStock = true // "… in Pune" means: available in Pune
    })
  }

  // Category words
  for (const word of Object.keys(CATEGORIES)) {
    take(new RegExp(String.raw`\b${word}\b`), () => {
      result.category = CATEGORIES[word]
    })
  }

  result.text = text.replace(FILLER, ' ').replace(/[^\p{L}\p{N}\s+-]/gu, ' ').replace(/\s+/g, ' ').trim()

  // Labels shown to the shopper ("Understood: …")
  const inr = (n) => `₹${n.toLocaleString('en-IN')}`
  const labels = []
  if (result.text) labels.push(`“${result.text}”`)
  if (result.category) labels.push(result.category)
  if (result.min !== null && result.max !== null) labels.push(`${inr(result.min)} to ${inr(result.max)}`)
  else if (result.max !== null) labels.push(`Under ${inr(result.max)}`)
  else if (result.min !== null) labels.push(`Above ${inr(result.min)}`)
  if (result.city) labels.push(`In stock in ${result.city}`)
  else if (result.inStock) labels.push('In stock only')
  result.understood = [...labels, ...result.understood]

  result.changed =
    result.city !== null || result.category !== null || result.min !== null ||
    result.max !== null || result.inStock || result.sort !== null
  return result
}
