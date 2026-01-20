from lapis import Request, Response

async def GET(req : Request) -> Response:
    return Response(status_code=200, body=f"the slugs were: {req.slugs}")