import process from "node:process"
import tailwindcss from "@tailwindcss/postcss"
import autoprefixer from "autoprefixer"

export default {
  plugins: [
    tailwindcss({
      // JSDOM cannot parse native nested selectors. Use the production
      // Lightning CSS lowering in tests, without minification, rather than
      // disabling stylesheet processing or suppressing parser diagnostics.
      optimize: process.env.NODE_ENV === "test" ? { minify: false } : undefined,
    }),
    autoprefixer(),
  ],
}
