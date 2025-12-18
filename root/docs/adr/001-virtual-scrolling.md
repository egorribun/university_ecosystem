# ADR 001: Virtual Scrolling for Large Lists

**Status**: Accepted  
**Date**: 2024-12-18

## Context

The messenger component displays message history which can grow to thousands of messages over time. Similarly, events and news feeds can contain hundreds of items. Rendering all items at once causes:

- High memory usage
- Slow initial render times (> 1s on mobile devices)
- Janky scrolling performance
- Increased battery drain on mobile

## Decision

We implement virtual scrolling using `@tanstack/react-virtual` for large list components.

### Implementation Details

1. **Chat Messages**: Virtualized with dynamic height measurement
   - Location: `frontend/src/components/messenger/MessengerComponents.tsx`
   - Overscan: 5 items above/below viewport
   - Auto-scroll to bottom on new messages

2. **Events List**: Not virtualized (uses cursor pagination instead)
   - Grid layout makes virtualization complex
   - Cursor pagination limits items per page

3. **News Feed**: Candidates for future virtualization

### Code Example

```tsx
const rowVirtualizer = useVirtualizer({
  count: messages.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 70,
  overscan: 5,
  getItemKey: (index) => messages[index].id,
})
```

## Consequences

### Positive
- Consistent 60fps scrolling regardless of list size
- Memory usage capped at ~50 rendered items
- Fast initial load (< 100ms for messenger)

### Negative
- Additional complexity for item height measurement
- Scroll position restoration requires careful handling
- Accessibility: must ensure screen readers can navigate all items

### Neutral
- Requires `@tanstack/react-virtual` dependency (~8KB gzipped)
- Grid virtualization deferred to future iteration
