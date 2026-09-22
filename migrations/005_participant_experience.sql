ALTER TABLE participants ADD COLUMN experience_years INTEGER NOT NULL DEFAULT 0
CHECK(experience_years BETWEEN 0 AND 60);
