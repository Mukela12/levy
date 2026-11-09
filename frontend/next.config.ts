import type { NextConfig } from "next";

// Two builds from one codebase.
//
// * The website (default): the full app on Vercel, with server routes.
// * The native app (`LEVY_TARGET=app next build`): a static export in `out/`
//   that Capacitor bundles into the iOS and Android apps. It has no server, so
//   routes that need one are named `*.web.tsx` / `*.web.ts` and only the web
//   build picks them up (the Acts and Answers pages, the email routes, the
//   proxy, sitemap and robots). Files named `*.app.tsx` exist only in the app.
//   See docs/mobile/PLAN.md.
const isApp = process.env.LEVY_TARGET === "app";

const nextConfig: NextConfig = isApp
  ? {
      output: "export",
      // Every route becomes a folder with an index.html, which is what the
      // app's local web server looks for.
      trailingSlash: true,
      images: { unoptimized: true },
      pageExtensions: ["app.tsx", "app.ts", "tsx", "ts"],
      env: { NEXT_PUBLIC_LEVY_TARGET: "app" },
    }
  : {
      pageExtensions: ["web.tsx", "web.ts", "tsx", "ts"],
      // The bare domain serves the chat welcome itself (not a redirect): the
      // homepage stays indexable with real content, and a shared levylegal.ai
      // link lands people in the app. /chat remains the same app for old links;
      // its canonical already points at the root. /acts keeps its own URLs.
      async rewrites() {
        return [{ source: "/", destination: "/chat" }];
      },
    };

export default nextConfig;
