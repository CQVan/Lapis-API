"""
The Module containing Lapis' native WebSocket Protocol Handler
"""

import asyncio
import binascii
from dataclasses import dataclass
from datetime import datetime
import socket
import base64
import hashlib
from enum import Enum

from lapis.server_types import Protocol
from lapis.protocols.http1 import Request, Response


@dataclass
class WSConfig:
    """
    The class containing all configuration settings for a Lapis WebSocket connection
    """


class WSRecvTimeoutError(Exception):
    """
    The Exception raised when recieve request times out
    """


class WSRecvInvalidFrameError(Exception):
    """
    The Exception raised when the recieved frame is invalid
    """


class WSPortalClosedError(Exception):
    """
    The Exception raised when trying to recieve/send from a closed portal
    """


class WSOpcode(Enum):
    """
    The class containing all opcodes for a WSFrame to contain
    """

    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


class WSFrame:
    """
    The class used to handle frame data between server and client
    """

    __data: bytes

    def __init__(self, data: bytes):
        if len(data) < 2:
            raise ValueError("Data too short to be a WebSocket frame")

        self.__data = data

    @property
    def fin(self) -> bool:
        """
        Returns if this frame is the final frame of the payload

        Used for fragmented data frames

        :rtype: bool
        """

        return bool(self.__data[0] & 0x80)

    @property
    def opcode(self) -> WSOpcode:
        """
        Returns the frame's opcode; the operation the frame is supposed to communicate

        :rtype: WSOpcode
        """

        return WSOpcode(self.__data[0] & 0x0F)

    @property
    def masked(self) -> bool:
        """
        Returns of the payload of the frame is masked

        :rtype: bool
        """

        return bool(self.__data[1] & 0x80)

    @property
    def payload_length(self) -> int:
        """
        Returns the length of the payload specified in the frame header

        :rtype: int
        """

        length = self.__data[1] & 0x7F

        if length < 126:
            return length
        if length == 126:
            return int.from_bytes(self.__data[2:4], "big")
        return int.from_bytes(self.__data[2:10], "big")

    def __header_length(self) -> int:
        """
        Returns the length of the header of the frame

        :rtype: int
        """

        length = self.__data[1] & 0x7F

        if length < 126:
            return 2
        if length == 126:
            return 4
        return 10

    @property
    def masking_key(self) -> bytes | None:
        """
        Returns the masking key of the frame used to mask the payload

        returns None if the frame isn't masked

        :rtype: bytes | None
        """

        if not self.masked:
            return None

        start = self.__header_length()
        return self.__data[start : start + 4]

    @property
    def data(self) -> str | bytes:
        """
        Returns the payload data of the frame

        returns either string or bytes depending on the opcode

        :rtype: str | bytes
        """
        header_len = self.__header_length()
        offset = header_len + (4 if self.masked else 0)

        payload = self.__data[offset : offset + self.payload_length]

        # Unmask if needed
        if self.masked:
            payload = bytes(b ^ self.masking_key[i % 4] for i, b in enumerate(payload))

        # Decode based on opcode
        if self.opcode == WSOpcode.TEXT:
            try:
                return payload.decode("utf-8")
            except UnicodeDecodeError as e:
                raise ValueError("Invalid UTF-8 in TEXT frame") from e

        return payload

    def __str__(self) -> str:
        """
        Returns a stringified version of WSFrame for debugging purposes

        :rtype: str
        """

        payload_preview = self.data
        # Truncate if payload is too long for readability
        if isinstance(payload_preview, bytes):
            payload_preview = payload_preview[:50]
            payload_preview = payload_preview.hex() + (
                "..." if len(self.data) > 50 else ""
            )
        elif isinstance(payload_preview, str):
            payload_preview = payload_preview[:50] + (
                "..." if len(self.data) > 50 else ""
            )

        return (
            f"WSFrame(fin={self.fin}, opcode={self.opcode}, masked={self.masked}, "
            f"payload_length={self.payload_length}, payload={payload_preview})"
        )


class WSPortal:
    """
    The interface the Websocket endpoint function uses to communicate between server and client
    """

    slugs: dict[str, str] = {}

    def __init__(self, slugs, client: socket.socket):

        self.__client: socket.socket = client
        self.__client.setblocking(False)

        self.inital_req: Request = None

        self.__recv_queue: asyncio.Queue[WSFrame] = asyncio.Queue[WSFrame]()
        self.__pong_waiters = set()

        self.__closed: bool = False
        self.slugs: dict[str, str] = slugs

        asyncio.create_task(self.__reader())

    def __send_frame(
        self, opcode: WSOpcode, payload: str | bytes = b"", fin: bool = True
    ):
        """
        Utility function used to send frames from server to client

        :param opcode: The type of frame sent
        :type opcode: WSOpcode
        :param payload: The data sent with the frame
        :type payload: str | bytes
        :param fin: If the frame is fragmented
        :type fin: bool
        """
        if self.__closed:
            raise WSPortalClosedError()

        first_byte = (0x80 if fin else 0) | opcode.value

        length = len(payload)
        header = bytearray()
        header.append(first_byte)

        if length < 126:
            header.append(length)
        elif length < (1 << 16):
            header.append(126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(127)
            header.extend(length.to_bytes(8, "big"))

        data = payload if isinstance(payload, bytes) else payload.encode()

        self.__client.sendall(bytes(header) + data)

    async def __read_exact(self, bufsize: int):
        loop = asyncio.get_running_loop()
        data = b""
        try:
            while len(data) < bufsize:
                chunk = await loop.sock_recv(self.__client, bufsize - len(data))
                if not chunk:
                    raise ConnectionResetError("Connection Was Reset!")
                data += chunk
            return data
        except Exception as err:
            raise ConnectionError("Connection Error or Timeout") from err

    async def __reader(self):
        try:
            while not self.__closed:

                # Get First part of Header
                header: bytes = await self.__read_exact(2)
                length_bytes: bytes = header[1] & 0x7F

                payload_len: int = 0

                # Get payload length
                if length_bytes == 126:
                    length_bytes = await self.__read_exact(2)
                    payload_len = int.from_bytes(length_bytes, "big")
                elif length_bytes == 127:
                    length_bytes = await self.__read_exact(8)
                    payload_len = int.from_bytes(length_bytes, "big")
                else:
                    payload_len = length_bytes
                    length_bytes = b""

                # recieve mask if required
                has_mask: bool = bool(header[1] & 0x80)
                mask: bytes = await self.__read_exact(4) if has_mask else b""

                # recieve body
                body: bytes = await self.__read_exact(payload_len)

                # Build WSFrame correctly
                frame: WSFrame = WSFrame(header + length_bytes + mask + body)

                # react based on opcode
                if frame.opcode == WSOpcode.PING:
                    if not frame.fin:  # Cannot send fragmented control frames
                        self.close(1002)
                    else:
                        self.__send_frame(
                            opcode=WSOpcode.PONG,
                            payload=(
                                frame.data
                                if isinstance(frame.data, bytes)
                                else frame.data.encode()
                            ),
                        )
                elif frame.opcode == WSOpcode.CLOSE:
                    self.close()
                elif frame.opcode == WSOpcode.PONG:
                    for waiter in self.__pong_waiters:
                        if not waiter.done():
                            waiter.set_result(True)
                else:
                    await self.__recv_queue.put(frame)
        except Exception:
            self.close(1011)
            raise

    @property
    def closed(self):
        """
        Returns if the connection between the client and server is open
        """
        return self.__closed

    async def recv(self, timeout: float = None) -> str | bytes:
        """
        Recieves a full frame from the client

        If the frame is fragmented, WSPortal.recv() will combine the fragments into a full payload

        :param timeout: If specified, the max time before server raises a WSRecvTimeoutError
        :type timeout: float
        :return: The data of the full frame
        :rtype: str | bytes
        """

        if self.closed:
            raise WSPortalClosedError("Tried to recieve from a closed portal!")

        try:
            frame: WSFrame = await asyncio.wait_for(
                self.__recv_queue.get(), timeout=timeout
            )

            if frame.fin:  # Unfragmented frame
                current_time = datetime.now().strftime("%H:%M:%S")
                ip, _ = self.__client.getpeername()

                print(f"{current_time} Server <-WS- {ip}")
                return frame.data

            result = frame.data
            is_text = isinstance(result, str)

            while True:
                frame = await asyncio.wait_for(self.__recv_queue.get(), timeout=timeout)

                if frame.opcode != WSOpcode.CONTINUATION:
                    self.close(1002)
                    raise WSRecvInvalidFrameError("Expected continuation frame")

                result += frame.data if is_text else frame.data.decode()

                if frame.fin:
                    break

            current_time = datetime.now().strftime("%H:%M:%S")
            ip, _ = self.__client.getpeername()

            print(f"{current_time} Server <-WS- {ip}")

            return result

        except asyncio.TimeoutError as err:
            raise WSRecvTimeoutError() from err

    def send(self, payload: str | bytes):
        """
        Sends a payload for the client to recieve

        :param payload: Data to send to the client
        :type payload: str | bytes
        """

        if self.closed:
            raise WSPortalClosedError("Tried to send through a closed portal!")

        opcode = WSOpcode.BINARY if isinstance(payload, bytes) else WSOpcode.TEXT

        self.__send_frame(opcode=opcode, payload=payload)

        current_time = datetime.now().strftime("%H:%M:%S")
        ip, _ = self.__client.getpeername()

        print(f"{current_time} Server -WS-> {ip}")

    async def ping(self, timeout: float) -> bool:
        """
        Pings client to confirm that client is still connected

        :param timeout: How long before ping times out and returns false
        :type timeout: float
        :return: If client returns with a *Pong* client frame
        :rtype: bool
        """

        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        self.__pong_waiters.add(waiter)

        try:
            self.__send_frame(WSOpcode.PING)
            return await asyncio.wait_for(waiter, timeout=timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self.__pong_waiters.discard(waiter)

    def close(self, code: int = 1000):
        """
        Closes the connection between the server and client using the given close code

        :param code: The close code the server will send to the client (default 1000)
        :type code: int
        """

        if self.closed:
            return

        self.__send_frame(opcode=WSOpcode.CLOSE, payload=code.to_bytes(2, "big"))

        self.__closed = True
        self.__client.close()

        current_time = datetime.now().strftime("%H:%M:%S")
        ip, _ = self.__client.getpeername()

        arrow = "-X->" if code == 1000 else "-!X!->"

        print(f"{current_time} Server {arrow} {ip}")


class WebSocketProtocol(Protocol):
    """
    The protocol created to handle websocket connections between server and client
    """

    def __init__(self, config: dict[str, any]):
        self.__WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        self.__config = WSConfig(**config)
        self.inital_req: Request = None

    def __compute_accept_key(self, sec_key: str) -> str:
        sha1 = hashlib.sha1((sec_key + self.__WS_GUID).encode("ascii")).digest()
        return base64.b64encode(sha1).decode("ascii")

    def get_target_endpoints(self) -> list[str]:
        """
        :return: All Endpoint functions the WebSocket Protocol looks for
        :rtype: list[str]
        """
        return ["WEBSOCKET"]

    def identify(self, initial_data) -> bool:
        self.inital_req: Request = Request(initial_data)

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
                426, headers={"Upgrade": "websocket", "Sec-WebSocket-Version": "13"}
            )

            client.send(resp.to_bytes())
            return False

        # Create accept key

        key = req.headers.get("Sec-WebSocket-Key")
        if not key:
            client.send(Response(400).to_bytes())
            return False

        try:
            raw = base64.b64decode(key, validate=True)
            if len(raw) != 16:
                raise ValueError("Invalid key")
        except (binascii.Error, ValueError):
            client.send(Response(400).to_bytes())
            return False

        accept_key = self.__compute_accept_key(key)

        # Send protocol transfer success message
        resp = Response(
            status_code=101,
            headers={
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Accept": accept_key,
            },
        )

        client.send(resp.to_bytes())

        current_time = datetime.now().strftime("%H:%M:%S")
        ip, _ = client.getpeername()
        print(
            f"{current_time} {self.inital_req.method} {self.inital_req.base_url} <-WS-> {ip}"
        )

        return True

    async def handle(
        self, client: socket.socket, slugs: dict[str, str], endpoints: dict[str, any]
    ):
        """
        Handles connection from client until socket is closed

        :param client: the socket connection between client and server
        :param slugs: any slugs they used to get
        :param endpoints: Description
        """

        for endpoint in endpoints:
            if endpoint in self.get_target_endpoints():
                portal: WSPortal = WSPortal(slugs=slugs, client=client)
                await endpoints[endpoint](portal)
                return

        raise FileNotFoundError("No Websocket Endpoint Found!")
