export const BRAND_BOOT_LOADER_CSS = String.raw`
:root {
  --brand-boot-loader-navy: #033167;
  --brand-boot-loader-red: #e40137;
  --brand-boot-loader-cycle: 6s;
  --brand-boot-loader-hold: 2500ms;
  --brand-boot-loader-exit: 450ms;
  --brand-boot-loader-size: clamp(9rem, 22vmin, 30rem);
  --brand-boot-loader-gap: clamp(1.125rem, 3vmin, 3rem);
  --brand-boot-loader-status-size: clamp(0.6875rem, 1.4vmin, 1.125rem);
  --brand-boot-loader-status-color: #8490a2;
  --brand-boot-loader-draw-ease: cubic-bezier(0.61, 0.06, 0.35, 1);
  --brand-boot-loader-exit-ease: cubic-bezier(0.4, 0, 0.2, 1);
  --z-boot-loader: 999998;
}

.dark {
  --brand-boot-loader-status-color: #aeb8c7;
}

html:has(.brand-boot-loader) {
  overflow-y: hidden;
  overflow-y: clip;
  animation: brand-boot-loader-scroll-unlock 1ms linear 12s forwards;
}

.brand-boot-loader ~ #root {
  overflow-x: hidden;
  overflow-x: clip;
}

.brand-boot-loader {
  position: fixed;
  z-index: var(--z-boot-loader);
  inset: 0;
  display: grid;
  min-width: 100%;
  min-height: 100vh;
  min-height: 100svh;
  min-height: 100dvh;
  box-sizing: border-box;
  place-items: center;
  overflow: hidden;
  overflow: clip;
  padding:
    max(1rem, env(safe-area-inset-top))
    max(1rem, env(safe-area-inset-right))
    max(1rem, env(safe-area-inset-bottom))
    max(1rem, env(safe-area-inset-left));
  color: var(--brand-boot-loader-status-color);
  background: var(--initial-bg, #f8fafc);
  isolation: isolate;
  opacity: 1;
  pointer-events: auto;
  contain: layout paint style;
  font-family: "Avenir Next", "Segoe UI", sans-serif;
  animation: brand-boot-loader-failsafe 1ms linear 12s forwards;
  will-change: opacity;
}

.brand-boot-loader *,
.brand-boot-loader *::before,
.brand-boot-loader *::after {
  box-sizing: border-box;
}

.brand-boot-loader[data-state="exiting"] {
  opacity: 0;
  pointer-events: none;
  animation: none;
  transition: opacity var(--brand-boot-loader-exit)
    var(--brand-boot-loader-exit-ease);
}

.lhci-mode .brand-boot-loader {
  display: none;
}

.brand-boot-loader__content {
  display: flex;
  width: min(100%, 36rem);
  max-height: calc(100dvh - 2rem);
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--brand-boot-loader-gap);
}

.brand-boot-loader__mark-holder {
  width: min(100%, var(--brand-boot-loader-size));
  flex: 0 1 auto;
  transform: translate(0.45%, 0.15%);
}

.brand-boot-loader__mark-holder svg {
  display: block;
  width: 100%;
  height: auto;
  overflow: visible;
  shape-rendering: geometricPrecision;
}

.brand-boot-loader__navy {
  fill: var(--brand-boot-loader-navy);
  stroke: var(--brand-boot-loader-navy);
}

.brand-boot-loader__red {
  fill: var(--brand-boot-loader-red);
  stroke: var(--brand-boot-loader-red);
}

.brand-boot-loader__body-path,
.brand-boot-loader__accent-path {
  opacity: 0;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 1000;
  stroke-dashoffset: 1000;
  will-change: opacity, stroke-dashoffset, fill-opacity, stroke-opacity;
}

.brand-boot-loader__body-path {
  fill-opacity: 0;
  stroke-width: 8;
  stroke-opacity: 1;
}

.brand-boot-loader__accent-path {
  fill: none;
  stroke-width: 6;
}

.brand-boot-loader__mark {
  animation: brand-boot-loader-mark-exit var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-exit-ease) infinite;
  will-change: opacity;
}

.brand-boot-loader__navy-group .brand-boot-loader__body-path {
  animation: brand-boot-loader-navy-body var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__red-group .brand-boot-loader__body-path {
  animation: brand-boot-loader-red-body var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__navy-group .brand-boot-loader__accent-outer {
  animation: brand-boot-loader-navy-accent-outer var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__navy-group .brand-boot-loader__accent-inner {
  animation: brand-boot-loader-navy-accent-inner var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__red-group .brand-boot-loader__accent-outer {
  animation: brand-boot-loader-red-accent-outer var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__red-group .brand-boot-loader__accent-inner {
  animation: brand-boot-loader-red-accent-inner var(--brand-boot-loader-cycle)
    var(--brand-boot-loader-draw-ease) infinite;
}

.brand-boot-loader__status {
  display: flex;
  min-height: 1.5em;
  align-items: baseline;
  justify-content: center;
  gap: 0.125rem;
  color: var(--brand-boot-loader-status-color);
  font-size: var(--brand-boot-loader-status-size);
  font-weight: 650;
  letter-spacing: 0.16em;
  line-height: 1.35;
  text-align: center;
  text-transform: uppercase;
}

.brand-boot-loader__dots {
  display: inline-flex;
  min-width: 1.1em;
  letter-spacing: 0.08em;
}

.brand-boot-loader__dots span {
  opacity: 0.25;
  animation: brand-boot-loader-dot 1.2s ease-in-out infinite;
}

.brand-boot-loader__dots span:nth-child(2) {
  animation-delay: 150ms;
}

.brand-boot-loader__dots span:nth-child(3) {
  animation-delay: 300ms;
}

@keyframes brand-boot-loader-mark-exit {
  0%,
  85.1667% {
    opacity: 1;
  }
  92.6667%,
  100% {
    opacity: 0;
  }
}

@keyframes brand-boot-loader-navy-body {
  0% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  4.2% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  26.4% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 0;
  }
  36%,
  92.6667% {
    opacity: 1;
    fill-opacity: 1;
    stroke-opacity: 0;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-red-body {
  0%,
  7.5% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  11.7% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
  33.9% {
    opacity: 1;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 0;
  }
  43.5%,
  92.6667% {
    opacity: 1;
    fill-opacity: 1;
    stroke-opacity: 0;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    fill-opacity: 0;
    stroke-opacity: 1;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-navy-accent-outer {
  0%,
  5.3667% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
  27.5667%,
  92.6667% {
    opacity: 1;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-navy-accent-inner {
  0%,
  6.5333% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
  28.7333%,
  92.6667% {
    opacity: 1;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-red-accent-outer {
  0%,
  12.8667% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
  35.0667%,
  92.6667% {
    opacity: 1;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-red-accent-inner {
  0%,
  14.0333% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
  36.2333%,
  92.6667% {
    opacity: 1;
    stroke-dashoffset: 0;
  }
  100% {
    opacity: 0;
    stroke-dashoffset: 1000;
  }
}

@keyframes brand-boot-loader-dot {
  0%,
  20%,
  100% {
    opacity: 0.25;
  }
  50% {
    opacity: 1;
  }
}

@keyframes brand-boot-loader-failsafe {
  to {
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
  }
}

@keyframes brand-boot-loader-scroll-unlock {
  to {
    overflow-y: auto;
  }
}

.brand-boot-loader[data-paused="true"] .brand-boot-loader__mark,
.brand-boot-loader[data-paused="true"] .brand-boot-loader__body-path,
.brand-boot-loader[data-paused="true"] .brand-boot-loader__accent-path,
.brand-boot-loader[data-paused="true"] .brand-boot-loader__dots span {
  animation-play-state: paused;
}

@media (max-height: 22.5rem) and (orientation: landscape) {
  :root {
    --brand-boot-loader-size: clamp(9rem, 38vmin, 9.5rem);
    --brand-boot-loader-gap: 0.75rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .brand-boot-loader__mark,
  .brand-boot-loader__body-path,
  .brand-boot-loader__accent-path,
  .brand-boot-loader__dots span {
    animation: none;
  }

  .brand-boot-loader__mark,
  .brand-boot-loader__accent-path,
  .brand-boot-loader__dots span {
    opacity: 1;
  }

  .brand-boot-loader__body-path {
    opacity: 1;
    fill-opacity: 1;
    stroke-opacity: 0;
    stroke-dashoffset: 0;
  }

  .brand-boot-loader__accent-path {
    stroke-dashoffset: 0;
  }

  .brand-boot-loader[data-state="exiting"] {
    transition: none;
  }
}

@media (forced-colors: active) {
  .brand-boot-loader__status {
    color: CanvasText;
  }
}
`
