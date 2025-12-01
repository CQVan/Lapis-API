from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs

@dataclass
class ServerConfig:
    dir : str = "./api"

class Request:
    method : str
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
        self.method, url, self.protocol = request_line.split(' ', 3)

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