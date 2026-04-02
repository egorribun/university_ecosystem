interface NewsDetailBodyProps {
  content: string
}

export function NewsDetailBody({ content }: NewsDetailBodyProps) {
  return (
    <section className="glass-layer-surface glass-noise rounded-2xl p-6 sm:p-8 md:p-10">
      <div className="news-article-body text-body leading-relaxed text-(--text-secondary)">
        {content?.split(/\n{2,}/).map((chunk: string, idx: number) => {
          const text = chunk.trim()
          if (!text) return null

          // Pull-quote: lines starting with >
          if (text.startsWith(">")) {
            return (
              <blockquote key={`q-${idx}`} className="news-pullquote">
                {text.replace(/^>\s*/, "")}
              </blockquote>
            )
          }

          // Drop cap on first paragraph (only if long enough)
          const isDropCap = idx === 0 && text.length > 200
          return (
            <p key={`p-${idx}`} className={isDropCap ? "news-dropcap" : undefined}>
              {text}
            </p>
          )
        })}
      </div>
    </section>
  )
}
