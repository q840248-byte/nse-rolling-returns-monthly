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
  'TMPV': 3370,
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
  'BPCL': 462,
  'ETERNAL': 1274894,
  'ZOMATO': 1274894,
  'BAJAJ-AUTO': 369,
  'SHRIRAMFIN': 3046,
  'HINDALCO': 1328,
  'APOLLOHOSP': 218,
  'INDUSINDBK': 1480,
  'TRENT': 3467,
  'BEL': 456,
  'HAL': 1274307,
  'DLF': 841,
  'VBL': 1273562,
  'VEDL': 2943,
  'JIOFIN': 1284422,
  'INDIGO': 1273121,
  'SBILIFE': 1274150,
  'HDFCLIFE': 1274197,
  'ADANIPOWER': 58,
  'TATACONSUM': 3367,
  'BSE': 1273635,
  'MCX': 2156,
  'CDSL': 1274088,
  'PAYTM': 1275094,
  'NYKAA': 1274992,
  'IRCTC': 1274700,
  'IRFC': 1274825,
  'PFC': 2522,
  'RECLTD': 2809,
  'YESBANK': 3783
};

function sanitizeEpsValues(values) {
  const valid = (values || [])
    .filter(pt => Array.isArray(pt) && pt[0] && pt[1] !== null && pt[1] !== undefined && !isNaN(parseFloat(pt[1])))
    .map(pt => [String(pt[0]), parseFloat(pt[1])])
    .sort((a, b) => a[0].localeCompare(b[0]));
  if (valid.length < 3) return valid;

  let startIdx = 0;
  if (valid.length >= 4) {
    const tailSlice = valid.slice(Math.min(4, Math.floor(valid.length / 2)), Math.min(valid.length, 15))
      .map(p => Math.abs(p[1])).sort((a, b) => a - b);
    const refMed = tailSlice.length > 0 ? tailSlice[Math.floor(tailSlice.length / 2)] : 0;
    const endAbs = Math.abs(valid[valid.length - 1][1]);
    if (refMed >= 0.5) {
      while (
        startIdx < Math.min(4, valid.length - 2) &&
        (Math.abs(valid[startIdx][1]) > Math.max(15, 10 * refMed) ||
         (valid.length <= 8 && endAbs >= 0.5 && Math.abs(valid[startIdx][1]) > 50 * endAbs))
      ) {
        startIdx++;
      }
    }
  }

  const trimmed = valid.slice(startIdx);
  if (trimmed.length < 3) return trimmed;
  const out = [trimmed[0]];
  for (let i = 1; i < trimmed.length - 1; i++) {
    const prev = out[out.length - 1][1];
    const cur = trimmed[i][1];
    const next = trimmed[i + 1][1];
    if (prev > 0 && next > 0 && (cur > 4 * Math.max(prev, next) || (cur > 0 && cur < 0.25 * Math.min(prev, next)))) {
      continue;
    }
    out.push(trimmed[i]);
  }
  out.push(trimmed[trimmed.length - 1]);
  return out;
}

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

        // If symbol given without ID, check known map first, then resolve via strict search / direct page
        if (!compId && symbol) {
          if (KNOWN_MAP[symbol]) {
            compId = KNOWN_MAP[symbol];
          } else {
            const queries = symbol.includes('-') ? [symbol, symbol.replace(/-/g, ' ')] : [symbol];
            for (const q of queries) {
              if (compId) break;
              const searchUrl = `https://www.screener.in/api/company/search/?q=${encodeURIComponent(q)}`;
              const sRes = await fetch(searchUrl, { headers: SCREENER_HEADERS });
              if (sRes.ok) {
                const sData = await sRes.json();
                if (Array.isArray(sData) && sData.length > 0) {
                  let match = sData.find(item => item.url && item.url.toUpperCase().includes(`/COMPANY/${symbol}/`));
                  if (!match) {
                    match = sData.find(item => item.url && item.url.toUpperCase().includes(`/${symbol}/`));
                  }
                  if (!match) {
                    match = sData.find(item => item.name && item.name.trim().toUpperCase() === symbol);
                  }
                  compId = match ? match.id : null;
                }
              }
            }
            if (!compId) {
              const pageRes = await fetch(`https://www.screener.in/company/${encodeURIComponent(symbol)}/`, { headers: SCREENER_HEADERS, redirect: 'follow' });
              if (pageRes.ok && pageRes.url.toUpperCase().includes(`/${symbol}/`)) {
                const htmlTxt = await pageRes.text();
                const idM = htmlTxt.match(/data-company-id="(\d+)"/);
                if (idM) compId = idM[1];
              }
            }
          }
        }

        if (!compId) {
          return new Response(JSON.stringify({ error: `Indian NSE/BSE symbol "${symbol}" not found on Screener` }), {
            status: 404,
            headers: CORS_HEADERS
          });
        }

        const days = url.searchParams.get('days') || '10000';
        const wantStandalone = url.searchParams.get('consolidated') === 'false';

        const consUrl = `https://www.screener.in/api/company/${compId}/chart/?q=Price-EPS&days=${days}&consolidated=true`;
        const saUrl = `https://www.screener.in/api/company/${compId}/chart/?q=Price-EPS&days=${days}`;

        let consData = null;
        let saData = null;
        if (wantStandalone) {
          const saRes = await fetch(saUrl, { headers: SCREENER_HEADERS });
          if (saRes.ok) saData = await saRes.json();
        } else {
          const [cRes, sRes] = await Promise.allSettled([
            fetch(consUrl, { headers: SCREENER_HEADERS }),
            fetch(saUrl, { headers: SCREENER_HEADERS })
          ]);
          if (cRes.status === 'fulfilled' && cRes.value.ok) {
            try { consData = await cRes.value.json(); } catch (e) {}
          }
          if (sRes.status === 'fulfilled' && sRes.value.ok) {
            try { saData = await sRes.value.json(); } catch (e) {}
          }
        }

        const getEpsPts = (d) => {
          const ds = (d && d.datasets || []).find(x => x.metric === 'EPS');
          return sanitizeEpsValues(ds ? ds.values : []);
        };
        const consEps = getEpsPts(consData);
        const saEps = getEpsPts(saData);

        let chartData = null;
        let epsBasis = 'standalone';
        let finalEps = [];

        if (!wantStandalone && consEps.length >= 2) {
          const consLast = new Date(consEps[consEps.length - 1][0]).getTime();
          const saLast = saEps.length > 0 ? new Date(saEps[saEps.length - 1][0]).getTime() : consLast;
          const staleDays = (saLast - consLast) / 86400000;
          if (saEps.length === 0 || staleDays <= 210) {
            chartData = consData;
            const consFirst = consEps[0][0];
            const stitched = [];
            const preSa = saEps.filter(pt => pt[0] < consFirst);
            if (preSa.length > 0) stitched.push(...preSa);
            let usedInternalSa = false;
            for (let i = 0; i < consEps.length; i++) {
              stitched.push(consEps[i]);
              if (i + 1 < consEps.length) {
                const gapDays = (new Date(consEps[i + 1][0]).getTime() - new Date(consEps[i][0]).getTime()) / 86400000;
                if (gapDays > 400) {
                  const midSa = saEps.filter(pt => pt[0] > consEps[i][0] && pt[0] < consEps[i + 1][0]);
                  if (midSa.length > 0) {
                    stitched.push(...midSa);
                    usedInternalSa = true;
                  }
                }
              }
            }
            stitched.sort((a, b) => a[0].localeCompare(b[0]));
            finalEps = stitched;
            epsBasis = (preSa.length > 0 || usedInternalSa) ? 'consolidated+standalone_splice' : 'consolidated';
          }
        }

        if (!chartData && saData) {
          chartData = saData;
          finalEps = saEps;
          epsBasis = 'standalone';
        } else if (!chartData && consData) {
          chartData = consData;
          finalEps = consEps;
          epsBasis = 'consolidated';
        }

        if (!chartData) {
          return new Response(JSON.stringify({ error: `Could not retrieve chart data for ${symbol || compId}` }), {
            status: 502,
            headers: CORS_HEADERS
          });
        }

        if (Array.isArray(chartData.datasets)) {
          chartData.datasets = chartData.datasets.map(ds =>
            ds.metric === 'EPS' ? { ...ds, values: finalEps } : ds
          );
        }

        chartData.resolvedSymbol = symbol;
        chartData.resolvedId = compId;
        chartData.epsBasis = epsBasis;

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
