import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        // Dev proxy: forwards /api requests to the local FastAPI backend.
        // In production, VITE_API_URL points directly to the Render backend URL.
        '/api': {
          target: env.VITE_BACKEND_DEV_URL || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      // Produce source maps for easier debugging (excluded from Vercel by default)
      sourcemap: false,
      // Ensure chunk warnings are visible
      chunkSizeWarningLimit: 1000,
    },
  }
})
