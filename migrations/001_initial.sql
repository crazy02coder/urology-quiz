CREATE TABLE exams (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE questions (
 id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id), position INTEGER NOT NULL,
 text TEXT NOT NULL, options TEXT NOT NULL, correct INTEGER NOT NULL CHECK(correct BETWEEN 0 AND 4),
 UNIQUE(exam_id,position)
);
CREATE TABLE sessions (
 id TEXT PRIMARY KEY, exam_id TEXT NOT NULL REFERENCES exams(id),
 phase TEXT NOT NULL DEFAULT 'lobby' CHECK(phase IN ('lobby','question','results','finished')),
 question_index INTEGER NOT NULL DEFAULT -1, deadline REAL, version INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL, finished_at REAL
);
CREATE TABLE participants (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), nickname TEXT NOT NULL,
 nickname_key TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, created_at REAL NOT NULL,
 UNIQUE(session_id,nickname_key), UNIQUE(id,session_id)
);
CREATE TABLE answers (
 participant_id TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES sessions(id),
 question_id TEXT NOT NULL REFERENCES questions(id), choice INTEGER NOT NULL CHECK(choice BETWEEN 0 AND 4),
 answered_at REAL NOT NULL, PRIMARY KEY(participant_id,question_id),
 FOREIGN KEY(participant_id,session_id) REFERENCES participants(id,session_id)
);
CREATE INDEX idx_answers_session_question ON answers(session_id,question_id);
CREATE TABLE admin_sessions (token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE login_attempts (client_key TEXT PRIMARY KEY, count INTEGER NOT NULL, window_start REAL NOT NULL);
CREATE TABLE previews (
 id TEXT PRIMARY KEY, admin_hash TEXT NOT NULL, title TEXT NOT NULL, questions TEXT NOT NULL,
 expires_at REAL NOT NULL, exam_id TEXT REFERENCES exams(id)
);
