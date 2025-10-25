-- Run this in the Supabase SQL editor for your project
-- Enables pgcrypto (for gen_random_uuid) and creates the patient_records table

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS public.patient_records (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_name text,
  age integer,
  gender text,
  symptoms_text text,
  image_file_url text,
  voice_file_url text,
  ai_diagnosis text,
  confidence integer,
  triage_level text,
  explanation text,
  created_at timestamptz DEFAULT now()
);

-- Optional: create a basic index for triage level and created_at
CREATE INDEX IF NOT EXISTS idx_patient_records_triage_level ON public.patient_records (triage_level);
CREATE INDEX IF NOT EXISTS idx_patient_records_created_at ON public.patient_records (created_at);
