/* Необязательный прокси на Cloudflare Workers (бесплатный тариф).
   Нужен только если archive.org не отдаёт данные в браузер из-за CORS.
   После деплоя впишите адрес в webapp/sources.js -> PROXY,
   например: export const PROXY = 'https://kitob-proxy.ваш-аккаунт.workers.dev/?u='; */
const ALLOWED = ['archive.org', 'gutendex.com', 'www.gutenberg.org', 'gutenberg.org'];

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const target = url.searchParams.get('u');
    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }));
    if (!target) return new Response('missing ?u=', { status: 400 });

    let dest;
    try { dest = new URL(target); } catch { return new Response('bad url', { status: 400 }); }
    if (!ALLOWED.some((h) => dest.hostname === h || dest.hostname.endsWith('.' + h))) {
      return new Response('host not allowed', { status: 403 });
    }

    const res = await fetch(dest.toString(), { headers: { 'User-Agent': 'KitobProxy/1.0' }, redirect: 'follow' });
    return cors(new Response(res.body, { status: res.status, headers: res.headers }));
  },
};

function cors(res) {
  const h = new Headers(res.headers);
  h.set('Access-Control-Allow-Origin', '*');
  h.set('Access-Control-Allow-Headers', '*');
  h.set('Access-Control-Allow-Methods', 'GET,OPTIONS');
  return new Response(res.body, { status: res.status, headers: h });
}
