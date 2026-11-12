# Deploying MediPos

Three pieces that can live in three different places: the Django API (the only thing that holds
data and business rules), the Next.js web app, and the Expo phone app.

- [Web app on Vercel](#web-app-on-vercel)
- [Exposing a local Django server](#exposing-a-local-django-server) — tunnels, and which one to pick
- [Whole stack on one server](#whole-stack-on-one-server-coolify-or-plain-docker)

---

## Web app on Vercel

The web app is a pure client: every page runs in the browser, talks to the API with a bearer token,
and does no server-side fetching. Nothing in the build needs the API to be reachable, so a Vercel
build never waits on your backend.

**Project settings**

| Setting | Value |
| --- | --- |
| Framework preset | Next.js (detected) |
| Root Directory | `frontend` |
| Build / install command | leave as detected (`next build` / `npm ci`) |
| Node version | 22 or newer |

**Environment variables** (Settings → Environment Variables, for Production *and* Preview):

```
NEXT_PUBLIC_API_URL=https://api-medipos.example.com
NEXT_PUBLIC_CURRENCY=PKR
NEXT_PUBLIC_BUSINESS_NAME=Your Pharmacy Name
```

`NEXT_PUBLIC_*` values are compiled into the JavaScript bundle, so **changing one needs a redeploy**,
not just a restart.

**The API must be HTTPS.** A page served from `https://…vercel.app` cannot call `http://localhost:8000`
— the browser blocks it as mixed content, and `localhost` on the visitor's machine is not your
machine anyway. That is what the tunnel below is for.

**On the Django side**, add the Vercel origin:

```
CORS_ALLOWED_ORIGINS=https://medipos.vercel.app,https://app.example.com
# Preview deployments get a new URL each time; allow them with a narrow regex:
CORS_ALLOWED_ORIGIN_REGEXES=^https://medipos-[a-z0-9-]+\.vercel\.app$
FRONTEND_URL=https://medipos.vercel.app     # used in password-reset emails
```

`output: "standalone"` is only applied when `DOCKER_BUILD=1` (set by `frontend/Dockerfile`), so
Vercel builds the app its own way. Nothing else in the repo is Vercel-specific.

---

## Exposing a local Django server

The backend runs on your machine, which has no fixed IP and sits behind NAT. A tunnel gives it a
public HTTPS hostname by making an outbound connection, so no port forwarding and no static IP.

### Recommended: Cloudflare Tunnel

Free, keeps the **same hostname forever**, terminates TLS for you, reconnects by itself, and runs as
a service so it survives reboots. You need a domain on Cloudflare (a cheap one is fine).

1. Add your domain to Cloudflare (free plan).
2. Zero Trust dashboard → **Networks → Tunnels → Create a tunnel** → *Cloudflared*. Name it
   `medipos`, and copy the token it shows.
3. Add a **public hostname**: `api-medipos.example.com` → service `http://backend:8000`
   (or `http://localhost:8000` if you run cloudflared outside Docker).
4. Run it:

   ```bash
   # with the compose stack (token in .env as CLOUDFLARE_TUNNEL_TOKEN)
   docker compose --profile tunnel up -d cloudflared

   # or directly on the machine, installed as a service that starts on boot
   cloudflared service install <your-token>
   ```

5. Point the clients at it and tell Django about the hostname:

   ```
   # backend .env
   DJANGO_ALLOWED_HOSTS=api-medipos.example.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://api-medipos.example.com
   CORS_ALLOWED_ORIGINS=https://medipos.vercel.app
   SECURE_SSL_REDIRECT=1

   # Vercel
   NEXT_PUBLIC_API_URL=https://api-medipos.example.com
   # phone/.env
   EXPO_PUBLIC_API_URL=https://api-medipos.example.com
   ```

Django already trusts `X-Forwarded-Proto` (`SECURE_PROXY_SSL_HEADER`), which is what cloudflared
sends, so HTTPS detection and the redirect work behind the tunnel without further changes.

A Cloudflare tunnel exposes the hostname to the whole internet. If this is a real pharmacy's data,
also put Cloudflare Access (Zero Trust) in front of `/admin/` — or keep the admin off the tunnel
entirely and reach it over the LAN.

### Alternatives

| Option | Stable hostname | Cost | Good for |
| --- | --- | --- | --- |
| **Cloudflare Tunnel** | Yes, your own subdomain | Free (needs a domain) | What you want here: production-ish, long-lived |
| **ngrok** | One static domain on the free plan (`something.ngrok-free.app`) | Free / paid | Quickest start; `ngrok http 8000 --url=your-name.ngrok-free.app` |
| **Tailscale Funnel** | Yes (`machine.tailnet.ts.net`) | Free | Already using Tailscale; simplest if so |
| **localtunnel / serveo** | No, changes every run | Free | A one-off demo, not for anything you depend on |

Rules of thumb: a tunnel whose URL changes on every restart is unusable here, because
`NEXT_PUBLIC_API_URL` is baked into the Vercel build and the phone app — you would redeploy both
every time. Pick one with a fixed hostname. Also remember the tunnel is only up while your machine
is: if the laptop sleeps, the shop's POS stops. For a real deployment, move the backend to a small
VPS (the Docker Compose stack below runs as-is) and keep the tunnel for development.

### Development without a tunnel

Everything on your own machine or LAN needs no tunnel at all:

```
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
# phone/.env — the Android emulator's alias for your machine
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000
# a real phone on the same Wi-Fi: your machine's LAN address
EXPO_PUBLIC_API_URL=http://192.168.1.20:8000
```

With a LAN address also set `DJANGO_ALLOWED_HOSTS=192.168.1.20,localhost` and run
`python manage.py runserver 0.0.0.0:8000`.

---

## Whole stack on one server (Coolify or plain Docker)

```bash
cp .env.example .env     # fill in secrets and your domains
docker compose up -d --build
```

On Coolify: create a **Docker Compose** resource from this repository, paste the variables from
`.env.example`, and give `backend` (port 8000) and `frontend` (port 3000) their domains. Coolify
terminates TLS, so leave `SECURE_SSL_REDIRECT=1`. Redeploy the frontend after changing
`NEXT_PUBLIC_API_URL`, since it is a build-time value.

Uploaded files — medicine photos and prescription scans — live in `MEDIA_ROOT`, which the compose
file keeps on a named volume. Django serves them at `/media/` by default; for a busy shop put a web
server or CDN in front of that path and set `SERVE_MEDIA=0`.

Mixing the two is fine and common: API on a VPS or behind a tunnel, web app on Vercel. The API is
the only service that needs the database, Redis and the Celery workers.
