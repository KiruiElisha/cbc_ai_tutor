import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host ? { protocol: 'ws', host, port: 1421 } : undefined,
    watch: { ignored: ['**/src-tauri/**'] },
  },
  envPrefix: ['VITE_', 'TAURI_ENV_*'],
  build: {
    // Chrome 80 covers the Nokia 7 Plus WebView (84). A newer target keeps
    // logical assignment (??=), which that WebView rejects and shows as a blank screen.
    target: 'chrome80',
    minify: !process.env.TAURI_ENV_DEBUG,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
})
