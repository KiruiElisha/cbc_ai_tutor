import './polyfill.js'
import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// `npm run preview:ui` only: sample data in place of the Rust side. Dropped from real builds.
// `npm run build:web` (the /learn PWA): the browser answers what Rust answers in the apps.
const preview =
  import.meta.env.MODE === 'preview' ? import('./dev/preview.js')
  : import.meta.env.MODE === 'web' ? import('./web/runtime.js')
  : Promise.resolve()
preview.then(() => mount(App, { target: document.getElementById('app') }))
