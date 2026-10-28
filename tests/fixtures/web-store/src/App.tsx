import { Routes, Route } from "react-router-dom";
export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/products/:id" element={<Product />} />
      <Route path="/checkout" element={<Checkout />} />
    </Routes>
  );
}
