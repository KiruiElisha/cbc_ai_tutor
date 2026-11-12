// After `vite build --mode web`: the /learn page Frappe serves (cbc_ai_tutor/www/learn.html), made
// from the built index.html with the PWA bits added: manifest, icons and the service worker.
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { createHash } from 'node:crypto'

const out = new URL('../../cbc_ai_tutor/public/learn/', import.meta.url)
const page = new URL('../../cbc_ai_tutor/www/learn.html', import.meta.url)
let html = readFileSync(new URL('index.html', out), 'utf8')
const base = '/assets/cbc_ai_tutor/learn/'
const build = createHash('sha1').update(html).digest('hex').slice(0, 10)

html = html.replace(
  '</head>',
  `    <link rel="manifest" href="${base}manifest.webmanifest" />
    <link rel="icon" type="image/png" sizes="192x192" href="${base}icons/icon-192.png" />
    <link rel="apple-touch-icon" href="${base}icons/apple-touch-icon.png" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-title" content="CBC Tutor" />
    <meta name="description" content="CBC lessons, quizzes and an AI tutor for Kenyan learners." />
    <script>
      // Offline lessons need the page itself offline too: /learn-sw.js keeps the app shell.
      if ("serviceWorker" in navigator) {
        addEventListener("load", function () {
          navigator.serviceWorker.register("/learn-sw.js?build=${build}", { scope: "/learn" }).catch(function () {});
        });
      }
    </script>
  </head>`,
)
// Frappe renders www pages with Jinja: keep the built page as it is
html = '{% raw %}\n' + html + '\n{% endraw %}\n'
mkdirSync(new URL('.', page), { recursive: true })
writeFileSync(page, html)
rmSync(new URL('index.html', out))
console.log(`wrote cbc_ai_tutor/www/learn.html (build ${build})`)
