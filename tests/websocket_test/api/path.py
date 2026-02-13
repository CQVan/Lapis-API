from lapis.protocols.http1 import Request, Response
from lapis.protocols.websocket import WSPortal

async def WEBSOCKET(portal : WSPortal):

    while not portal.closed:
        payload = await portal.recv()
        portal.send(payload=payload)

    pass

async def GET(req : Request) -> Response:
    return Response(body="Isn't this the Websocket test?")