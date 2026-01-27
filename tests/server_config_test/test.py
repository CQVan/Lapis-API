from lapis import ServerConfig, Lapis

config : ServerConfig = ServerConfig.from_json("./config.json")

server = Lapis(config=config)
server.run("localhost", 80)