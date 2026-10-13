// Withdrawn-offer guard.
//
// Runs at the edge BEFORE the static-asset cache is consulted, so an offer that
// has been pulled still returns a real 404 even if an old copy is still warm in
// the Cloudflare Pages edge cache (Pages deploys do NOT purge the edge cache).
//
// Every other /deals/* request falls straight through to the static assets.
//
// To withdraw / restore an offer, edit WITHDRAWN below.

const WITHDRAWN = new Set([
  "norwegian-cruise-line_0",
  "trip-com_0",
]);

function normalize(pathname) {
  let p = pathname.replace(/\/+$/, ""); // drop trailing slash
  p = p.replace(/\.html$/, ""); // drop .html extension
  return p;
}

export async function onRequest(context) {
  const { request, next } = context;
  const url = new URL(request.url);
  const path = normalize(url.pathname);

  const m = path.match(/^\/deals\/([^/]+)$/);
  if (m && WITHDRAWN.has(m[1])) {
    return new Response(
      "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">" +
        "<meta name=\"robots\" content=\"noindex\">" +
        "<title>404 Not Found | TravelPromoHub</title></head>" +
        "<body style=\"font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem\">" +
        "<h1>404 &mdash; Offer withdrawn</h1>" +
        "<p>This offer is no longer available.</p>" +
        "<p><a href=\"/\">Back to all current deals</a></p></body></html>",
      {
        status: 404,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store, must-revalidate",
          "x-robots-tag": "noindex, nofollow",
        },
      }
    );
  }

  return next();
}
