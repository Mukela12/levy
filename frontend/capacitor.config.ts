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
  plugins: {
    SplashScreen: {
      launchShowDuration: 0,
      launchAutoHide: true,
      backgroundColor: '#0a0a0b',
      showSpinner: false,
    },
  },
}

export default config
