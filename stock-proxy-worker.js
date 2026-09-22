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

// Verified Screener warehouse IDs for instant zero-latency lookup of top NSE bluechips
const KNOWN_MAP = {
  'RELIANCE': 2726,
  'TCS': 3365,
  'HDFCBANK': 1298,
  'INFY': 1489,
  'ICICIBANK': 1384,
  'ITC': 1552,
  'LT': 1870,
  'L&T': 1870,
  'BHARTIARTL': 467,
  'SBIN': 3188,
  'SBI': 3188,
  'STATE BANK': 3188,
  'TATAMOTORS': 3370,
  'TATA MOTORS': 3370,
  'KOTAKBANK': 1818,
  'AXISBANK': 348,
  'HINDUNILVR': 1350,
  'HUL': 1350,
  'BAJFINANCE': 372,
  'MARUTI': 2023,
  'SUNPHARMA': 3245,
  'ASIANPAINT': 295,
  'TITAN': 3437,
  'HCLTECH': 1297,
  'WIPRO': 3763,
  'NTPC': 2303,
  'ONGC': 2320,
  'POWERGRID': 2523,
  'ADANIENT': 56,
  'ADANIPORTS': 57,
  'TATASTEEL': 3373,
  'JSWSTEEL': 1657,
  'COALINDIA': 681,
  'ULTRACEMCO': 3525,
  'BAJAJFINSV': 373,
  'M&M': 1973,
  'NESTLEIND': 2236,
  'TECHM': 100068,
  'GRASIM': 1198,
  'CIPLA': 661,
  'DIVISLAB': 837,
  'DRREDDY': 852,
  'EICHERMOT': 888,
  'BPCL': 462
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

        // If symbol given without ID, check known map first, then resolve via search
        if (!compId && symbol) {
          if (KNOWN_MAP[symbol]) {
            compId = KNOWN_MAP[symbol];
          } else {
            const searchUrl = `https://www.screener.in/api/company/search/?q=${encodeURIComponent(symbol)}`;
            const sRes = await fetch(searchUrl, { headers: SCREENER_HEADERS });
            if (sRes.ok) {
              const sData = await sRes.json();
              if (Array.isArray(sData) && sData.length > 0) {
                // Look for exact symbol match in URL (e.g. /company/SYMBOL/)
                let match = sData.find(item => item.url && item.url.toUpperCase().includes(`/COMPANY/${symbol}/`));
                if (!match) {
                  match = sData.find(item => item.url && item.url.toUpperCase().includes(`/${symbol}/`));
                }
                if (!match) {
                  match = sData.find(item => item.name && item.name.toUpperCase().startsWith(symbol + ' '));
                }
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
        const wantStandalone = url.searchParams.get('consolidated') === 'false';

        let chartData = null;
        if (!wantStandalone) {
          try {
            const consUrl = `https://www.screener.in/api/company/${compId}/chart/?q=Price-EPS&days=${days}&consolidated=true`;
            const cRes = await fetch(consUrl, { headers: SCREENER_HEADERS });
            if (cRes.ok) {
              const data = await cRes.json();
              const epsDs = (data.datasets || []).find(d => d.metric === 'EPS');
              const epsCount = epsDs && epsDs.values ? epsDs.values.length : 0;
              if (epsCount >= 30) {
                chartData = data;
              }
            }
          } catch (e) {
            // Ignore consolidated failure, try standalone
          }
        }

        // If consolidated had few/no points (e.g. standalone company like Nestle or fail), try standalone
        if (!chartData) {
          const saUrl = `https://www.screener.in/api/company/${compId}/chart/?q=Price-EPS&days=${days}`;
          const saRes = await fetch(saUrl, { headers: SCREENER_HEADERS });
          if (saRes.ok) {
            chartData = await saRes.json();
          }
        }

        if (!chartData) {
          return new Response(JSON.stringify({ error: `Could not retrieve chart data for ${symbol || compId}` }), {
            status: 502,
            headers: CORS_HEADERS
          });
        }

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
