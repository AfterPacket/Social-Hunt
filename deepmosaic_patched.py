# Social-Hunt/deepmosaic_patched.py
"""
Patched version of DeepMosaic that runs non-interactively
"""
import sys
import os

# Add the DeepMosaics directory to the path
deepmosaic_dir = os.path.join(os.path.dirname(__file__), "DeepMosaics")
sys.path.insert(0, deepmosaic_dir)

# Monkey patch the input() function to raise an exception instead of waiting
import builtins
original_input = builtins.input

def noninteractive_input(prompt=""):
    if "press any key" in prompt.lower() or "key to exit" in prompt.lower():
        raise KeyboardInterrupt("Non-interactive mode: cannot wait for user input")
    # For other inputs, return a default value or raise
    raise RuntimeError(f"Cannot get input in non-interactive mode: {prompt}")

builtins.input = noninteractive_input

# Now import and run the actual DeepMosaic
try:
    from deepmosaic import main
    # Check if main is callable
    if callable(main):
        main()
    else:
        # If deepmosaic doesn't have a main function, we need to handle it differently
        import deepmosaic
        # The module might execute code on import
        print("DeepMosaic module loaded")
except KeyboardInterrupt as e:
    print(f"Interrupted: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)