from abc import ABC, abstractmethod
from dataclasses import dataclass
import socket

@dataclass
class ServerConfig:
    dir : str = "./api"
    max_request_size : int = 4096
    server_name : str = "Server"
    path_script_name : str = "path"

class Protocol(ABC):

    @abstractmethod
    def identify(self, initial_data: bytes) -> bool:
        pass

    @abstractmethod
    def handshake(self, client : socket.socket) -> bool:
        pass

    @abstractmethod
    def handle(self, client : socket.socket, slugs: dict[str, str], endpoints: dict):
        pass