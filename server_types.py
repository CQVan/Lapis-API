from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
from http import HTTPMethod

@dataclass
class ServerConfig:
    dir : str = "./api"
    max_payload : int = 4096

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
        self.query_params = parse_qs(parsed.query)
        pass