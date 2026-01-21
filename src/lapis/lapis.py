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

from lapis.protocols.http1 import HTTP1Protocol, Request, Response
from .server_types import BadAPIDirectory, BadRequest, Protocol, ServerConfig

class Lapis:
    """
    The Lapis class implements the centeral object used to run a Lapis REST server
    """
    cfg: ServerConfig = ServerConfig()

    __s: socket.socket = None
    __paths: dict = {}
    __taken_endpoints : list[str] = []
    __protocols : list[type[Protocol]] = []

    __running : bool = False

    def __init__(self, config: ServerConfig | None = None):

        if config is not None:
            self.cfg = config

        self.__register_protocol(HTTP1Protocol)

        self.__paths = self._bake_paths()

    def run(self, ip: str, port: int):
        """
        Starts the Lapis server to listen on a given ip and port
        
        :param ip: The ip for the server to listen on
        :type ip: str
        :param port: The port for the server to listen on
        :type port: int
        """
        self.__s = socket.socket()
        self.__s.bind((ip, port))
        self.__s.listen()
        
        self.__running = True
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

    def __register_protocol(self, protocol):

        if self.__running:
            raise RuntimeError("Cannot register new Protocol while server is running")

        endpoints : list[str] = protocol.get_target_endpoints()
        if bool(set(endpoints) & set(self.__taken_endpoints)):
            raise Exception("Cannot reuse target endpoint method!")

        self.__protocols.insert(0, protocol)
        self.__taken_endpoints.extend(endpoints)

    def register_protocol(self, protocol : type[Protocol]):
        """
        Registers new protocol for the server to use to communicate with clients

        Cannot be called while server is running

        :param protocol: Description
        :type protocol: type[Protocol]
        """
        self.__register_protocol(protocol=protocol)

        self.__paths = self._bake_paths()

        pass

    def _get_dynamic_dirs(self, directory: pathlib.Path):
        return [
            p for p in directory.iterdir()
            if p.is_dir() and p.name.startswith("[") and p.name.endswith("]")
        ]

    def _bake_paths(self) -> dict:

        server_path = pathlib.Path(sys.argv[0]).resolve()
        root : pathlib.Path = server_path.parent / pathlib.Path(self.cfg.dir)

        if not root.exists():
            raise BadAPIDirectory("Missing api directory")

        result = {}

        for path in root.rglob(f"{self.cfg.path_script_name}.py"):
            if not path.is_file():
                continue

            parts = path.relative_to(root).parts
            current_level = result
            current_fs_level = root
            
            for part in parts[:-1]:
                dynamic_dirs = self._get_dynamic_dirs(current_fs_level)
                if len(dynamic_dirs) > 1:
                    raise BadAPIDirectory(
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
                if k in self.__taken_endpoints
            }

            # Add endpoints
            current_level.update(api_routes)

        return result

    def _handle_request(self, client: socket.socket):
        try:
            data = client.recv(self.cfg.max_request_size)
            request : Request = Request(data)

        except Exception as e:
            print(f"Error handling client: {e}")
            self.__send_response(client, Response(status_code=400, body="400 Bad Request"))
            client.close()
            return

        try:
            path = pathlib.Path(f"{self.cfg.dir}{request.base_url}")
            parts : list[str] = path.relative_to(self.cfg.dir).parts
            
            leaf : dict = self.__paths
            for part in parts:
                if part in leaf:
                    leaf = leaf[part]
                    continue
                
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
            
            for ProtocolCls in self.__protocols:
                protocol: Protocol = ProtocolCls()

                if not protocol.identify(initial_data=data):
                    continue

                if not protocol.handshake(client=client):
                    break

                target_endpoints = ProtocolCls.get_target_endpoints()

                endpoints = { 
                    f"/{k}": leaf[f"/{k}"] 
                    for k in target_endpoints 
                    if f"/{k}" in leaf 
                }

                protocol.handle(
                    client=client,
                    slugs=request.slugs,
                    endpoints=endpoints,
                )
                break
            else:
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

        finally:
            client.close()

    def __send_response(self, client : socket.socket, response : Response):
        client.sendall(response.to_bytes())
        current_time = datetime.now().strftime("%H:%M:%S")
        ip, _ = client.getpeername()
        print(f"{current_time} {response.status_code.value} -> {ip}")

    def __close(self):
        if self.__s is not None:
            try:
                print("Closing Server...")
                self.__running = False
                self.__s.close()
            except Exception as e:
                print(f"Error when closing socket: {e}")
