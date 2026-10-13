// Canonical-host redirect.
//
// The site now lives on its own domain. Any request that arrives on the old
// Cloudflare Pages hostname (travelpromohub-site.pages.dev, plus per-deployment
// preview aliases like <hash>.travelpromohub-site.pages.dev) is permanently
// redirected to the canonical domain, so the two hosts never serve two versions.
//
// Runs at the edge before static assets / route handlers, so it applies to every
// path. Requests already on the canonical host fall straight through.

const CANONICAL_HOST = "travelpromohub.com";

export async function onRequest(context) {
  const url = new URL(context.request.url);
  const host = url.hostname.toLowerCase();

  if (host !== CANONICAL_HOST && host.endsWith(".pages.dev")) {
    return Response.redirect(
      `https://${CANONICAL_HOST}${url.pathname}${url.search}`,
      301
    );
  }

  return context.next();
}
