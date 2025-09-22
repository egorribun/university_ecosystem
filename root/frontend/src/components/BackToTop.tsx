import { useEffect, useState, useCallback } from "react";

export default function BackToTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 420);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const onClick = useCallback(() => {
    try { window.scrollTo({ top: 0, behavior: "smooth" }); } catch { window.scrollTo(0, 0); }
  }, []);
  return (
    <button
      type="button"
      className={"back-to-top" + (show ? " visible" : "")}
      aria-label="Наверх"
      onClick={onClick}
    >
      ↑
    </button>
  );
}