#!/usr/bin/env python3

import http.server
import json
import logging
import typing
import os
import sys
import random
import string
import traceback
import socketserver

if __name__ == "__main__":
    try:
        import fn  # type: ignore
    except ImportError:
        raise ImportError("Failed to import fn.py")

    # first argument: function name
    try:
        function_name = sys.argv[1]
    except IndexError:
        raise ValueError("Missing function name")

    if function_name == "":
        raise ValueError("Empty function name")

    # create a webserver at port 8080 and execute fn.fn for every request
    class tfaasFNHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            print(f"GET {self.path}")
            if self.path == "/health":
                logging.info("reporting health: OK")
                self.send_response(200)
                self.end_headers()
                self.wfile.write("OK".encode("utf-8"))
                return

            logging.error(f"Invalid path for GET: {self.path}")
            self.send_response(404)
            self.end_headers()
            return

        def do_POST(self) -> None:
            d: typing.Optional[str] = self.rfile.read(
                int(self.headers["Content-Length"])
            ).decode("utf-8")
            if d == "":
                logging.error("Empty body")
                self.send_response(400)
                self.end_headers()
                self.wfile.write("Empty body".encode("utf-8"))
                return

            # try parsing the input as json
            try:
                i = json.loads(d)
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse json: {e}")
                self.send_response(400)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
                return

            try:
                tmp_file = os.path.join(
                    i["out_path"],
                    "".join(random.choices(string.ascii_letters, k=7)) + ".tmp",
                )

                with open(tmp_file, "xb") as f:
                    fn.fn(
                        lat=i["lat"],
                        lon=i["lon"],
                        alt=i["alt"],
                        clouds=i["clouds"],
                        sunlit=i["sunlit"],
                        in_path=i["in_path"],
                        out_writer=f,
                    )

                result_file = os.path.join(
                    i["out_path"],
                    f"{function_name}-{os.path.basename(i['in_path'])}",
                )

                os.rename(tmp_file, result_file)

                logging.info("fn executed successfully")
                self.send_response(200)
                self.end_headers()
                self.wfile.write("OK".encode("utf-8"))
                return
            except Exception as e:
                logging.error(f"Failed to execute fn: {e}")
                logging.error(traceback.format_exc())
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
                return

    # with socketserver.ThreadingTCPServer(("", 8000), tfaasFNHandler) as httpd:
    with socketserver.TCPServer(("", 8000), tfaasFNHandler) as httpd:
        httpd.serve_forever()
