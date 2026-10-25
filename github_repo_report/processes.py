"""Bounded subprocess execution with credential-helper descendant cleanup."""
import os
import signal
import subprocess


def terminate_tree(process):
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        # /T includes helper descendants, /F avoids interactive termination.
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=2, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
        if process.poll() is None:
            process.kill()


def run_command(command, *, timeout, input=None, check=False, **options):
    if input is not None:
        options["stdin"] = subprocess.PIPE
    if os.name == "posix":
        options["start_new_session"] = True
    else:
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(command, **options)
    try:
        stdout, stderr = process.communicate(input, timeout=timeout)
    except BaseException:
        # Kill before waiting: descendants can hold the output pipes open even
        # after their immediate parent exits. Never drain those pipes unbounded.
        terminate_tree(process)
        process.wait(timeout=2)
        raise
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result
