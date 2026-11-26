"""Minimal stand-in for the WordPress REST API used by the end-to-end suite."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
posts: dict[int, dict] = {}
_next_id = [100]


@app.get("/wp-json/wp/v2/users/me")
def me():
    return {"name": "editor"}


@app.post("/wp-json/wp/v2/posts")
async def create(request: Request):
    _next_id[0] += 1
    posts[_next_id[0]] = await request.json()
    return JSONResponse(status_code=201, content={"id": _next_id[0], "link": f"http://wp.test/?p={_next_id[0]}",
                                                  "status": posts[_next_id[0]]["status"]})


@app.post("/wp-json/wp/v2/posts/{post_id}")
async def update(post_id: int, request: Request):
    if post_id not in posts:
        return JSONResponse(status_code=404, content={"message": "Invalid post ID."})
    posts[post_id] = await request.json()
    return {"id": post_id, "link": f"http://wp.test/?p={post_id}", "status": posts[post_id]["status"]}


@app.get("/_posts")
def all_posts():
    return [{"id": pid, **post} for pid, post in posts.items()]
