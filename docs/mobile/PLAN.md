# Levy for iOS and Android: plan and working notes

Started 10 November 2026 on branch `mobile/app` (worktree `~/levy-mobile`).
Keep this file current: it is the map every later session starts from.

## The decision

Ship the existing Next.js app inside **Capacitor 8** as a **bundled static
export**, not a wrapper around the live website.

- **One codebase, two builds.** `next build` makes the website exactly as
  before. `LEVY_TARGET=app next build` makes a static copy of the signed-in app
  in `frontend/out/`, which Capacitor packs into the iOS and Android projects in
  `frontend/ios` and `frontend/android`.
- **Why bundled:** Capacitor's own docs say loading a live URL is not meant for
  production, and Apple rejects "repackaged websites" (guideline 4.2). A bundle
  also opens instantly and costs users no data for the app's own files, which
  matters on Zambian mobile data.
- **Why Capacitor and not a rewrite:** the signed-in app is already 100%
  client-side and talks to the FastAPI backend by absolute URL, so it ports
  almost unchanged. A React Native rewrite would be months.
- **Versions (10 Nov 2026):** Capacitor 8.6.0 (9 is in beta, GA expected end of
  November; it needs Xcode 27, so move in Q1 2027). iOS uses Swift Package
  Manager (no CocoaPods). Android compile/target SDK 36, which Play has required
  since 31 Aug 2026. App id `ai.levylegal.app`, name "Levy".

## How the two builds are separated

- Files only the website needs are named `*.web.tsx` / `*.web.ts`; files only
  the app needs are named `*.app.tsx`. `next.config.ts` sets `pageExtensions`
  per target, so each build only sees its own routes. Web-only today: the Acts
  and Answers pages, the email route handlers, `/admin/news`, `/privacy`,
  `/llms.txt`, the proxy, and the `/chat/[id]` and `/matters/[id]` routes.
  `sitemap.ts` and `robots.ts` keep their names (Next 16 cannot resolve them
  renamed); they are harmless in the app.
- A static export cannot serve `/chat/<id>`. The app opens a saved chat at
  `/chat/view/?id=<id>` (and `/matters/view/?id=`). Always build links with
  `chatPath()` / `matterPath()` from `src/lib/routes.ts` and read the open chat
  with `useActiveChatId()` from `src/lib/active-chat.tsx`. A test fails if a
  component builds a `/chat/${...}` link by hand.
- The proxy file is `proxy.web.ts` with a default export: under that name Next
  16 looks for `default`, not `proxy`.
- **Check after any change to routing:** the website's route table must stay
  identical. On 10 Nov the web build listed the same 30 routes, 972 Acts, 65
  Answers and the proxy before and after the split.

## Developer workflow

```
cd ~/levy-mobile/frontend
npm run app:build                 # static export to out/
npx cap sync                      # copy out/ into both native projects
```

- **Android:** needs Java 21 (Gradle 8.14 rejects Android Studio's Java 25):
  `export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home`
  then `cd android && ./gradlew assembleDebug` and
  `adb install -r app/build/outputs/apk/debug/app-debug.apk`. Emulator: the
  Pixel_9_Pro AVD (Android 17, WebView 145).
- **iOS:** `xcodebuild -project ios/App/App.xcodeproj -scheme App -sdk
  iphonesimulator -destination 'id=<udid>' build`, or open it in Xcode.
  Simulator: iPhone 17 Pro, iOS 26.5, Xcode 26.6.
- **Live reload:** run the dev server and sync with
  `CAP_SERVER_URL=http://10.0.2.2:3001` (Android) or `http://localhost:3001`
  (iOS). Never ship a build made with it set.
- **Debugging:** Android `chrome://inspect`; iOS Safari > Develop > Simulator.
  Console output: `adb logcat | grep Capacitor/Console`, and
  `xcrun simctl launch --console-pty <udid> ai.levylegal.app`.
- **Gotcha:** Capacitor serves the root `index.html` for any path without a
  file extension, on both platforms. In-app navigation is fine (the route data
  are `.txt` files), but a reload or deep link on `/chat/view/` would render
  the home page. See Phase 1.

## Phase 0: proof (done 10 Nov 2026)

- The website build is unchanged and the app build works: 19 static routes,
  18 MB (canopy art 5.8 MB, JS 5.8 MB, PDF worker 2.1 MB).
- **Both apps launch and render the real welcome screen:** the Pixel 9 Pro
  emulator and the iPhone 17 Pro simulator, with the tour, composer, suggested
  question, Kafue photo and dock.
- **API origins:** `capacitor://localhost` and `https://localhost` added to the
  API's CORS list, with a test. NOT deployed yet: until then no question can
  be answered in the app.
- **Tests:** 97/97 frontend and 3/3 for the new origin test.

## Phase 1 status (10 Nov 2026, commits eebbba1 and 8b3e94a)

Checked on the Pixel 9 Pro emulator and the iPhone 17 Pro simulator, signed in
as the QA account, light and dark.

**Done:**
- No white flash on launch (the splash is held until the first screen paints).
- Levy's own icon and splash on both platforms, generated from `frontend/assets/`.
- Sign-in required. The session lives in Capacitor Preferences with PKCE and
  refreshes on resume.
- Reset links and the welcome email go to the website (`linkTarget`, `siteRoute`).
- The theme follows the phone, and the status bar follows the theme.
- Safe areas use Capacitor's `--safe-area-inset-*` variables, falling back to `env()`.
- Conversation layout like a chat app: no dock, a one-line composer on the
  bottom edge, the title in the top bar, a new-chat button, and the menu opening
  from the left.
- No keyboard on launch, no zoom on focus, and haptics on send.
- Reloads keep the page: native routers (iOS `StaticSiteRouter`, Android
  `StaticSiteWebViewClient`), proven by killing iOS's web process on an open chat.
- The Android back button.
- Website-only links open in the in-app browser.
- One tap opens a recent chat on iOS.

**Since done (10 Nov, later):**
- The API CORS change is live (44d934c on Railway; local `main` only, not pushed).
- Streamed answers work on both platforms (Android 1, iOS 2 questions).
- Backgrounding mid-answer on iOS: Home pressed 4 s into the answer, app
  reopened 30+ s later, the answer was complete with its sources.

**Still not done:**
1. **Deploy the website** for the welcome route's CORS, the touch fixes and the
   privacy policy reading the shared AI list. Needs `mobile/app` merged into
   `main`. The web route table is verified identical (40 lines, proxy intact).
2. **Deploy the backend's `DELETE /api/account`** (on this branch, 39cd9cb). The
   app's delete button fails politely until then.
3. **A real low-end Android phone** (Phase 3) and **a real iPhone** (see the
   first-tap note below).

## Commercial readiness (10 Nov 2026, commits 39cd9cb and 1bfe0d4)

| Requirement | What the app does |
|---|---|
| Apple 5.1.1(v), Play account deletion | Account > Delete account, two steps (open, type "delete"). `DELETE /api/account` removes chats, messages, feedback, artifacts, uploads (rows, chunks, keyword rows, files), folders, templates, matters, then the sign-in. Library documents the user owns stay, with no owner. 9 backend tests. |
| Apple 5.1.2(i) AI consent | One-time screen before the first question naming Anthropic, OpenAI, Google (Gemini API), Moonshot AI and OpenRouter, Tavily, with where each is. Saved on the account (`user_metadata.ai_consent`), checked with the server before asking, so one phone is enough. Raise `AI_CONSENT_VERSION` in `lib/ai-providers.ts` when a provider is added. Reviewable in Account. |
| Play AI content reporting | A flag next to the thumbs: harmful or offensive, wrong about the law, something else, optional note. Stored as a thumbs-down whose reason starts `[report:<kind>]`; read reports where feedback is read. |
| Privacy and support links | Account > About Levy: AI services, privacy policy (in-app browser), Contact support (mailto), version. |
| Apple privacy manifest | `ios/App/App/PrivacyInfo.xcprivacy`: email, name, other user content (app functionality, linked, no tracking); UserDefaults reason CA92.1. Must match the App Privacy answers. |
| iOS settings | Camera and photo purpose strings, `ITSAppUsesNonExemptEncryption` false, iPhone only (decided 10 Nov) in portrait, 1.0.0 (1). |
| Support URL and Play deletion link | `www.levylegal.ai/support` (website-only page, 9b39b06), with `#delete-account` naming the app and developer, the steps, what is deleted and kept, and an email route. **Goes live only when the website is deployed**; the app's Help and support row opens it. |
| Android release | 1.0.0 (1). Release signing reads `android/keystore.properties` (git-ignored; see `keystore.properties.example`). `allowBackup` off so the stored session is not copied to cloud backups. |

**Mukela's part before submitting:** the Apple team in Xcode (Signing), the
Android upload key (`keytool` line in the example file) and its passwords,
the App Store Connect and Play Console listings, a review demo account, the
age-rating answers, the Data safety form, and the Play account type. The
support URL is built (deploy the website first). Confirm the support page's
line that database backups roll over within 30 days matches the Supabase plan.

**iOS first tap (simulator only, open):** after a cold launch the first tap
did nothing in 9 of 13 tries; Android never missed. The touch reaches the
app's window (a temporary `UIWindow.sendEvent` logger showed it), and in the
4 tries that worked, a log stream had been started or a screenshot taken
seconds before; WebKit then logged "Synthetic click completed". Not the splash
(it still failed with the splash off) and not the analytics listener (removed
from the app anyway). Settings took its first tap. Later the same happened
mid-session after a minute of idle, and a tap made straight after a
screenshot worked every time, including after 20 s of idle. So it is the
simulator tool's touch injection waking up, not Levy. When testing, take a
screenshot before the first tap. Confirm on a real iPhone in TestFlight.

## Review pass (10 Nov 2026, c3d6e95)

Walked both phones screen by screen (sign-in, create account, recovery,
welcome, chat, keyboard, menu, documents, templates, matters, study,
account, consent, tour, source viewer, offline, light and dark). Fixed:
- One loader (`components/canopy/loader.tsx`, three reading lines, not the
  logo) for every page-level wait.
- Offline: native Network status (Android's WebView never reports offline),
  plain "You're offline" errors, the question put back in the composer.
- Switching chats from the menu left the menu open (query routes keep the
  pathname); it closes on a chat change now.
- The tour waits for the AI consent on a first run, and its first card clears
  the gesture bar (a Tailwind class with a space was being dropped).
- Sign-in fields' keyboard hints, privacy and help links under the forms,
  no tap flash, pressed states, 16px fields on touch screens.

Ideas not done yet: bundle the 960px welcome photos in the app (they come
from Supabase storage and are missing offline); iOS Password AutoFill
(needs the Team ID and an apple-app-site-association file on the website).

**Gotchas found in Phase 1:**
- **iOS root view controller.** Capacitor 8's template creates it in
  `SceneDelegate.swift`, ignoring the storyboard's class. Overrides go there.
- **iOS taps and hover.** A `:hover` rule that reveals something makes the first
  tap a hover. Keep reveals inside `@media (hover: hover)` (Tailwind 4 already
  does).
- **iOS zoom.** iOS zooms into any focused field under 16px. Touch screens get a
  16px composer, and the app fixes the scale.
- **Android splash.** `SplashScreen.hide()` can be dropped if sent too early, so
  AppShell repeats it. The Android 12+ splash colours are in
  `res/values(-night)/colors.xml` (`levySplash`).
- **The asset generator** also writes web app files into `public/`. Delete them
  (the website is not a PWA).
- **Debug bridge logs print plugin results, including the stored session.**
  `loggingBehavior: 'debug'` keeps them out of release builds; don't share
  debug logs.
- **Testing signed in without typing a password:** mint a QA-probe session (the
  project's own QA flow), then write it to Preferences.
  - Android: CDP `Capacitor.Plugins.Preferences.set` through
    `adb forward tcp:9333 localabstract:webview_devtools_remote_<pid>`.
  - iOS: `xcrun simctl spawn <udid> defaults write ai.levylegal.app
    CapacitorStorage.<key> -string <json>`.

## What the first run showed (the Phase 1 backlog)

**Blockers (nothing works without these):**
1. Deploy the API CORS change (Railway, BantuRide login).
2. **Sign-in storage.** `@supabase/ssr`'s browser client keeps the session in
   cookies, which are unreliable on `capacitor://`. In the app, use
   `supabase-js` with PKCE and a secure-storage adapter (Keychain/Keystore,
   not localStorage, which the OS may clear); refresh on app resume.
3. **Password reset** links point at `window.location.origin`
   (`capacitor://localhost`). Use a 6-digit email code (`verifyOtp`) in the
   app, which also survives email scanners.
4. **The welcome email** is a relative call to a Next route, which the app does
   not have. Move it to the backend.
5. **Guests:** Turnstile may not accept the app's origin. Decide: sign-in
   required in the app (recommended), or add the hostnames to Turnstile.

**Native feel and polish:**
6. **White flash on iOS cold start** (about 3 seconds). Keep the splash screen
   until the shell has mounted (`launchAutoHide: false`, then `hide()`), and
   set dark native backgrounds.
7. **Status bar and safe areas.** Android draws edge to edge (forced for API 36)
   with dark status-bar icons on the dark UI. Use the core SystemBars plugin
   (style per theme, `--safe-area-inset-*` CSS variables). The first launch
   logged "Error injecting safe area CSS".
8. **Hide web-only UI in the app:** the "new home at levylegal.ai" banner
   (overlapping the status bar on both platforms) and Vercel Analytics/Speed
   Insights (they fail to load anyway).
9. **The keyboard opens by itself on Android launch** (composer autofocus). No
   autofocus in the app.
10. **Android back button:** close sheets, then go back, then exit at the root.
11. **Reloads and deep links:** add a small native router (iOS: subclass
    `CAPBridgeViewController.router()`; Android: request interception) that
    serves `<dir>/index.html` for folder paths, so a reload stays on the page.
    iOS reloads the WebView when its process is killed in the background, so
    this matters.
12. **App icon and splash artwork:** they are Capacitor's placeholders. Generate
    them with `@capacitor/assets` from the Levy mark.
13. **Links to web-only pages** (Acts, Answers, Privacy) open in the in-app
    browser (`@capacitor/browser`).
14. **Answers that stream for 30-60 seconds:** iOS suspends a backgrounded app
    after about 5 seconds. On resume, reload the thread; the server already
    saves signed-in answers. Keep `CapacitorHttp` off (it breaks streaming).

## Phases

| Phase | What | Done when |
|---|---|---|
| 0 Proof | Two builds, both apps launch | Done 10 Nov |
| 1 Foundation | Backlog 1-14, automated smoke test | On both simulators: sign in, ask, get a streamed answer, reopen it from the list, reload on that page, back button; light and dark |
| 2 Native value and store rules | Share sheet, haptics, camera and photo upload, push "your answer is ready" (FCM), in-app account deletion, AI-data consent screen (Apple 5.1.2(i), naming Anthropic and OpenAI), "Report answer" (Play AI policy), offline saved answers | Each item works on both platforms |
| 3 Quality | Design pass for phone screens to a premium standard, low-end Android performance, font scaling, accessibility | Tested on a cheap real Android phone and the largest font size |
| 4 Release | TestFlight; Play internal then closed testing; listings, screenshots, privacy labels, Data safety, age rating, demo account for review | Both stores approve v1.0 |
| 5 Levy News tab | When News publishes on the web | Per the 27 Oct News plan |

## Store requirements checklist (from the 10 Nov research)

- **Apple:**
  - 4.2: native value beyond the website. Bundled pages, push, share, camera and offline saved answers.
  - 5.1.1(v): account deletion in the app (deactivation does not count).
  - 5.1.2(i): explicit consent before personal data goes to a third-party AI.
  - 4.8: if Google sign-in ships on iOS, Sign in with Apple must ship too.
  - Privacy manifest (Preferences needs reason CA92.1), App Privacy labels (prompts are "Other User Content").
  - The new age-rating questions must be answered by 12 Jan 2027.
  - A demo account for review.
- **Google Play:**
  - Target API 36.
  - A personal account created after 13 Nov 2023 needs 12 testers opted in for 14 days of closed testing.
  - In-app reporting for AI output.
  - Account deletion in the app and by a web link.
  - Data safety form.
  - 16 KB page size from 1 Feb 2027 (no native libraries today).
  - App Links need the Play app-signing SHA-256.
- **Both:** no purchase screens in v1, and no live JS updates in v1.

## Testing

- **Every change:**
  - The frontend unit tests (`node --test tests/*.test.mjs`) and backend tests.
  - The web route table unchanged.
  - The app build succeeds.
- **Every app build:**
  - Install on the Pixel 9 Pro emulator and the iPhone 17 Pro simulator.
  - Walk the smoke path (Phase 1 "done when").
  - Take screenshots in light and dark.
  - Check the console for errors.
- **Later:**
  - An Appium (WEBVIEW context) or Playwright-over-CDP smoke script on the Android emulator.
  - fastlane for signing and uploads.
  - Sentry for crashes.

## Decisions

Decided 10 Nov ("go with your recommendations"): app id `ai.levylegal.app`
(permanent after the first upload), email and password sign-in only in v1,
sign-in required in the app.

Decided 10 Nov (later): iPhone only for v1.

Still waiting on Mukela:
1. **The Google Play account:** personal (the 12-tester rule applies if it was created after 13 Nov 2023) or organisation (needs a D-U-N-S number).
