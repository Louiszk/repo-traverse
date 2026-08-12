/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        sienna: {
          300: '#D5A898',
          400: '#B27A66',
          500: '#8E5B4B',
          600: '#6C4032',
        },
        softrose: {
          300: '#E6BCB2',
          400: '#DDA79A',
          500: '#CD9588',
          600: '#B87F72',
        },
        dark: {
          900: '#1A1614',
          800: '#241E1A',
          700: '#2D2521',
          600: '#3C302B',
        },
        brand: {
          500: '#B27A66',
          600: '#8E5B4B',
          700: '#6C4032',
          cyan: '#D5A898',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 8s linear infinite',
      },
    },
  },
  plugins: [],
};

