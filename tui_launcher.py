import subprocess
import sys

import launcher


def main() -> int:
    problem = launcher.check_prerequisites()
    if problem:
        print(f"ERROR: {problem}")
        input("Press Enter to exit...")
        return 1

    # textual/httpx (tui.py's own top-level imports) aren't installed until
    # bootstrap has run - importing tui.py before this point would crash
    # immediately with ModuleNotFoundError on a fresh install, and since this
    # runs from a console-mode shortcut, that crash's traceback flashes and
    # the console closes before anyone can read it. Bootstrap runs first,
    # with plain console output, then tui.py is only imported afterwards.
    try:
        launcher.run_bootstrap_if_needed()
    except subprocess.CalledProcessError as e:
        print(f"First-time setup failed: {e}")
        input("Press Enter to exit...")
        return 1

    import tui
    return tui.main() or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)
