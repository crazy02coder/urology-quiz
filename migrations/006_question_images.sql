CREATE TABLE question_images (
 id TEXT PRIMARY KEY,
 question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
 position INTEGER NOT NULL,
 placement TEXT NOT NULL CHECK(placement IN ('question','explanation')),
 mime_type TEXT NOT NULL CHECK(mime_type IN ('image/png','image/jpeg','image/webp')),
 data BLOB NOT NULL,
 UNIQUE(question_id,position)
);
