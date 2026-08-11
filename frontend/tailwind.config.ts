/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0f0f11',
        foreground: '#e4e4e7',
        card: '#1a1a1e',
        'card-foreground': '#e4e4e7',
        border: '#2a2a30',
        muted: '#27272a',
        'muted-foreground': '#a1a1aa',
        accent: '#27272a',
        primary: {
          DEFAULT: '#3b82f6',
          foreground: '#ffffff',
        },
        destructive: {
          DEFAULT: '#ef4444',
          foreground: '#ffffff',
        },
      },
      borderRadius: {
        lg: '8px',
        md: '6px',
        sm: '4px',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
