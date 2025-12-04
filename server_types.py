from dataclasses import dataclass
from urllib.parse import urlparse, parse_qsl
from http import HTTPMethod, HTTPStatus

@dataclass
class ServerConfig:
    dir : str = "./api/"
    max_request_size : int = 4096
    server_name : str = "Server"

class Response:
    def __init__(self, 
                 status_code : int | HTTPStatus = HTTPStatus.OK, 
                 protocol : str = 'HTTP/1.1', 
                 headers : dict[str, any] = None, 
                 cookies : dict[str, any] = None, 
                 body : str = ""):
        self.status_code = status_code if isinstance(status_code, HTTPStatus) else HTTPStatus(status_code)
        self.protocol = protocol
        self.headers = headers if headers is not None else {}
        self.cookies = cookies if cookies is not None else {}
        self.body = body

    @property
    def reason_phrase(self):
        return self.status_code.phrase

    def set_cookie(self, key, value):
        self.cookies[key] = value

    def add_header(self, key, value):
        self.headers[key] = value

    def to_bytes(self):
        response_line = f"{self.protocol} {self.status_code.value} {self.reason_phrase}\r\n"
        headers = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
        cookies = "".join(f"Set-Cookie: {k}={v}\r\n" for k, v in self.cookies.items())
        return (response_line + headers + cookies + "\r\n" + self.body).encode('utf-8')



class Request:
    method : HTTPMethod
    headers : dict[str, any] = {}
    base_url : str
    protocol : str

    body : str
    cookies : dict[str, any] = {}

    query_params : dict[str, any] = {}

    def __init__(self, data : bytes):
        head, self.body = data.decode().split('\r\n\r\n', 1)

        headers = head.splitlines()
        request_line = headers.pop(0)
        method, url, self.protocol = request_line.split(' ', 3)
        self.method = HTTPMethod[method.upper()]

        for header in headers:
            key, value = header.split(':', 1)

            if key == "Cookie":
                cookies = value.split(';')
                for cookie in cookies:
                    ckey, cvalue = cookie.split('=')
                    self.cookies[ckey.strip()] = cvalue.strip()

            else:
                self.headers[key] = value.strip()

        parsed = urlparse(url)
        self.base_url = parsed.path
        self.query_params = dict(parse_qsl(parsed.query))
        pass