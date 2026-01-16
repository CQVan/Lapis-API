Lapis is a file-based REST API framework inspired by Vercel functions

To create a basic Lapis server, create a folder called *api* and create python script named *path.py*
then within your main folder create a python script to start the server (we will call this script *main.py* in our example)

Your project directory should look like this:

```
project-root/
|-- api/
|  |-- path.py
`-- main.py
```

Then within the *api/path.py* file create your first GET api endpoint by adding the following code:
```py
from lapis import Response, Request

async def GET (req : Request) -> Response:
    return Response(status_code=200, body="Hello World!")
```

Finally by adding the following code to *main.py* and running it:
```py
from lapis import Lapis

server = Lapis()

server.run("localhost", 80)
```

You can now send an HTTP GET request to localhost:80 and recieve the famous **Hello World!** response!
