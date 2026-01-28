# deepmosaic_runner.py
import subprocess
import sys
import os
from pathlib import Path

def run_deepmosaic_noninteractive(args):
    """
    Run DeepMosaic with non-interactive handling
    """
    # Build the command
    cmd = [sys.executable, "-u"] + args  # -u for unbuffered output
    
    # Run the process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,  # Don't allow stdin
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Read output in real-time
    output_lines = []
    error_lines = []
    
    while True:
        # Read stdout
        stdout_line = process.stdout.readline()
        if stdout_line:
            output_lines.append(stdout_line)
            sys.stdout.write(stdout_line)
        
        # Read stderr
        stderr_line = process.stderr.readline()
        if stderr_line:
            error_lines.append(stderr_line)
            sys.stderr.write(stderr_line)
        
        # Check if process has finished
        if process.poll() is not None:
            # Read any remaining output
            remaining_stdout, remaining_stderr = process.communicate()
            if remaining_stdout:
                output_lines.append(remaining_stdout)
                sys.stdout.write(remaining_stdout)
            if remaining_stderr:
                error_lines.append(remaining_stderr)
                sys.stderr.write(remaining_stderr)
            break
    
    return process.returncode, ''.join(output_lines), ''.join(error_lines)

if __name__ == "__main__":
    # Pass through all arguments
    returncode, stdout, stderr = run_deepmosaic_noninteractive(sys.argv[1:])
    sys.exit(returncode)