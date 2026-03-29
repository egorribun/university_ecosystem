# Wave 36 — UI/UX Polish Design: Premium Glass + Motion

## Direction
Premium Glass aesthetic (Arc Browser / Vercel Dashboard style). Combines Depth Layers (visual) with Motion First (interaction) approaches.

## Sections

### 1. Glass Morphism 2.0 — Depth Layers
- 4-layer depth system: Background (0) → Surface (blur-8) → Elevated (blur-16) → Floating (blur-24)
- Noise texture overlay via SVG `feTurbulence` filter (frosted glass effect, 0 JS, ~300 bytes)
- Aurora mesh background on Dashboard via CSS `@property` animated gradient (20s hue-rotate)
- Apply glass effects consistently to modals, dropdowns, toasts (currently cards only)

### 2. Micro-Interactions
- Button ripple: CSS-only via `::after` + `@keyframes ripple` on `:active`
- Input focus glow: Ring animation 0→4px with brand color ease-out
- Card hover lift: translateY(-4px) + shadow-premium-lift + border glow
- Switch bounce: Enhanced spring overshoot on thumb
- Checkbox celebration: Scale burst 1→1.2→1 on check (300ms)
- Like heart pulse: Scale + rotate animation

### 3. Skeleton-to-Content Morph
- Skeleton shape preserved during transition (no pop-in replacement)
- Background: skeleton-gray → transparent (400ms)
- Content: fade-in + blur 4px→0 (300ms, 100ms delay)
- CSS transition classes on wrapper, React state toggle

### 4. Animated Theme Toggle
- Sun/Moon SVG path morphing
- Color wave pulse from toggle button (CSS `::before` scale)
- All glass surfaces transition simultaneously (600ms)

### 5. Page Transition Variants
- Dashboard→Page: Fade + slide up (default, already exists)
- News list→detail: Shared layout animation (card expands)
- Schedule→dialog: Scale from click position
- Tab switches: Directional slide left/right

### 6. Staggered Entry Animations
- Dashboard cards: 0.06s cascade with blur dissolve
- News feed: 0.04s stagger slide-up
- Events grid: Pop-in scale 0.9→1 + blur
- Messenger contacts: Fade-in top-to-bottom

## Constraints
- All animations respect `prefers-reduced-motion: reduce`
- Bundle impact: primarily CSS (~500 lines), minimal TSX (~300 lines)
- No cursor glow (removed per user feedback)
- No external animation libraries beyond Framer Motion
- Main chunk must remain <500 KB (CI gate)

## Files to create/modify
- `frontend/src/styles/partials/_glass-layers.css` — depth system + noise texture
- `frontend/src/styles/partials/_micro-interactions.css` — ripple, glow, celebrations
- `frontend/src/styles/partials/_skeleton-morph.css` — morph transitions
- `frontend/src/components/ui/ThemeToggle.tsx` — animated toggle
- `frontend/src/components/ui/motion/StaggerChildren.tsx` — stagger wrapper
- `frontend/src/components/ui/SkeletonMorph.tsx` — morph container
- `frontend/src/styles/tokens/semantics.css` — aurora gradient tokens
- `frontend/src/styles/theme.css` — import new partials
- Existing components: GlassCard, Button, Input, Checkbox, Switch, Dialog, Snackbar, PageTransition, ScrollReveal
