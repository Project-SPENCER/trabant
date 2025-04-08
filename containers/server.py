#!/usr/bin/env python3

import http.server
import json
import logging
import typing
import traceback
import socketserver
import fn

if __name__ == "__main__":

    class handler(http.server.BaseHTTPRequestHandler):
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
                result_file = i["out_path"]

                with open(result_file, "xb") as f:
                    fn.fn(
                        lat=i["lat"],
                        lon=i["lon"],
                        alt=i["alt"],
                        clouds=i["clouds"],
                        sunlit=i["sunlit"],
                        in_path=i["in_path"],
                        out_writer=f,
                    )

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

    print("Starting server")
    with socketserver.TCPServer(("", 8080), handler) as httpd:
        httpd.serve_forever()
