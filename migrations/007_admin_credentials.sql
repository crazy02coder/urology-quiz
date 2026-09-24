CREATE TABLE admin_credentials (
 id INTEGER PRIMARY KEY CHECK(id = 1),
 username TEXT NOT NULL,
 password_hash TEXT NOT NULL,
 updated_at REAL NOT NULL
);
