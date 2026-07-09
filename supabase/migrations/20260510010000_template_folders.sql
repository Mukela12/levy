-- Folders for templates. Mirrors document_folders but scoped to the
-- templates table. Owner-only (no global folders).

CREATE TABLE IF NOT EXISTS template_folders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id UUID NOT NULL,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS template_folders_owner_idx ON template_folders(owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS template_folders_owner_name_idx
  ON template_folders(owner_id, lower(name));

ALTER TABLE templates
  ADD COLUMN IF NOT EXISTS folder_id UUID
  REFERENCES template_folders(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS templates_folder_idx ON templates(folder_id);
