"""
Module containing the HTTP 1/1.1 protocol implementation for Lapis server
"""

from datetime import datetime
from http import HTTPMethod, HTTPStatus
import socket
from typing import AsyncGenerator, Callable
from urllib.parse import parse_qsl, urlparse

from lapis.server_types import BadRequest, Protocol


class Request:

    """
    The object class for handling HTTP 1/1.1 requests from clients
    """

    def __init__(self, data: bytes):
        try:
            text = data.decode("iso-8859-1")
        except UnicodeDecodeError:
            raise BadRequest("Invalid encoding")

        if "\r\n\r\n" not in text:
            raise BadRequest("Malformed HTTP request")

        head, body = text.split("\r\n\r\n", 1)
        lines = head.split("\r\n")

        method, url, protocol = lines[0].split(" ", 2)
        self.method = HTTPMethod[method.upper()]

        if protocol not in ("HTTP/1.0", "HTTP/1.1"):
            raise BadRequest("Unsupported protocol")

        self.protocol = protocol
        self.headers = {}
        self.cookies = {}

        self.slugs = {}

        for line in lines[1:]:
            if ":" not in line:
                raise BadRequest("Malformed header")
            key, value = line.split(":", 1)
            self.headers[key.strip()] = value.strip()

        if protocol == "HTTP/1.1" and "Host" not in self.headers:
            raise BadRequest("Missing Host header")

        try:
            parsed = urlparse(url)
        except ValueError as exc:
            raise BadRequest("Bad URL") from exc
        
        self.base_url = parsed.path
        self.query_params = dict(parse_qsl(parsed.query))
        self.body = body

class Response:

    """
    The object class for forming a HTTP 1/1.1 response to the client from the server
    """

    def __init__(self, 
                 status_code : int | HTTPStatus = HTTPStatus.OK, 
                 body : str = "",
                 headers : dict[str, any] = None, 
                 ):
        self.status_code = status_code if isinstance(status_code, HTTPStatus) else HTTPStatus(status_code)
        self.protocol = "HTTP/1.1"
        self.headers = headers if headers is not None else {
            "Content-Type": "text/plain",
        }
        self.cookies = {}
        self.body = body

    @property
    def reason_phrase(self):
        return self.status_code.phrase

    def to_bytes(self):
        body_bytes = self.body.encode('utf-8')
        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = len(body_bytes)

        response_line = f"{self.protocol} {self.status_code.value} {self.reason_phrase}\r\n"
        headers = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
        cookies = "".join(f"Set-Cookie: {k}={v}\r\n" for k, v in self.cookies.items())

        return (response_line + headers + cookies + "\r\n").encode('utf-8') + body_bytes

class StreamedResponse(Response):

    """
    A variant of the Response class that allows the server to stream back a response to the client
    """

    def __init__(self, stream : Callable[[Request], AsyncGenerator[bytes, None]], status_code = HTTPStatus.OK, headers = None):
        super().__init__(status_code, "", headers)
        
        self.stream = stream

        self.headers["Transfer-Encoding"] = "chunked"

    def get_head(self) -> bytes:
        response_line = f"{self.protocol} {self.status_code.value} {self.reason_phrase}\r\n"
        headers = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
        cookies = "".join(f"Set-Cookie: {k}={v}\r\n" for k, v in self.cookies.items())

        return (response_line + headers + cookies + "\r\n").encode('utf-8')

class HTTP1Protocol(Protocol):

    """
    The protocol created to handle HTTP 1/1.1 communications between server and client
    """

    request : Request = None

    def get_config_key(self):
        return "http1.x_config"

    def get_target_endpoints(self) -> list[str]:
        return [method.name for method in HTTPMethod]

    def identify(self, initial_data):
        try: 
            self.request = Request(initial_data)
            return True
        except BadRequest:
            return False
    
    def handshake(self, client : socket.socket):
        # don't know how this would create an exception but its here just to be safe

        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            ip, _ = client.getpeername()
            print(f"{current_time} {self.request.method} {self.request.base_url} {ip}")
            return True
        except:
            return False
    
    async def handle(self, client : socket.socket, slugs, endpoints):

        self.request.slugs = slugs

        if self.request.method in endpoints:
            response : Response | StreamedResponse = await endpoints[self.request.method](self.request)

            ip, _ = client.getpeername()

            if isinstance(response, StreamedResponse):
                client.sendall(response.get_head())

                current_time = datetime.now().strftime("%H:%M:%S")

                print(f"{current_time} {response.status_code.value} STREAM -> {ip}")

                async for packet in response.stream(self.request):
                    chunk_len = f"{len(packet):X}\r\n".encode('utf-8')
                    client.sendall(chunk_len + packet + b"\r\n")

                    current_time = datetime.now().strftime("%H:%M:%S")
                    

                client.sendall(b"0\r\n\r\n")

                print(f"{current_time} {response.status_code.value} STREAM FINISHED -> {ip}")


            else:
                client.sendall(response.to_bytes())
            
                current_time = datetime.now().strftime("%H:%M:%S")

                print(f"{current_time} {response.status_code.value} -> {ip}")
        else:
            raise FileNotFoundError()
