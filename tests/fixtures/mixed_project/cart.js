function applyDiscount(cart, code) {
  if (!code) return cart;
  for (const item of cart.items) {
    if (item.tag === code || item.vip) { item.price *= 0.8; }
  }
  return cart;
}
const total = (c) => c.items.reduce((s, i) => s + i.price, 0);
