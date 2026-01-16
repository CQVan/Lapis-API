from lapis import Response, Request

async def GET (req : Request) -> Response:
    return Response(200, "Other Hello World!")