/**
 * Telegram Bot API Proxy — Cloudflare Worker
 * 
 * Hugging Face Spaces blocks outbound connections to api.telegram.org.
 * This worker proxies all Telegram API calls through Cloudflare's network.
 * 
 * Free tier: 100,000 requests/day — more than enough for a Telegram bot.
 * 
 * SETUP (takes 2 minutes):
 * 
 * Option A — Cloudflare Dashboard (no CLI):
 *   1. Go to https://dash.cloudflare.com → Sign up (free)
 *   2. Workers & Pages → Create Worker
 *   3. Name it "tg-proxy" → Deploy
 *   4. Click "Edit Code" → paste this entire file → Save and Deploy
 *   5. Your proxy URL: https://tg-proxy.<your-account>.workers.dev
 * 
 * Option B — Wrangler CLI:
 *   1. npm install -g wrangler
 *   2. wrangler login
 *   3. wrangler deploy workers/telegram_proxy.js --name tg-proxy
 *   4. Your proxy URL: https://tg-proxy.<your-account>.workers.dev
 * 
 * THEN set in Hugging Face Space Secrets:
 *   TELEGRAM_API_BASE_URL = https://tg-proxy.<your-account>.workers.dev/bot
 *   TELEGRAM_API_BASE_FILE_URL = https://tg-proxy.<your-account>.workers.dev/file/bot
 */

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/" || url.pathname === "/health") {
      return new Response(JSON.stringify({ status: "ok", service: "telegram-api-proxy" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Proxy: rewrite URL from worker → api.telegram.org
    // e.g. https://tg-proxy.workers.dev/bot123:TOKEN/sendMessage
    //    → https://api.telegram.org/bot123:TOKEN/sendMessage
    const telegramUrl = `https://api.telegram.org${url.pathname}${url.search}`;

    const init = {
      method: request.method,
      headers: new Headers(request.headers),
    };

    // Forward request body for POST/PUT
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    try {
      const response = await fetch(telegramUrl, init);
      // Return Telegram's response as-is
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      });
    }
  },
};
