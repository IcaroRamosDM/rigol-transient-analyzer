"""Portable cancellation and hidden Windows child processes."""
from pathlib import Path
import os
import signal

KILL = getattr(signal, "SIGKILL", signal.SIGTERM)


def signal_process(process, number):
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            if number == signal.SIGINT:
                Path(process.rta_cancel_file).touch()
            else:
                process.kill()
        else:
            os.killpg(process.pid, number)
    except ProcessLookupError:
        pass


def session_options():
    return {} if os.name == "nt" else {"start_new_session": True}
