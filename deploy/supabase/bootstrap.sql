-- Run once in the chosen Supabase project's SQL editor before Railway startup.
-- App tables stay outside the schemas exposed by Supabase's Data API.
BEGIN;
CREATE SCHEMA IF NOT EXISTS framebounty;
REVOKE ALL ON SCHEMA framebounty FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA framebounty FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA framebounty FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA framebounty REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA framebounty REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- Never convert an existing public bucket or overwrite its objects silently.
INSERT INTO storage.buckets (id, name, public)
VALUES ('framebounty-media', 'framebounty-media', false)
ON CONFLICT (id) DO NOTHING;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM storage.buckets WHERE id='framebounty-media' AND public) THEN
    RAISE EXCEPTION 'framebounty-media must be a private bucket; select a dedicated private project/bucket';
  END IF;
END $$;
-- No anon/authenticated storage policies: only the server service-role key reads
-- objects. FrameBounty app sessions are not Supabase Auth JWTs.
COMMIT;
