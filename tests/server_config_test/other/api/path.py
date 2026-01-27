from lapis import Response, Request

async def GET (req : Request) -> Response:
    return Response(status_code=200, body="API path from a different api folder!")