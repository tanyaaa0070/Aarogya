-- Use this file in Supabase SQL editor to create safe INSERT policies for `patient_records`.
-- Option A: Allow authenticated users to INSERT (recommended for client-side inserts with auth)
-- Run this when your app requires authenticated users (via Supabase auth) to insert rows.

-- Enable RLS if not enabled
ALTER TABLE IF EXISTS public.patient_records ENABLE ROW LEVEL SECURITY;

-- Policy to allow authenticated inserts
CREATE POLICY IF NOT EXISTS allow_authenticated_inserts
  ON public.patient_records
  FOR INSERT
  TO authenticated
  WITH CHECK (auth.role() = 'authenticated' OR auth.uid() IS NOT NULL);

-- Option B: (Testing only) allow all inserts — NOT for production
-- CREATE POLICY allow_all_inserts
--   ON public.patient_records
--   FOR INSERT
--   USING ( true )
--   WITH CHECK ( true );

-- Option C: If you plan to do server-side inserts only, keep RLS and use a server-side service_role key
-- No policy changes required. Ensure your server uses the service role key and keeps it secret.
