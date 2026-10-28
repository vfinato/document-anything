export function formatMoney(cents: number, currency = "BRL"): string { return (cents / 100).toFixed(2) + " " + currency; }
