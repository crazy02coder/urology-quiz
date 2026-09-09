ALTER TABLE sessions ADD COLUMN question_duration_seconds INTEGER NOT NULL DEFAULT 45
CHECK(question_duration_seconds BETWEEN 5 AND 300);
