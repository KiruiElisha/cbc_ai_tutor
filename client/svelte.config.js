import { vitePreprocess } from '@sveltejs/vite-plugin-svelte'

export default {
  preprocess: vitePreprocess(),
  compilerOptions: {
    // Screens are re-created on every route change ({#key router.path} in App.svelte),
    // so reading route params once at setup is intended.
    warningFilter: (w) => w.code !== 'state_referenced_locally',
  },
}
