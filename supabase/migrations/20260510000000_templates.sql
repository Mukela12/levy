-- Templates: user-owned reusable document skeletons (.docx, .pdf, .txt, .md)
-- the agent can suggest and use to draft new documents.

CREATE TABLE IF NOT EXISTS templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  file_type TEXT NOT NULL,           -- 'docx' | 'pdf' | 'txt' | 'md'
  file_size_bytes INTEGER,
  storage_path TEXT NOT NULL,        -- '<bucket>/<key>' as the rest of the
                                     -- codebase stores paths
  preview_text TEXT,                 -- first ~2000 chars extracted at upload
                                     -- so the suggest_templates tool can rank
                                     -- without re-fetching the file
  page_count INTEGER,                -- nullable; populated for pdf/docx
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS templates_owner_idx ON templates(owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS templates_owner_name_idx ON templates(owner_id, lower(name));

-- Storage bucket for the actual files. Idempotent — does nothing if it already
-- exists. Bucket is private; the app mints signed URLs on demand.
INSERT INTO storage.buckets (id, name, public)
VALUES ('templates', 'templates', false)
ON CONFLICT (id) DO NOTHING;
