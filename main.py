from fastapi import FastAPI,Depends,HTTPException,status
from models import URLRequest
from database import get_db
from fastapi.responses import RedirectResponse,FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

def encode_base62(num):
    num = (num*3001) + 1000000000 
    base = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    slug = ""
    while(num != 0):
        remainder = num % 62
        slug += base[remainder]
        num = num // 62
    
    reversed_slug = slug[::-1]
    return reversed_slug


@app.get("/")
def serve_ui():
    return FileResponse("static/index.html")

@app.post("/shorten")
def url_shortner(request : URLRequest, db = Depends(get_db)):
    cur = db.cursor()
    cur.execute("INSERT INTO urls (original_url) VALUES (%s) RETURNING id", (request.url,))
    row = cur.fetchone()
    if row is not None:
        user_id = row[0]
        slug = encode_base62(user_id)
        sql_query = "UPDATE urls SET slug = %s WHERE id = %s;"
        cur.execute(sql_query, (slug,user_id))
        db.commit()
        return {
            "slug": slug,
            "original_url":request.url
        }

    else:
        print("No user found with that ID.")

@app.get("/{slug}")
def get_slug(slug : str, db = Depends(get_db)):
    cur = db.cursor()
    cur.execute("UPDATE urls SET click_count = click_count + 1 WHERE slug = %s RETURNING original_url", (slug,))
    row = cur.fetchone()
    if row is not None:
        original_url = row[0]
        db.commit()
        return RedirectResponse(url=original_url, status_code=301)
    else:
        raise HTTPException(
            status_code=404,
            detail="Slug not found"
        )

    
