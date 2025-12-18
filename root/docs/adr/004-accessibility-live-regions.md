# ADR 004: Accessibility LiveRegion Provider

**Status**: Accepted  
**Date**: 2024-12-18

## Context

Screen reader users need to be informed of dynamic content changes (form submissions, errors, loading states) that occur without page reload. Without proper ARIA live regions, these updates are invisible to assistive technology.

Common issues:
- Toast notifications not announced
- Form validation errors not read
- Loading state changes silent
- Success/failure feedback missing

## Decision

Create a global `LiveRegionProvider` component and `useAnnouncer` hook for centralized screen reader announcements.

### Architecture

```tsx
<LiveRegionProvider>
  <App />
</LiveRegionProvider>

// In any component:
const { announce } = useAnnouncer()
announce("Form submitted successfully", "polite")
```

### Implementation Details

1. **Two Live Region Types**:
   - `polite`: Non-urgent updates (read when user is idle)
   - `assertive`: Urgent updates (interrupts current speech)

2. **Portal Rendering**:
   - Regions rendered via `createPortal` to `document.body`
   - Ensures consistent DOM position

3. **Auto-Clear**:
   - Messages cleared after 3 seconds
   - Prevents stale announcements

4. **Visual Hiding**:
   - Uses `sr-only` class (visually hidden, screen reader visible)
   - No visual UI impact

### Code Structure

```tsx
// LiveRegionProvider.tsx
<div role="status" aria-live="polite" className="sr-only">
  {politeMessage}
</div>
<div role="alert" aria-live="assertive" className="sr-only">
  {assertiveMessage}
</div>
```

## Consequences

### Positive
- Centralized announcement system
- Consistent screen reader experience
- Easy to use hook API
- No visual UI changes needed

### Negative
- Requires app-wide provider wrapper
- Developers must remember to announce important actions
- Message timing requires coordination

### Usage Guidelines
- Use `polite` for success messages, status updates
- Use `assertive` for errors, critical alerts
- Keep messages concise and actionable
- Test with actual screen readers (NVDA, VoiceOver)
