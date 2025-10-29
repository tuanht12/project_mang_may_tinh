"""
Test sau khi thiết lập môi trường.
Kiểm tra xem tất cả các module cần thiết có thể được nhập thành công hay không.
In ra "Hello, World!" nếu tất cả các module được nhập thành công.
"""

import socket
import threading
import time
import pandas as pd
import numpy as np
import sys


def assert_python_version():
    """Đảm bảo phiên bản Python là 3.9 hoặc cao hơn."""
    version_python = sys.version_info
    if version_python.major != 3 or version_python.minor < 9:
        raise EnvironmentError(
            f"Python 3.9 or higher is required, but you have {version_python.major}.{version_python.minor}."
        )


if __name__ == "__main__":
    assert_python_version()
    print("Hello, World!")
    print("All modules imported successfully.")
