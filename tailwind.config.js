/** Tailwind config for the STATIC build (vendored standalone CLI, run by export_static.py).
 *  Scans the JSX source (which holds every className literal, including the ones stored as
 *  strings in TOKENS/BIAS) so the generated tailwind.css contains exactly the utilities the
 *  app uses - replacing the runtime cdn.tailwindcss.com script. Mirrors the old inline
 *  config (darkMode class + the four font families). */
module.exports = {
  darkMode: 'class',
  content: ['./static/app.jsx', './static/index.html'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['IBM Plex Sans', 'system-ui', 'sans-serif'],
        serif: ['Source Serif 4', 'Georgia', 'serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
        deva: ['IBM Plex Sans Devanagari', 'IBM Plex Sans', 'sans-serif'],
      },
    },
  },
};
