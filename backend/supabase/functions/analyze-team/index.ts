import { createHandler } from './handler.mjs';

Deno.serve(createHandler({
  SUPABASE_URL: Deno.env.get('SUPABASE_URL'),
  SUPABASE_ANON_KEY: Deno.env.get('SUPABASE_ANON_KEY'),
  SUPABASE_SERVICE_ROLE_KEY: Deno.env.get('SUPABASE_SERVICE_ROLE_KEY'),
  OPENAI_API_KEY: Deno.env.get('OPENAI_API_KEY'),
  AI_MODEL: Deno.env.get('AI_MODEL'),
  ALLOWED_ORIGINS: Deno.env.get('ALLOWED_ORIGINS'),
}));
