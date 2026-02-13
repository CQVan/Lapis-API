from lapis.protocols.http1 import Request, Response
from lapis.protocols.websocket import WSPortal

async def WEBSOCKET(portal : WSPortal):

    while not portal.closed:
        payload = await portal.recv()
        portal.send(payload=payload)

        await portal.ping(1000)

    pass

async def GET(req : Request) -> Response:
    return Response(body="Isn't this the Websocket test?")