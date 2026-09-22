/**
 * Cloudflare Worker: Screener.in CORS Proxy for NSE Stock Fundamentals & Decomposition
 * 
 * Supports:
 * 1. GET /api/search?q=RELIANCE -> Resolves stock symbol/name to Screener company ID
 * 2. GET /api/stock?symbol=RELIANCE (or ?id=2726) -> Returns 15-year Price & EPS chart data with CORS
 * 3. OPTIONS * -> Permissive CORS preflight handler
 *
 * Deploy instructions:
 * 1. Paste this into Cloudflare Workers dashboard (Workers & Pages -> Create Worker)
 * 2. Click Save & Deploy
 * 3. Copy your worker URL (e.g., https://stock-proxy.your-name.workers.dev) into Tab 9 Proxy Settings!
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
  'Content-Type': 'application/json'
};

const SCREENER_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Accept': 'application/json, text/plain, */*'
};

export default {
  async fetch(request, env, ctx) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    try {
      // 1. Search endpoint: /api/search?q=SYMBOL
      if (path === '/api/search' || path === '/search') {
        const query = url.searchParams.get('q');
        if (!query) {
          return new Response(JSON.stringify({ error: 'Missing query parameter "q"' }), {
            status: 400,
            headers: CORS_HEADERS
          });
        }
        const screenerUrl = `https://www.screener.in/api/company/search/?q=${encodeURIComponent(query)}`;
        const res = await fetch(screenerUrl, { headers: SCREENER_HEADERS });
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          status: res.status,
          headers: CORS_HEADERS
        });
      }

      // 2. Stock fundamentals endpoint: /api/stock?symbol=SYMBOL or /api/stock?id=ID
      if (path === '/api/stock' || path === '/stock') {
        let symbol = url.searchParams.get('symbol') || '';
        let compId = url.searchParams.get('id');

        symbol = symbol.trim().toUpperCase();

        // If symbol given without ID, resolve ID via search first
        if (!compId && symbol) {
          // Special known mappings for tricky tickers
          const KNOWN_MAP = {
            'LT': 1870,
            'TATAMOTORS': 1285768,
            'M&M': 1969,
            'SBIN': 3188
          };

          if (KNOWN_MAP[symbol]) {
            compId = KNOWN_MAP[symbol];
          } else {
            const searchUrl = `https://www.screener.in/api/company/search/?q=${encodeURIComponent(symbol)}`;
            const sRes = await fetch(searchUrl, { headers: SCREENER_HEADERS });
            if (sRes.ok) {
              const sData = await sRes.json();
              if (Array.isArray(sData) && sData.length > 0) {
                // Look for exact symbol match in URL
                const match = sData.find(item => item.url && item.url.includes(`/company/${symbol}/`));
                compId = match ? match.id : sData[0].id;
              }
            }
          }
        }

        if (!compId) {
          return new Response(JSON.stringify({ error: `Could not resolve company ID for symbol "${symbol}"` }), {
            status: 404,
            headers: CORS_HEADERS
          });
        }

        const days = url.searchParams.get('days') || '5475'; // 15 years default
        const chartUrl = `https://www.screener.in/api/company/${compId}/chart/?q=Price-EPS&days=${days}&consolidated=true`;
        const cRes = await fetch(chartUrl, { headers: SCREENER_HEADERS });
        
        if (!cRes.ok) {
          return new Response(JSON.stringify({ error: `Screener returned status ${cRes.status}` }), {
            status: cRes.status,
            headers: CORS_HEADERS
          });
        }

        const chartData = await cRes.json();
        chartData.resolvedSymbol = symbol;
        chartData.resolvedId = compId;

        return new Response(JSON.stringify(chartData), {
          status: 200,
          headers: CORS_HEADERS
        });
      }

      // Root / Health check
      return new Response(JSON.stringify({
        status: 'ok',
        service: 'NSE Stock Fundamentals Screener CORS Proxy',
        endpoints: [
          '/api/search?q={query}',
          '/api/stock?symbol={symbol}',
          '/api/stock?id={company_id}'
        ]
      }), {
        status: 200,
        headers: CORS_HEADERS
      });

    } catch (err) {
      return new Response(JSON.stringify({ error: err.message || 'Internal proxy error' }), {
        status: 500,
        headers: CORS_HEADERS
      });
    }
  }
};
