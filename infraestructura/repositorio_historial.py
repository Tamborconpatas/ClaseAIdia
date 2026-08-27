import sqlite3
import datetime
import os

DB_PATH = "transcriptions_history.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            date TEXT NOT NULL,
            backend TEXT NOT NULL,
            text_content TEXT,
            srt_content TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_transcription(filename: str, backend: str, text_content: str, srt_content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO transcriptions (filename, date, backend, text_content, srt_content)
        VALUES (?, ?, ?, ?, ?)
    ''', (os.path.basename(filename), now, backend, text_content, srt_content))
    conn.commit()
    conn.close()

def get_all_transcriptions():
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, filename, date, backend, text_content, srt_content FROM transcriptions ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "filename": r[1],
            "date": r[2],
            "backend": r[3],
            "text": r[4],
            "srt": r[5]
        })
    return result

init_db()
