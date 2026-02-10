import asyncio
import socket
from server_types import Protocol
from http1 import Request, Response

import base64
import hashlib
from enum import Enum

class WSRecvTimeoutError(Exception):
    """
    The Exception raised when recieve request times out
    """

class WSOpcode(Enum):
    CONTINUATION = 0x0
    TEXT         = 0x1
    BINARY       = 0x2
    CLOSE        = 0x8
    PING         = 0x9
    PONG         = 0xA

class WSPFrame:
    __data: bytes

    def __init__(self, data: bytes):
        if len(data) < 2:
            raise ValueError("Data too short to be a WebSocket frame")

        self.__data = data

    @property
    def fin(self) -> bool:
        return bool(self.__data[0] & 0x80)

    @property
    def opcode(self) -> WSOpcode:
        return WSOpcode(self.__data[0] & 0x0F)

    @property
    def masked(self) -> bool:
        return bool(self.__data[1] & 0x80)

    @property
    def payload_length(self) -> int:
        length = self.__data[1] & 0x7F

        if length < 126:
            return length

        if length == 126:
            return int.from_bytes(self.__data[2:4], "big")

        return int.from_bytes(self.__data[2:10], "big")

    def _header_length(self) -> int:
        length = self.__data[1] & 0x7F

        if length < 126:
            return 2
        if length == 126:
            return 4
        return 10

    @property
    def masking_key(self) -> bytes | None:
        if not self.masked:
            return None

        start = self._header_length()
        return self.__data[start:start + 4]

    @property
    def data(self) -> str | bytes:
        header_len = self._header_length()
        offset = header_len + (4 if self.masked else 0)

        payload = self.__data[offset:offset + self.payload_length]

        # Unmask if needed
        if self.masked:
            key = self.masking_key
            payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))

        # Decode based on opcode
        if self.opcode == WSOpcode.TEXT:
            try:
                return payload.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ValueError("Invalid UTF-8 in TEXT frame") from e

        return payload

class WSPortal():

    slugs : dict[str, str] = {}

    def __init__(self, slugs, 
                 client : socket.socket, 
                 recv_queue : asyncio.Queue,
                 pong_waiters : asyncio.Future
                 ):
        
        self.__client = client
        self.__recv_queue = recv_queue
        self.__pong_waiters = pong_waiters

        self.__closed = False
        self.slugs = slugs
        pass

    @property
    def closed(self): return self.__closed

    async def recv(timeout : float = None) -> str | bytes:
        """
        Recieves a full frame from the client

        If the frame is fragmented, WSPortal.recv() will combine the fragments into the full frame
        
        :param timeout: If specified, the max time before server raises a WSRecvTimeoutError
        :type timeout: float
        :return: The data of the full frame
        :rtype: str | bytes
        """

        pass

    async def recv_frag(timeout : float = None) -> str | bytes:
        """
        Recieves a single frame from the client

        This is different from WSPortal.recv where if the client sends a fragmented frame,
        it will only capture the first fragment of the frame
        
        :param timeout: If specified, the max time before server raises a WSRecvTimeoutError
        :type timeout: float
        :return: The data of the first frame
        :rtype: str | bytes
        """


        pass

    def send(payload : str | bytes):
        """
        Sends a payload for the client to recieve
        
        :param payload: Data to send to the client
        :type payload: str | bytes
        """
        pass

    async def ping(timeout : float) -> bool:
        """
        Pings client to confirm that client is still connected
        
        :param timeout: How long before ping times out and returns false
        :type timeout: float
        :return: If client returns with a *Pong* client frame
        :rtype: bool
        """
        pass

class WebSocketProtocol(Protocol):

    __WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __compute_accept_key(self, sec_key: str) -> str:
        sha1 = hashlib.sha1((sec_key + self.__WS_GUID).encode("ascii")).digest()
        return base64.b64encode(sha1).decode("ascii")

    def get_config_key(self):
        return "websocket13_config"

    def get_target_endpoints(self) -> list[str]:
        return ["WEBSOCKET"]
    
    def identify(self, initial_data) -> bool:
        self.inital_req : Request = Request(initial_data)

        if self.inital_req.headers.get("Connection") != "Upgrade":
            return False
        
        if self.inital_req.headers.get("Upgrade", "").lower() != "websocket":
            return False
        
        return True
    
    def handshake(self, client) -> bool:
        req = self.inital_req

        if req.method != "GET":
            client.send(Response(400).to_bytes())
            return False
        
        if "Host" not in req.headers:
            client.send(Response(400).to_bytes())
            return False

        version = req.headers.get("Sec-WebSocket-Version")

        if version != "13":
            resp = Response(
                426,
                headers={
                    "Upgrade": "websocket",
                    "Sec-WebSocket-Version": "13"
                }
            )
            
            client.send(resp.to_bytes())
            return False

        key = req.headers.get("Sec-WebSocket-Key")
        if not key:
            client.send(Response(400).to_bytes())
            return False

        try:
            raw = base64.b64decode(key, validate=True)
            if len(raw) != 16:
                raise ValueError
        except Exception:
            client.send(Response(400).to_bytes())
            return False

        accept_key = self.__compute_accept_key(key)

        resp = Response(
            status_code=101,
            headers={
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Accept": accept_key
            }
        )

        client.send(resp.to_bytes())
        return True

    async def handle(self, client : socket.socket, slugs : dict[str, str], endpoints : dict[str, any]):
        
        """
        Handles connection from client until socket is closed
        
        :param client: the socket connection between client and server
        :param slugs: any slugs they used to get 
        :param endpoints: Description
        """

        portal : WSPortal = WSPortal(slugs=slugs)

        for endpoint in endpoints:
            if endpoint in WebSocketProtocol.get_target_endpoints():
                endpoints[endpoint](portal)
                break
        else:
            raise FileNotFoundError()

        pass

