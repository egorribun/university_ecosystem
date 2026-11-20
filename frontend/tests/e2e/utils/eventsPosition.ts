/** Check the selected card's actual entrance transform before comparing offsets. */
export const isStaggerRowSettled = (element: Element): boolean => {
  const wrapper = element.closest(".css-stagger-item")
  if (!wrapper) {
    throw new Error("the selected event must be inside a staggered row")
  }

  const transform = getComputedStyle(wrapper).transform
  const translateY = transform === "none" ? 0 : new DOMMatrixReadOnly(transform).m42
  return translateY === 0
}
