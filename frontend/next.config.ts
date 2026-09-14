import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The bare domain serves the chat welcome itself (not a redirect): the
  // homepage stays indexable with real content, and a shared levylegal.ai
  // link lands people in the app. /chat remains the same app for old links;
  // its canonical already points at the root. /acts keeps its own URLs.
  async rewrites() {
    return [{ source: '/', destination: '/chat' }]
  },
  /* config options here */
};

export default nextConfig;
