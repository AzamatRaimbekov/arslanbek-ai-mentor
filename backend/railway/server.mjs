import { createServer } from 'node:http';
import { Readable } from 'node:stream';
import { bootstrap } from './bootstrap.mjs';
import { createGateway } from './gateway.mjs';

const env = { ...process.env };
const port = Number(env.PORT || 8080);
for (const key of ['SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'AUTH_URL', 'REST_URL', 'REST_HEALTH_URL', 'ALLOWED_ORIGINS']) {
  if (!env[key]) throw new Error(`Missing ${key}`);
}
// The analysis handler calls this same gateway over loopback; secrets never reach the browser.
env.SUPABASE_URL = `http://127.0.0.1:${port}`;
let ready = false;
const gateway = createGateway(env, { isReady: () => ready });
const server = createServer({ requestTimeout: 30000, headersTimeout: 15000 }, async (incoming, outgoing) => {
  try {
    const chunks = []; let length = 0;
    for await (const chunk of incoming) {
      length += chunk.length;
      if (length > 5 * 1024 * 1024) { outgoing.writeHead(413).end(); return; }
      chunks.push(chunk);
    }
    const method = incoming.method || 'GET';
    const request = new Request(`http://localhost${incoming.url}`, { method, headers: incoming.headers,
      ...(['GET', 'HEAD'].includes(method) ? {} : { body: Buffer.concat(chunks) }) });
    const response = await gateway(request);
    outgoing.writeHead(response.status, Object.fromEntries(response.headers));
    if (response.body) Readable.fromWeb(response.body).on('error', () => outgoing.destroy()).pipe(outgoing);
    else outgoing.end();
  } catch { if (!outgoing.headersSent) outgoing.writeHead(500, { 'Content-Type': 'application/json' }).end('{"error":"Request failed"}'); else outgoing.destroy(); }
});
server.listen(port, '::', () => console.info(`Backend listening on ${port}`));
bootstrap(env).then(() => { ready = true; }).catch(error => {
  console.error('Bootstrap failed:', error.code || error.message);
  server.close(() => process.exit(1));
  setTimeout(() => process.exit(1), 5000).unref();
});
process.on('SIGTERM', () => { ready = false; server.close(() => process.exit(0)); setTimeout(() => process.exit(0), 10000).unref(); });
