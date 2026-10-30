import './polyfill.js'
import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'

// `npm run preview:ui` only: sample data in place of the Rust side. Dropped from real builds.
const preview = import.meta.env.MODE === 'preview' ? import('./dev/preview.js') : Promise.resolve()
preview.then(() => mount(App, { target: document.getElementById('app') }))
