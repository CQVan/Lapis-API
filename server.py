import select
import socket
import runpy
from datetime import datetime

from server_types import ServerConfig, Request

class Server:

    s: socket.socket = None

    cfg : ServerConfig = ServerConfig()

    def __init__(self, config : ServerConfig | None = None):
        if config is not None:
            self.cfg = config
        pass

    def run(self, ip: str, port: int):
        self.s = socket.socket()
        
        self.s.bind((ip, port))

        self.s.listen()
        print(f"Server is now listening on http://{ip}:{port}")
        try:
            while True:
                readable, _, _ = select.select([self.s], [], [], 0.1)
                if self.s in readable:

                    client, (return_ip, _) = self.s.accept()
                    data = client.recv(self.cfg.max_payload)

                    current_datetime = datetime.now()
                    current_time = current_datetime.strftime("%H:%M:%S")

                    request : Request = Request(data=data)

                    print(f"{current_time} {request.method} {request.base_url} {return_ip}")

        except KeyboardInterrupt:
            pass
        finally:
            self.__close()

    def __close(self):
        if self.s is not None:
            try:
                print("Closing Server...")
                self.s.close()
            except Exception as e:
                print(f"Error when closing socket: {e}")



server = Server()

server.run("localhost", 80)