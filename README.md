# xterm-js-shell
Start a direct web Bash shell using Xterm.js - no SSH connection required. This is a single-user shell that runs with the privileges of the process that started it, and it can handle multiple simultaneous connections.

The project is based on "asyncio" and supports authentication, detailed logging, and graceful shell termination.

The graceful termination feature allows you to run the web shell server in a "socket activation" mode. You can start the server on demand and terminate it when there are no active connections for a while. A typical use case is to launch the web shell server as part of the initial authentication process.

The [asyncio web server](https://websockets.readthedocs.io/en/stable/reference/asyncio/server.html#creating-a-server) can bind to either a TCP port or a UNIX socket. The latter is particularly useful when starting a web shell server on demand for each user. You can create a unique UNIX socket filename for each user's server in a secure path. WebSocket HTTP requests can then be proxied to the appropriate UNIX socket using a user-friendly URL format such as "wss://example.com/xterm-js-shell/user1".

Example authentication process:
- The user opens the web "index.html" page for the first time.
- The "index.html" page is either dynamically generated or makes a fetch() request to an authentication system.
- The authentication system generates a JWT token. Up to this point, the web shell server is not involved, yet.
- The web "index.html" page then connects to the web shell server and provides the JWT token.
- The JWT token is validated by the implementation of auth_callback().

This project has not been tested at scale but has passed a ChatGPT code audit and is expected to be fully functional.
