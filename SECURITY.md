# Security

## Trust model

MACU Studio is a **single-user, self-hosted** tool. By design it runs on a machine you control and
trust, and it has **no built-in authentication** on its own surfaces:

- the Studio web app + REST API (`:8774`, includes the MCP server at `/mcp`)
- the render service (`:8773`)

All three **bind to loopback (`127.0.0.1`) by default**, so out of the box nothing is reachable from
other machines.

### Exposing on a LAN

Setting `MACU_STUDIO_HOST=0.0.0.0` (or `MACU_RENDER_HOST=0.0.0.0`) binds these servers to all
interfaces so you can reach Studio from another device on your network. **There is still no
authentication**, so anyone who can reach the port can drive the full API — write manifests, trigger
GPU renders, and publish. Only do this on a **trusted network**.

Do **not** expose `:8774` / `:8773` / `/mcp` directly to the public internet. If you need remote
access, put them behind something that authenticates first — a VPN/tailnet, or a reverse proxy with
auth in front (e.g. Cloudflare Access, an authenticating proxy, or HTTP basic auth). Note that
surveillance/most-CDN ToS aside, the practical risk here is an open, unauthenticated control surface,
not a data leak: no endpoint returns stored credentials (the macu-web connect token is write-only via
the API and redacted from status responses).

### Credentials

- The macu-web connect token is stored at `~/.config/macu-studio/macu-web.json` with `0600`
  permissions (owner-only). Treat that file as a secret.
- `.env` files are gitignored. Never commit secrets.

## Studio is not the web-side security boundary

When you publish to a hosted site (e.g. macu-web), **the server is the authoritative security
boundary** — it must treat everything Studio pushes (manifests, scripts, metadata, titles) as
untrusted input and validate/sanitize it server-side. Studio's own validation is advisory (early
feedback in the Publish UI); because Studio is open source, a determined party can push arbitrary
content straight to the publish endpoint, so the receiving server cannot rely on Studio having
checked anything.

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue: email
**august.wasilowski@gmail.com** with details and reproduction steps. You'll get an acknowledgement and
a fix timeline.
