import psycopg2

def get_db():
    conn = psycopg2.connect("dbname=postgres user=postgres password=postgres123 host=localhost")
    try:
        yield conn
    finally:
        conn.close()