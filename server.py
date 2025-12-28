from http import HTTPMethod
import select
import socket
import asyncio
import pathlib
import inspect
import runpy
from threading import Thread
from datetime import datetime
from server_types import BadRequest, ServerConfig, Request, Response

class Server:
    s: socket.socket = None
    cfg: ServerConfig = ServerConfig()

    paths: dict = {}

    def __init__(self, config: ServerConfig | None = None):
        if config is not None:
            self.cfg = config

        print("Baking Paths...")
        self.paths = self._bake_paths()
        print(self.paths)

    def run(self, ip: str, port: int):
        self.s = socket.socket()
        self.s.bind((ip, port))
        self.s.listen()
        print(f"Server is now listening on http://{ip}:{port}")

        try:
            while True:
                readable, _, _ = select.select([self.s], [], [], 0.1)
                if self.s in readable:
                    client, _ = self.s.accept()
                    t = Thread(target=self._handle_request, args=(client,), daemon=True)
                    t.start()
        except KeyboardInterrupt:
            pass
        finally:
            self.__close()


    def _bake_paths(self) -> dict:
        # 1. Setup root and script target
        root = pathlib.Path(self.cfg.dir)
        script_file_name = f"{self.cfg.path_script_name}.py"
        result = {}

        # 2. Recursively find all target files (e.g., path.py)
        for path in root.rglob(script_file_name):
            if not path.is_file():
                continue

            # 3. Build/Navigate the nested dictionary based on folder structure
            parts = path.relative_to(root).parts
            current_level = result
            
            # We iterate through parts[:-1] to navigate folders, not the file itself
            for part in parts[:-1]:
                current_level = current_level.setdefault(part, {})

            script_globals = runpy.run_path(str(path.absolute()))

            # Grab just endpoint methods
            api_routes = {
                f"/{k}": v 
                for k, v in script_globals.items() 
                if k in HTTPMethod
            }

            # Add endpoints
            current_level.update(api_routes)

        return result

    def _handle_request(self, client: socket.socket):
        try:
            data = client.recv(self.cfg.max_request_size)
            current_time = datetime.now().strftime("%H:%M:%S")

            try:
                request = Request(data=data)
            except BadRequest:
                self.__send_response(client, Response(400, "Bad Request"))
                return

            ip, _ = client.getpeername()
            print(f"{current_time} {request.method} {request.base_url} {ip}")

            try:

                path = pathlib.Path(f"{self.cfg.dir}{request.base_url}")
                parts = path.relative_to(self.cfg.dir).parts
                
                leaf = None
                for part in parts:
                    leaf = self.paths[part]

                if f"/{request.method}" in leaf:
                    response : Response = asyncio.run(leaf[f"/{request.method}"](request))
                    self.__send_response(client, response)

                # TODO: Add slugs
                else:
                    raise FileNotFoundError()

                pass

            except FileNotFoundError:
                response : Response = Response(status_code=404, body="404 Not Found")
                self.__send_response(client, response)
                pass

            except Exception as e:
                print(f"Error handling request: {e}")
                response = Response(status_code=500, body="Internal Server Error")
                self.__send_response(client, response)

        except Exception as e:
            print(f"Error handling client: {e}")
            self.__send_response(client, Response(status_code=404, body="404 Not Found"))
            
        finally:
            client.close()

    def __send_response(self, client : socket.socket, response : Response):
        client.sendall(response.to_bytes())
        current_time = datetime.now().strftime("%H:%M:%S")
        ip, _ = client.getpeername()
        print(f"{current_time} {response.status_code.value} -> {ip}")

    def __close(self):
        if self.s is not None:
            try:
                print("Closing Server...")
                self.s.close()
            except Exception as e:
                print(f"Error when closing socket: {e}")

if __name__ == "__main__":
    server = Server()
    server.run("localhost", 80)
