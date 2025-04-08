#!/usr/bin/env python3

import typing
import json


def fn(i: typing.Optional[str]) -> typing.Optional[str]:
    if i is None:
        return None

    # i is a json string:
    # { "path": "/path/to/file", "expected_content": "XXXX", "write": false }

    # parse the json string
    j = json.loads(i)

    # read the file
    with open(j["path"], "r") as f:
        content = f.read()

    if content != j["expected_content"]:
        raise Exception(f"expected content: {j['expected_content']}, got: {content}")

    if j["write"]:
        # write to the file
        try:
            with open(j["path"], "w") as f:
                f.write("hellofromfunction")
        except Exception as e:
            raise Exception(f"failed to write to the file: {e}")

    return content
