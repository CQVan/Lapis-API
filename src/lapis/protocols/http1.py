
import asyncio
from datetime import datetime
from http import HTTPMethod, HTTPStatus
import socket
from urllib.parse import parse_qsl, urlparse

from lapis.server_types import BadRequest, Protocol

class Response:
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

    def set_cookie(self, key, value):
        self.cookies[key] = value

    def add_header(self, key, value):
        self.headers[key] = value

    def to_bytes(self):
        body_bytes = self.body.encode('utf-8')
        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = len(body_bytes)

        response_line = f"{self.protocol} {self.status_code.value} {self.reason_phrase}\r\n"
        headers = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
        cookies = "".join(f"Set-Cookie: {k}={v}\r\n" for k, v in self.cookies.items())

        return (response_line + headers + cookies + "\r\n").encode('utf-8') + body_bytes

class Request:
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
        except ValueError:
            raise BadRequest("Bad URL")
        
        self.base_url = parsed.path
        self.query_params = dict(parse_qsl(parsed.query))
        self.body = body

class HTTP1Protocol(Protocol):

    request : Request = None

    def get_target_endpoints(self) -> list[str]:
        return [method.name for method in HTTPMethod]

    def identify(self, initial_data):
        try: 
            self.request = Request(initial_data)
            return True
        except BadRequest:
            return False
    
    def handshake(self, client : socket.socket):
        current_time = datetime.now().strftime("%H:%M:%S")
        ip, _ = client.getpeername()
        print(f"{current_time} {self.request.method} {self.request.base_url} {ip}")
        return True
    
    def handle(self, client : socket.socket, slugs, endpoints):
        self.request.slugs = slugs
        if f"/{self.request.method}" in endpoints:
            response : Response = asyncio.run(endpoints[f"/{self.request.method}"](self.request))
            client.sendall(response.to_bytes())
            
            current_time = datetime.now().strftime("%H:%M:%S")
            peer = client.getpeername()
            ip = peer[0]

            print(f"{current_time} {response.status_code.value} -> {ip}")
        else:
            raise FileNotFoundError()

    pass