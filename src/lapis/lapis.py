"""
Docstring for lapis.lapis

The main script for the Lapis server handling initial request handling and response
"""

import select
import socket
import pathlib
import runpy
import sys
from threading import Thread
from datetime import datetime

from lapis.protocals.http1 import HTTP1Protocal, Request, Response
from .server_types import BadRequest, Protocol, ServerConfig
from http import HTTPMethod

class Lapis:

    cfg: ServerConfig = ServerConfig()

    __s: socket.socket = None
    __paths: dict = {}
    __taken_endpoints : list[str] = []
    __protocals : list[type[Protocol]] = []

    def __init__(self, config: ServerConfig | None = None):

        if config is not None:
            self.cfg = config

        self.__paths = self._bake_paths()
        self.register_protocal(HTTP1Protocal)

    def run(self, ip: str, port: int):
        self.__s = socket.socket()
        self.__s.bind((ip, port))
        self.__s.listen()
        print(f"Server is now listening on http://{ip}:{port}")

        try:
            while True:
                readable, _, _ = select.select([self.__s], [], [], 0.1)
                if self.__s in readable:
                    client, _ = self.__s.accept()
                    t = Thread(target=self._handle_request, args=(client,), daemon=True)
                    t.start()
        except KeyboardInterrupt:
            pass
        finally:
            self.__close()

    def register_protocal(self, protocal : type[Protocol]):
        endpoints : list[str] = protocal.get_target_endpoints()
        if bool(set(endpoints) & set(self.__taken_endpoints)):
            raise Exception("Cannot reuse target endpoint method!")

        self.__protocals.insert(0, protocal)
        self.__taken_endpoints.extend(endpoints)
        pass

    def _get_dynamic_dirs(self, directory: pathlib.Path):
        return [
            p for p in directory.iterdir()
            if p.is_dir() and p.name.startswith("[") and p.name.endswith("]")
        ]

    def _bake_paths(self) -> dict:

        server_path = pathlib.Path(sys.argv[0]).resolve()
        root : pathlib.Path = server_path.parent / pathlib.Path(self.cfg.dir)
        script_file_name = f"{self.cfg.path_script_name}.py"
        result = {}

        for path in root.rglob(script_file_name):
            if not path.is_file():
                continue

            parts = path.relative_to(root).parts
            current_level = result
            current_fs_level = root
            
            for part in parts[:-1]:
                dynamic_dirs = self._get_dynamic_dirs(current_fs_level)
                if len(dynamic_dirs) > 1:
                    raise RuntimeError(
                        f"Multiple dynamic route folders in {current_fs_level}: "
                        f"{', '.join(d.name for d in dynamic_dirs)}"
                    )

                # move filesystem pointer
                current_fs_level = current_fs_level / part

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
            request : Request = Request(data)

            try:
                path = pathlib.Path(f"{self.cfg.dir}{request.base_url}")
                parts : list[str] = path.relative_to(self.cfg.dir).parts
                
                leaf : dict = self.__paths
                for part in parts:
                    if part in leaf:
                        leaf = leaf[part]
                    else:
                        dynamic_routes: list[str] = list(
                            {
                                key
                                for key in leaf
                                if key.startswith("[") and key.endswith("]")
                            }
                        )

                        if len(dynamic_routes) == 1:
                            request.slugs[dynamic_routes[0].strip("[]")] = part
                            leaf = leaf[dynamic_routes[0]]
                        else:
                            raise FileNotFoundError()

                if len(leaf) == 0:
                    raise FileExistsError()
                
                found_protocol : bool = False
                
                for p in self.__protocals:
                    protocal : Protocol = p()

                    if protocal.identify(initial_data=data):
                        found_protocol = True
                        if protocal.handshake(client=client):

                            target_endpoints = p.get_target_endpoints()

                            endpoints = {
                                f"/{k}": leaf[f"/{k}"]
                                for k in target_endpoints
                                if f"/{k}" in leaf
                            }

                            protocal.handle(client=client, slugs=request.slugs, endpoints=endpoints)
                            break
                        else: 
                            break
                    pass
                
                if not found_protocol:
                    raise BadRequest()
            
            except BadRequest as e:
                response : Response = Response(status_code=400, body="400 Bad Request")
                self.__send_response(client=client, response=response)

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
        peer = client.getpeername()
        ip = peer[0]
        print(f"{current_time} {response.status_code.value} -> {ip}")

    def __close(self):
        if self.s is not None:
            try:
                print("Closing Server...")
                self.s.close()
            except Exception as e:
                print(f"Error when closing socket: {e}")
