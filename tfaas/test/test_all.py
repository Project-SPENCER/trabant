#!/usr/bin/env python3

import unittest

import json
import os
import os.path as path
import signal
import subprocess
import sys
import time
import typing
import urllib.error
import urllib.request

# if the debug flag is set, no cleanup will be done
DEBUG = False

connection: typing.Dict[str, typing.Union[str, int]] = {
    "host": "localhost",
    "management_port": 8080,
    "http_port": 8000,
}

tf_process: typing.Optional[subprocess.Popen] = None  # type: ignore
src_path = "."
fn_path = path.join(src_path, "test", "fns")
script_path = path.join(src_path, "scripts")


def setUpModule() -> None:
    """start tfaas instance"""
    # call make clean
    try:
        subprocess.run(["make", "clean"], cwd=src_path, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to clean up:\n{e.stderr.decode('utf-8')}")

    # start tfaas
    try:
        env = os.environ.copy()
        env["HTTP_PORT"] = str(connection["http_port"])

        global tf_process

        # find architecture and operating system
        uname = os.uname()
        if uname.machine == "x86_64":
            arch = "amd64"
        elif uname.machine == "arm64":
            arch = "arm64"
        else:
            raise Exception(f"Unsupported architecture: {uname.machine}")

        if uname.sysname == "Linux":
            os_name = "linux"
        elif uname.sysname == "Darwin":
            os_name = "darwin"
        else:
            raise Exception(f"Unsupported operating system: {uname.sysname}")

        tf_binary = path.join(src_path, f"tf-{os_name}-{arch}")

        # os.makedirs(path.join(src_path, "tmp"), exist_ok=True)
        with open(path.join(".", "tf_test.out"), "w") as f:
            tf_process = subprocess.Popen(
                [tf_binary],
                cwd=src_path,
                env=env,
                stdout=f,
                stderr=f,
            )

    except subprocess.CalledProcessError as e:
        print(f"Failed to start:\n{e.stderr.decode('utf-8')}")

    # wait for tfaas to start
    while True:
        try:
            urllib.request.urlopen(
                f"http://{connection['host']}:{connection['management_port']}/"
            )
            break
        except urllib.error.HTTPError:
            break
        except Exception:
            continue
    # wait for tfaas to start
    while True:
        try:
            urllib.request.urlopen(
                f"http://{connection['host']}:{connection['http_port']}/"
            )
            break
        except urllib.error.HTTPError:
            break
        except Exception:
            continue

    return


def tearDownModule() -> None:
    """stop tfaas instance"""

    # call wipe-functions.sh
    try:
        if DEBUG:
            print("Skipping wipe-functions.sh")
        else:
            subprocess.run(
                ["./wipe-functions.sh"],
                cwd=script_path,
                check=True,
                capture_output=True,
            )
    except subprocess.CalledProcessError as e:
        print(f"Failed to wipe functions:\n{e.stderr.decode('utf-8')}")

    try:
        tf_process.send_signal(signal.SIGINT)  # type: ignore
        tf_process.wait(timeout=1)  # type: ignore
        tf_process.terminate()  # type: ignore
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop:\n{e.stderr.decode('utf-8')}")
    except subprocess.TimeoutExpired:
        print("Failed to stop: Timeout expired")

    # call make clean
    try:
        if DEBUG:
            print("Skipping make clean")
        else:
            subprocess.run(
                ["make", "clean"], cwd=src_path, check=True, capture_output=True
            )
    except subprocess.CalledProcessError as e:
        print(f"Failed to clean up:\n{e.stderr.decode('utf-8')}")

    return


def startFunction(
    folder_name: str,
    fn_name: str,
    env: str,
    threads: int,
    mount_dirs: typing.List[typing.Tuple[str, str, bool]] = [],
) -> str:
    """starts a function, returns name"""

    # get full path of folder
    folder_name = os.path.abspath(folder_name)

    # use the upload.sh script
    try:
        subprocess.run(
            [
                "./upload-with-mount.sh",
                folder_name,
                fn_name,
                env,
                str(threads),
                ",".join(
                    [
                        f"{path}:{target}:{'rw' if mode else 'ro'}"
                        for path, target, mode in mount_dirs
                    ]
                ),
            ],
            cwd=script_path,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(
            f"Failed to upload function {fn_name}:\n{e.stdout.decode('utf-8')}\n{e.stderr.decode('utf-8')}"
        )
        raise e

    return fn_name


class tfaasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super(tfaasTest, cls).setUpClass()

    def setUp(self) -> None:
        global connection
        self.host = connection["host"]
        self.http_port = connection["http_port"]


class TestEcho(tfaasTest):
    fn = ""

    @classmethod
    def setUpClass(cls) -> None:
        super(TestEcho, cls).setUpClass()
        cls.fn = startFunction(path.join(fn_path, "echo"), "echo", "python3", 1)

    def setUp(self) -> None:
        super(TestEcho, self).setUp()
        self.fn = TestEcho.fn

    def test_invoke_http(self) -> None:
        """invoke a function"""

        # make a request to the function with a payload
        payload = "Hello World!"

        req = urllib.request.Request(
            f"http://{self.host}:{self.http_port}/{self.fn}",
            data=payload.encode("utf-8"),
        )

        res = urllib.request.urlopen(req, timeout=10)

        # check the response
        self.assertEqual(res.status, 200)
        self.assertEqual(res.read().decode("utf-8"), payload)

        return


class TestAsync(tfaasTest):
    fn = ""
    rw_dir = ""

    @classmethod
    def setUpClass(cls) -> None:
        super(TestAsync, cls).setUpClass()

        # create a temporary directory
        cls.rw_dir = (
            subprocess.run(["mktemp", "-d"], check=True, capture_output=True)
            .stdout.decode("utf-8")
            .strip()
        )

        cls.fn = startFunction(
            path.join(fn_path, "readfile"),
            "readfile",
            "python3",
            1,
            [(cls.rw_dir, "rw_dir", True)],
        )

    def setUp(self) -> None:
        super(TestAsync, self).setUp()
        self.fn = TestAsync.fn

    def test_invoke_async(self) -> None:
        """invoke a function"""

        # create a file in that directory
        tmp_file = "test.txt"
        payload = "hello async!"

        with open(path.join(self.rw_dir, tmp_file), "w") as f:
            f.write(payload)

        # make a request to the function with a payload
        req = urllib.request.Request(
            f"http://{self.host}:{self.http_port}/{self.fn}",
            data=json.dumps(
                {
                    "path": f"/files/rw_dir/{tmp_file}",
                    "expected_content": payload,
                    "write": True,
                }
            ).encode("utf-8"),
            headers={"X-tfaas-Async": "true"},
        )

        res = urllib.request.urlopen(req, timeout=10)

        # check the response
        self.assertEqual(res.status, 202)
        time.sleep(5)
        with open(path.join(self.rw_dir, tmp_file), "r") as f:
            self.assertEqual(f.read(), "hellofromfunction")

        return


class TestBinary(tfaasTest):
    fn = ""

    @classmethod
    def setUpClass(cls) -> None:
        super(TestBinary, cls).setUpClass()
        cls.fn = startFunction(
            path.join(fn_path, "echo-binary"), "echobinary", "binary", 1
        )

    def setUp(self) -> None:
        super(TestBinary, self).setUp()
        self.fn = TestBinary.fn

    def test_invoke_http(self) -> None:
        """invoke a function"""

        # make a request to the function with a payload
        payload = "Hello World!"

        req = urllib.request.Request(
            f"http://{self.host}:{self.http_port}/{self.fn}",
            data=payload.encode("utf-8"),
        )

        res = urllib.request.urlopen(req, timeout=10)

        # check the response
        self.assertEqual(res.status, 200)
        self.assertEqual(res.read().decode("utf-8"), payload)

        return


class TestMicropython(tfaasTest):
    fn = ""

    @classmethod
    def setUpClass(cls) -> None:
        super(TestMicropython, cls).setUpClass()
        cls.fn = startFunction(
            path.join(fn_path, "echo-micro"), "echomicro", "micropython", 1
        )

    def setUp(self) -> None:
        super(TestMicropython, self).setUp()
        self.fn = TestMicropython.fn

    def test_invoke_http(self) -> None:
        """invoke a function"""

        # make a request to the function with a payload
        payload = "Hello World!"

        req = urllib.request.Request(
            f"http://{self.host}:{self.http_port}/{self.fn}",
            data=payload.encode("utf-8"),
        )

        res = urllib.request.urlopen(req, timeout=10)

        # check the response
        self.assertEqual(res.status, 200)
        self.assertEqual(res.read().decode("utf-8"), payload)

        return


class TestFile(tfaasTest):
    fn = ""
    ro_dir = ""
    rw_dir = ""

    @classmethod
    def setUpClass(cls) -> None:
        super(TestFile, cls).setUpClass()

        # create a temporary directory
        cls.ro_dir = (
            subprocess.run(["mktemp", "-d"], check=True, capture_output=True)
            .stdout.decode("utf-8")
            .strip()
        )

        cls.rw_dir = (
            subprocess.run(["mktemp", "-d"], check=True, capture_output=True)
            .stdout.decode("utf-8")
            .strip()
        )

        cls.fn = startFunction(
            path.join(fn_path, "readfile"),
            "readfile",
            "python3",
            1,
            [(cls.ro_dir, "ro_dir", False), (cls.rw_dir, "rw_dir", True)],
        )

    def setUp(self) -> None:
        super(TestFile, self).setUp()
        self.fn = TestFile.fn

    def test_readfile_http(self) -> None:
        """invoke a function"""

        # create a file in that directory
        tmp_file = "test.txt"
        payload = "Hello World!"

        with open(path.join(self.ro_dir, tmp_file), "w") as f:
            f.write(payload)

        # make a request to the function with a payload
        req = urllib.request.Request(
            f"http://{self.host}:{self.http_port}/{self.fn}",
            data=json.dumps(
                {
                    "path": f"/files/ro_dir/{tmp_file}",
                    "expected_content": payload,
                    "write": False,
                }
            ).encode("utf-8"),
        )

        res = urllib.request.urlopen(req, timeout=10)

        # check the response
        self.assertEqual(res.status, 200)
        self.assertEqual(res.read().decode("utf-8"), payload)

        return

    def test_failwritefile_http(self) -> None:
        """invoke a function"""

        # create a file in that directory
        tmp_file = "test.txt"
        payload = "Hello World!"

        with open(path.join(self.ro_dir, tmp_file), "w") as f:
            f.write(payload)

        # make a request to the function with a payload
        req = urllib.request.Request(
            f"http://{self.host}:{self.http_port}/{self.fn}",
            data=json.dumps(
                {
                    "path": f"/files/ro_dir/{tmp_file}",
                    "expected_content": payload,
                    "write": True,
                }
            ).encode("utf-8"),
        )

        res = urllib.request.urlopen(req, timeout=10)

        # check the response (should not work)
        self.assertIn("failed to write to the file", res.read().decode("utf-8"))

        return

    def test_writefile_http(self) -> None:
        """invoke a function"""

        # create a file in that directory
        tmp_file = "test.txt"
        payload = "Hello World!"

        with open(path.join(self.rw_dir, tmp_file), "w") as f:
            f.write(payload)

        # make a request to the function with a payload
        req = urllib.request.Request(
            f"http://{self.host}:{self.http_port}/{self.fn}",
            data=json.dumps(
                {
                    "path": f"/files/rw_dir/{tmp_file}",
                    "expected_content": payload,
                    "write": True,
                }
            ).encode("utf-8"),
        )

        res = urllib.request.urlopen(req, timeout=10)

        # check the response
        self.assertEqual(res.status, 200)
        self.assertEqual(res.read().decode("utf-8"), payload)
        with open(path.join(self.rw_dir, tmp_file), "r") as f:
            self.assertEqual(f.read(), "hellofromfunction")

        return


if __name__ == "__main__":
    # check that make is installed
    try:
        subprocess.run(["make", "--version"], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Make is not installed:\n{e.stderr.decode('utf-8')}")
        sys.exit(1)

    # check that Docker is working
    try:
        subprocess.run(["docker", "ps"], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Docker is not installed or not working:\n{e.stderr.decode('utf-8')}")
        sys.exit(1)

    unittest.main()  # run all tests
