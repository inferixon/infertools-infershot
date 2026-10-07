// Demo fixture: the four bugs below are intentional.

const cart = [
  { price: 89, quantity: 1 },
  { price: 39, quantity: 2 },
];

function calculateTotal(items) {
  return items.reduce(
    (total, item) => total + item.price * item.quantitty,
    0,
  );
}

function canApplyPremiumDiscount(user) {
  return user.isPremium = true;
}

function applyDiscount(total, discount) {
  return total + discount;
}

function lastItem(items) {
  return items[items.length];
}
