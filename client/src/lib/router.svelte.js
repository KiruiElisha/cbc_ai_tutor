/** A small hash router: '#/learn/lesson/abc' → { name: 'lesson', params: { id: 'abc' } }. */

const routes = []

export function route(pattern, name) {
  const keys = []
  const re = new RegExp(
    '^' + pattern.replace(/:([a-z_]+)/g, (_, k) => (keys.push(k), '([^/]+)')) + '/?$',
  )
  routes.push({ re, keys, name })
  // App.svelte registers routes after this module has read the address; read it again.
  Object.assign(router, parse(location.hash))
}

function parse(hash) {
  const path = (hash || '').replace(/^#/, '') || '/'
  const [pathname, query = ''] = path.split('?')
  for (const r of routes) {
    const m = pathname.match(r.re)
    if (m) {
      const params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]))
      for (const [k, v] of new URLSearchParams(query)) params[k] = v
      return { name: r.name, params, path }
    }
  }
  return { name: 'home', params: {}, path }
}

export const router = $state(parse(location.hash))

window.addEventListener('hashchange', () => {
  Object.assign(router, parse(location.hash))
  window.scrollTo(0, 0)
})

export function go(path, { replace = false } = {}) {
  const hash = '#' + path
  if (replace) {
    history.replaceState(null, '', hash)
    Object.assign(router, parse(hash))
  } else if (location.hash === hash) {
    Object.assign(router, parse(hash))
  } else {
    location.hash = hash
  }
}

export function back(fallback = '/') {
  if (history.length > 1) history.back()
  else go(fallback, { replace: true })
}

export const enc = encodeURIComponent
