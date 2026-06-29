"""Platform facade — OS-specific helpers without shadowing stdlib `platform`."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from platform_win import *  # noqa: F401,F403
elif sys.platform == "darwin":
    from platform_darwin import *  # noqa: F401,F403
else:
    from platform_darwin import *  # noqa: F401,F403
