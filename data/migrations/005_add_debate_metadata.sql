ALTER TABLE ai_theses ADD COLUMN debate_mode TEXT NOT NULL DEFAULT 'full';
ALTER TABLE ai_theses ADD COLUMN citation_density REAL NOT NULL DEFAULT 0.0;
