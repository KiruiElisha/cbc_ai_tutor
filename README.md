## CBC AI Tutor

Lessons, quizzes, assignments and an AI tutor ("Mwalimu") for Kenya's Competency Based Curriculum, PP1 to Grade 12.

The repository has two parts:

- **`cbc_ai_tutor/`**: a Frappe app (needs ERPNext's sibling app **Education**). It holds the curriculum, lessons, progress, subscriptions and payments, and serves the REST API under `/api/method/cbc_ai_tutor.api.*`.
- **`client/`**: the desktop and mobile app, built with Svelte 5 and Tauri 2 (Rust). It has one code base for Windows, macOS, Linux, Android and iOS.

Three kinds of users sign in to the app:

| Role | Signs in with | Does |
| --- | --- | --- |
| Parent | email + password, a 6-digit email code, or Google (signs up in the app) | adds children, follows progress, pays, messages the school |
| Learner | learner code + PIN (set by the parent) | lessons, quizzes, assignments and Mwalimu; works offline |
| Teacher | email + password, a 6-digit email code, or Google (an Instructor with a school) | assignments, reviews, CBC observations and assessments, replies to parents |

### Server

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app education --branch version-16
bench get-app $URL_OF_THIS_REPO
bench --site $SITE install-app cbc_ai_tutor
```

Installing creates the CBC grades (PP1, PP2 and Grade 1 to 12), their learning areas, three placeholder plans and the roles. To run the seeding again on an existing site:

```bash
bench --site $SITE execute cbc_ai_tutor.setup.install.seed
```

Set the plan prices under **Subscription Plan** before going live; the seeded prices are placeholders. Then open **CBC Settings** and fill in each section:

- **General**: app name, support contacts, trial length and limits, session length.
- **AI Tutor**: provider (OpenAI, Anthropic, Google Gemini or any OpenAI-compatible endpoint), model and API key. While this is off, Mwalimu answers "not available" and the rest of the app works.
- **M-Pesa (IntaSend)**:
  1. Enter your publishable and secret keys.
  2. Use `https://sandbox.intasend.com` as the API base URL for testing. The default is live.
  3. In the IntaSend dashboard, add a webhook pointing to the **Webhook URL** shown in settings (`/api/method/cbc_ai_tutor.api.payments.intasend_webhook`). Use the same challenge string in both places.
- **PayPal**:
  1. Enter the client ID and secret, and pick Sandbox or Live.
  2. In the PayPal developer dashboard, create a webhook for `/api/method/cbc_ai_tutor.api.payments.paypal_webhook`. Subscribe it to `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED` and `PAYMENT.CAPTURE.DECLINED`.
  3. Paste the webhook ID back into settings.

Payments are checked three ways: by the webhook, when the app polls, and by a job that runs every 10 minutes for payments still pending. Access is granted once per payment, and only when the amount and currency match the plan.

**Sign-in.** Learners use their code and PIN. Parents and teachers can use a password, a 6-digit code emailed to them, or Google. Email codes need an outgoing Email Account. For Google, create a Web application OAuth client, paste its client ID and secret into **CBC Settings**, turn Google on, and add the **Redirect URL** shown there (it looks like `https://school.example.co.ke/api/method/cbc_ai_tutor.api.signin.google_callback`) as an authorised redirect URI.

The site must be reachable over **HTTPS** from phones, because the app refuses plain HTTP except for `localhost`, `192.168.*` and `*.local` hosts, which are meant for testing. Email (password reset, renewal reminders, replies to parents) needs an outgoing Email Account on the site.

Teachers are **Instructor** records linked to a user and a **School**. They see learners whose parent picked that school.

### App

Requirements:

- Node 20 or later
- Rust (stable)
- On Windows: the MSVC build tools and WebView2 (Windows 10/11 already have WebView2)
- For Android: JDK 17, the Android SDK and NDK, with `JAVA_HOME`, `ANDROID_HOME` and `NDK_HOME` set
- For iOS: a Mac with Xcode

```bash
cd client
npm install
npm run tauri dev               # desktop, with hot reload
npm run tauri build             # desktop installers (.msi / .exe, .dmg, .deb / .AppImage)
npm run tauri android init      # once
npm run tauri android dev       # on a device or emulator
npm run tauri android build     # .apk / .aab (sign it before uploading to Play)
npm run tauri ios init && npm run tauri ios build   # on macOS
```

The app is already pointed at its server. That address is not shown in the app. To build an app pointed at a different server, set the address at build time:

```bash
CBC_SERVER_URL=https://tutor.example.co.ke npm run tauri build
```

Other checks: `npm run check` (Svelte), and `cargo test` in `client/src-tauri` (sync, storage and API client).

#### How the app works

- **Rust core** (`client/src-tauri/src`):
  - Talks to the server and keeps a SQLite database on the device with lessons, quizzes, the learner's own records and an outbox of work done offline.
  - Stores device tokens in the OS keychain on Windows and macOS. On other platforms they are kept in the app's private database. Tokens are never exposed to the web view.
- **Learner sync**: a learner's lessons and quizzes are downloaded and work without internet. Quiz attempts, lesson progress, practice and assignment hand-ins are saved locally first and sent when the device is online. The server re-marks quizzes, and replays are ignored.
- **Parents and teachers** use the server directly. Their last answers are cached, so screens still open offline, under an "Offline. Showing what was saved…" banner.
- **Payment return links**: PayPal sends the parent back through `cbctutor://payment?tx=…`, which reopens the app on the payment screen.

### Contributing

This app uses `pre-commit` for code formatting and linting:

```bash
cd apps/cbc_ai_tutor
pre-commit install
```

### License

mit
