// Internal-only cleanup for deployment verification; no HTTP endpoint exposes this.
import pg from 'pg';
const device = process.argv[2];
if (device !== 'check' && !/^[0-9a-f-]{36}$/.test(device || '')) throw new Error('Expected test device UUID');
const db = new pg.Client({ connectionString: process.env.DATABASE_URL, connectionTimeoutMillis: 10000 });
try {
  await db.connect();
  if (device === 'check') await db.query('select 1');
  else await db.query("delete from public.students where device_id=$1 and hostname='arslanbek-deployment-smoke'", [device]);
  console.info('Test database operation complete.');
} catch { console.error('Test database operation failed.'); process.exitCode = 1; }
finally { await db.end(); }
