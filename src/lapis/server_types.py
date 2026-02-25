"""
Module containing all server related types and exceptions
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import socket
import json
import sys
from typing import get_origin, get_type_hints
import pathlib


@dataclass
class ServerConfig:
    """
    The class containing all configuration settings for a Lapis server to operate with
    """

    api_directory: str = "./api"
    max_request_size: int = 4096
    server_name: str = "Server"
    path_script_name: str = "path"

    protocol_configs: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_json(cls, file_path: str | pathlib.Path) -> "ServerConfig":
        """
        Generates a ServerConfig object from the json file found at the file path

        :param file_path: The file path of the json server config
        :type file_path: str
        :return: The resulting ServerConfig object generated from the json file
        :rtype: ServerConfig
        """

        base_dir = pathlib.Path(sys.argv[0]).parent.resolve()
        path = (base_dir / file_path).resolve()

        config: ServerConfig = ServerConfig()

        with open(path, "r", encoding="utf-8") as file:
            # Read and parse the JSON content from the file
            data = json.load(file)

            hints = get_type_hints(config.__class__)

            for key, expected_type in hints.items():
                if key not in data:
                    continue

                value = data[key]

                if not cls._check_type(value, expected_type):
                    raise BadConfigError(
                        f'"{key}" must be of type {expected_type.__name__}'
                    )

                setattr(config, key, value)

        return config

    @classmethod
    def _check_type(cls, value, expected_type) -> bool:
        """
        Returns if a value is an instance of a type while accounting for generics
        """
        origin = get_origin(expected_type)

        if origin is None:
            return isinstance(value, expected_type)

        if origin is dict:
            return isinstance(value, dict)

        if origin is list:
            return isinstance(value, list)

        return isinstance(value, origin)


# region Exceptions


class BadRequest(Exception):
    """
    An Exception raised when a client request is not formatted correctly
    """


class BadAPIDirectory(Exception):
    """
    An Exception raised when the format of the directory containing all endpoints is incorrect
    """


class BadConfigError(Exception):
    """
    An Exception raised when the format or typing of a Config is given
    """


class ProtocolEndpointError(Exception):
    """
    The exception raised when there is an error with protocol target endpoint functions
    """


# endregion


class Protocol(ABC):
    """
    An abstract class used for the server to be able to handle different protocals (ex: HTTP/1.1)
    """

    @abstractmethod
    def __init__(self, config: dict[str, any]):
        pass

    @classmethod
    def get_config_key(cls) -> str:
        """
        Gathers the keyword used to get the protocol's config from ServerConfig.protocol_configs

        :return: Description
        :rtype: str
        """

        return cls.__module__

    @abstractmethod
    def get_target_endpoints(self) -> list[str]:
        """
        :return: A list of all possible target function names of the protocol
        :rtype: list[str]
        """

        raise NotImplementedError

    @abstractmethod
    def identify(self, initial_data: bytes) -> bool:
        """
        Function called so see if initial request is attempting to upgrade to the given protocol

        :param initial_data: The initial request from the client
        :type initial_data: bytes
        :return: If the initial request is for the given protocol
        :rtype: bool
        """

        raise NotImplementedError

    @abstractmethod
    def handshake(self, client: socket.socket) -> bool:
        """
        Handles the transfering logic between the initial protocol (HTTP/1.1) to the new protocol

        :param client: The socket connecting the server to the client
        :type client: socket.socket
        :return: If the handshake was successful
        :rtype: bool
        """

        raise NotImplementedError

    @abstractmethod
    async def handle(
        self, client: socket.socket, slugs: dict[str, str], endpoints: dict[str, any]
    ):
        """
        Handles the protocol logic and server to client communication

        :param client: The socket connecting the server to the client
        :type client: socket.socket
        :param slugs: Any slugs in the url used to reach the endpoints
        :type slugs: dict[str, str]
        :param endpoints: All endpoints of a given url
        :type endpoints: dict[str, any]
        """

        raise NotImplementedError
