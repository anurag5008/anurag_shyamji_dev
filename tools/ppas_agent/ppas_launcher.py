import os
import subprocess
import sys
import time
import urllib.request

AGENT_URL = "http://127.0.0.1:8765/health"


def get_launcher_folder():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(
        os.path.abspath(__file__)
    )


def get_agent_exe():
    launcher_folder = get_launcher_folder()

    exe_path = os.path.join(
        launcher_folder,
        "PPAS Agent.exe"
    )

    if os.path.exists(exe_path):
        return exe_path

    return None


def is_agent_running():
    try:
        with urllib.request.urlopen(
            AGENT_URL,
            timeout=2
        ) as response:

            return response.status == 200

    except Exception:
        return False


def start_agent():
    # Agent is already running.
    if is_agent_running():
        return True

    exe_path = get_agent_exe()

    if not exe_path:
        return False

    try:

        # Start Agent completely in the background.
        # CREATE_NO_WINDOW prevents a console window when possible.
        creation_flags = getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0x08000000
        )

        subprocess.Popen(
            [exe_path],
            creationflags=creation_flags,
            close_fds=True
        )

    except Exception:
        return False

    # Wait for Flask Agent to become ready.
    for _ in range(60):

        time.sleep(1)

        if is_agent_running():
            return True

    return False


if __name__ == "__main__":
    start_agent()
