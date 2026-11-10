import type { CapacitorConfig } from '@capacitor/cli'

// The native shell around the static app build (`npm run app:build` writes
// `out/`). See docs/mobile/PLAN.md for the whole workflow.
//
// Live reload while developing: run the dev server, then sync with
// CAP_SERVER_URL pointing at it, e.g.
//   CAP_SERVER_URL=http://10.0.2.2:3001 npx cap run android   (Android emulator)
//   CAP_SERVER_URL=http://localhost:3001 npx cap run ios      (iOS simulator)
// Never ship a build made with CAP_SERVER_URL set: the app would load the
// network address instead of its own bundle.
const devServer = process.env.CAP_SERVER_URL

const config: CapacitorConfig = {
  appId: 'ai.levylegal.app',
  appName: 'Levy',
  webDir: 'out',
  ...(devServer ? { server: { url: devServer, cleartext: devServer.startsWith('http://') } } : {}),
  // Behind the web view before the first paint, so a cold start never flashes
  // white. Matches the splash and the dark theme.
  backgroundColor: '#0b0d0c',
  ios: { contentInset: 'never' },
  // Bridge logs include what plugins return, such as the stored session, so
  // they are written only in debug builds, never in release.
  loggingBehavior: 'debug',
  plugins: {
    SplashScreen: {
      // Held until AppShell has painted the first real frame, then faded.
      launchAutoHide: false,
      launchShowDuration: 6000,
      backgroundColor: '#0b0d0c',
      showSpinner: false,
      splashFullScreen: false,
      splashImmersive: false,
    },
    SystemBars: { insetsHandling: 'css', style: 'DARK' },
    Keyboard: { resizeOnFullScreen: true },
  },
}

export default config
