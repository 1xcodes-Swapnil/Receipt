/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['Playfair Display', 'Georgia', 'serif'],
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'Consolas', 'monospace'],
      },
      colors: {
        brand: {
          50: '#F4F8FA',
          100: '#E4F0F4',
          200: '#C5DCE4',
          300: '#94B8C5',
          400: '#6995A5',
          500: '#477586',
          600: '#345B6A',
          700: '#274450',
          800: '#1C2D37',
          900: '#132027',
          950: '#0B1317',
        },
        surface: '#F8FAFC',
        card: '#FFFFFF',
        accent: '#1C2D37',
      },
      borderRadius: {
        '4xl': '2rem',
        '5xl': '2.5rem',
      },
      boxShadow: {
        'soft-xl': '0 20px 40px -15px rgba(28, 45, 55, 0.07), 0 0 1px 1px rgba(28, 45, 55, 0.04)',
        'soft-2xl': '0 25px 50px -12px rgba(28, 45, 55, 0.12)',
        'glow': '0 0 20px rgba(148, 184, 197, 0.4)',
      },
    },
  },
  plugins: [],
}

