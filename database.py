import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_db():
    conn = psycopg2.connect(os.environ.get("DATABASE_URL", "dbname=postgres user=postgres password=postgres123 host=localhost"))
    try:
        yield conn
    finally:
        conn.close()
