import { useEffect, useRef } from "react"

interface Particle {
    x: number
    y: number
    size: number
    color: string
    // Physics properties
    orbitRadius: number
    orbitAngle: number
    orbitSpeed: number
    ease: number // How fast this specific particle follows its target
}

const ParticleAuthBackground = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const mouseRef = useRef({ x: 0, y: 0 })
    const mouseHistoryRef = useRef<{ x: number; y: number }[]>([])
    const virtualMouseRef = useRef({ x: 0, y: 0 })
    const particlesRef = useRef<Particle[]>([]) // Use ref for particles to persist across renders without state

    useEffect(() => {
        const canvas = canvasRef.current
        const container = containerRef.current
        if (!canvas || !container) return

        const ctx = canvas.getContext("2d")
        if (!ctx) return

        let animationFrameId: number
        let width = 0
        let height = 0

        // Configuration
        const particleCount = 1000 // Increased count for denser swarm
        const baseRadius = 280 // Increased radius for larger cloud
        const swarmSpeed = 12 // Speed at which the swarm follows the path (pixels per frame)

        // Colors for different themes
        const getThemeColors = () => {
            const isDark = document.body.classList.contains("dark")
            return isDark
                ? ["#4fb3ff", "#0ea5e9", "#38bdf8", "#7dd3fc"] // Bright blues for dark mode
                : ["#0369a1", "#0284c7", "#0ea5e9", "#38bdf8"] // Darker blues for light mode
        }

        const initParticles = () => {
            const colors = getThemeColors()
            const newParticles: Particle[] = []

            for (let i = 0; i < particleCount; i++) {
                const angle = Math.random() * Math.PI * 2
                // Gaussian-like distribution for radius (more dense in center)
                const r = (Math.random() + Math.random() + Math.random()) / 3 * baseRadius * 2

                newParticles.push({
                    x: width / 2 + Math.cos(angle) * r, // Start at center
                    y: height / 2 + Math.sin(angle) * r,
                    size: Math.random() * 2.5 + 1.5, // Larger particles (1.5px - 4.0px)
                    color: colors[Math.floor(Math.random() * colors.length)],
                    orbitRadius: r,
                    orbitAngle: angle,
                    orbitSpeed: (Math.random() * 0.002 + 0.0005) * (Math.random() > 0.5 ? 1 : -1), // Extremely slow rotation
                    ease: Math.random() * 0.005 + 0.001, // Extremely slow follow speed (0.001 - 0.006) for maximum lag
                })
            }
            particlesRef.current = newParticles
        }

        const resize = () => {
            width = container.clientWidth || window.innerWidth
            height = container.clientHeight || window.innerHeight
            canvas.width = width
            canvas.height = height

            // Initialize mouse at center if not moved yet
            if (mouseRef.current.x === 0 && mouseRef.current.y === 0) {
                mouseRef.current = { x: width / 2, y: height / 2 }
                virtualMouseRef.current = { x: width / 2, y: height / 2 }
            }

            if (particlesRef.current.length === 0) {
                initParticles()
            }
        }

        const handleMouseMove = (e: MouseEvent) => {
            const rect = container.getBoundingClientRect()
            const x = e.clientX - rect.left
            const y = e.clientY - rect.top

            mouseRef.current = { x, y }

            // Add to history only if distance is significant to prevent buildup
            const last = mouseHistoryRef.current[mouseHistoryRef.current.length - 1]
            if (!last || Math.hypot(x - last.x, y - last.y) > 5) {
                mouseHistoryRef.current.push({ x, y })
            }
        }

        const render = () => {
            ctx.clearRect(0, 0, width, height)

            // Update Virtual Mouse (Ghost Cursor)
            let target = mouseRef.current

            // If we have history, target the next point in history
            if (mouseHistoryRef.current.length > 0) {
                target = mouseHistoryRef.current[0]

                const dx = target.x - virtualMouseRef.current.x
                const dy = target.y - virtualMouseRef.current.y
                const dist = Math.hypot(dx, dy)

                if (dist < swarmSpeed) {
                    // Reached the point, snap to it and remove from history
                    virtualMouseRef.current = target
                    mouseHistoryRef.current.shift()
                } else {
                    // Move towards point
                    virtualMouseRef.current.x += (dx / dist) * swarmSpeed
                    virtualMouseRef.current.y += (dy / dist) * swarmSpeed
                }
            } else {
                // No history, ease towards current mouse (catch up)
                const dx = target.x - virtualMouseRef.current.x
                const dy = target.y - virtualMouseRef.current.y
                const dist = Math.hypot(dx, dy)

                if (dist > 1) {
                    virtualMouseRef.current.x += (dx / dist) * Math.min(dist, swarmSpeed)
                    virtualMouseRef.current.y += (dy / dist) * Math.min(dist, swarmSpeed)
                }
            }

            // Update and draw particles
            particlesRef.current.forEach((p) => {
                // 1. Update orbit angle
                p.orbitAngle += p.orbitSpeed

                // 2. Calculate target position based on VIRTUAL mouse + orbit
                const targetX = virtualMouseRef.current.x + Math.cos(p.orbitAngle) * p.orbitRadius
                const targetY = virtualMouseRef.current.y + Math.sin(p.orbitAngle) * p.orbitRadius

                // 3. Ease towards target
                p.x += (targetX - p.x) * p.ease
                p.y += (targetY - p.y) * p.ease

                // Draw
                ctx.fillStyle = p.color
                ctx.beginPath()
                ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
                ctx.fill()
            })

            animationFrameId = requestAnimationFrame(render)
        }

        // Watch for theme changes
        const observer = new MutationObserver((mutations) => {
            let shouldUpdate = false
            mutations.forEach((mutation) => {
                if (mutation.type === "attributes" && mutation.attributeName === "class") {
                    shouldUpdate = true
                }
            })
            if (shouldUpdate) {
                // Update colors of existing particles without resetting position
                const colors = getThemeColors()
                particlesRef.current.forEach(p => {
                    p.color = colors[Math.floor(Math.random() * colors.length)]
                })
            }
        })

        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ["class"],
        })

        // Initial setup
        const initTimer = setTimeout(() => {
            resize()
            render()
        }, 0)

        window.addEventListener("resize", resize)
        window.addEventListener("mousemove", handleMouseMove)

        // Cleanup
        return () => {
            clearTimeout(initTimer)
            window.removeEventListener("resize", resize)
            window.removeEventListener("mousemove", handleMouseMove)
            cancelAnimationFrame(animationFrameId)
            observer.disconnect()
        }
    }, [])

    return (
        <div
            ref={containerRef}
            className="absolute inset-0 z-0 overflow-hidden pointer-events-none"
            aria-hidden="true"
        >
            <canvas
                ref={canvasRef}
                className="absolute inset-0 w-full h-full"
            />
            {/* Overlay gradient to ensure text readability */}
            <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[var(--page-bg)] opacity-40" />
        </div>
    )
}

export default ParticleAuthBackground
