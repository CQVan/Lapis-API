from abc import ABC, abstractmethod
from dataclasses import dataclass
import socket

@dataclass
class ServerConfig:
    dir : str = "./api"
    max_request_size : int = 4096
    server_name : str = "Server"
    path_script_name : str = "path"
    

# region Exceptions

class BadRequest(Exception):
    pass

class BadAPIDirectory(Exception):
    pass

# endregion

class Protocol(ABC):
    """
    An abstract class used for the server to be able to handle different protocals (ex: HTTP/1.1)
    """

    @classmethod
    @abstractmethod
    def get_target_endpoints() -> list[str]:
        '''
        :return: A list of all possible target function names of the protocol
        :rtype: list[str]
        '''
        pass

    @abstractmethod
    def identify(self, initial_data: bytes) -> bool:
        """
        Function called so see if initial request is attempting to upgrade to the given protocol
        
        :param initial_data: The initial request from the client
        :type initial_data: bytes
        :return: If the initial request is for the given protocol
        :rtype: bool
        """
        pass

    @abstractmethod
    def handshake(self, client : socket.socket) -> bool:
        '''
        Handles the transfering logic between the initial protocol (HTTP/1.1) to the new protocol
        
        :param client: The socket connecting the server to the client
        :type client: socket.socket
        :return: If the handshake was successful
        :rtype: bool
        '''
        pass

    @abstractmethod
    def handle(self, client : socket.socket, slugs: dict[str, str], endpoints: dict):
        '''
        Handles the protocol logic and server to client communication
        
        :param client: The socket connecting the server to the client
        :type client: socket.socket
        :param slugs: Any slugs in the url used to reach the endpoints
        :type slugs: dict[str, str]
        :param endpoints: All endpoints of a given url
        :type endpoints: dict
        '''
        pass