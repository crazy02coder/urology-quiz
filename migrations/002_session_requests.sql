CREATE TABLE session_requests (
 request_id TEXT NOT NULL, exam_id TEXT NOT NULL REFERENCES exams(id),
 session_id TEXT NOT NULL REFERENCES sessions(id), PRIMARY KEY(request_id,exam_id)
);
