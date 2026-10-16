"""Single source of truth for displayed and packaged AURORA AutoFill versions."""
from datetime import date

from .versioning import canonical_to_bridge, parse_dated_version

APP_NAME = "AURORA AutoFill"
BASE_VERSION = "0.6.1"
# The build pipeline writes this module before tests and packaging. A source
# checkout stays explicitly marked as development instead of claiming stability.
try:
    from ._build import BUILD_VERSION, SOURCE_COMMIT
except ImportError:
    BUILD_VERSION, SOURCE_COMMIT = f"{BASE_VERSION}-dev.0", ""
APP_VERSION = BUILD_VERSION
IS_PRERELEASE = "-" in APP_VERSION
_dated = parse_dated_version(APP_VERSION)
if _dated:
    # DDMMYY is the public version; package managers need chronological dates.
    DEBIAN_VERSION = canonical_to_bridge(APP_VERSION).replace("-", "~", 1)
    WINDOWS_VERSION = BASE_VERSION + "." + str((_dated[1] - date(2000, 1, 1)).days)
else:
    DEBIAN_VERSION = APP_VERSION.replace("-", "~", 1)
    WINDOWS_VERSION = BASE_VERSION + "." + (
        APP_VERSION.split("-dev.", 1)[1].split(".", 1)[0]
        if "-dev." in APP_VERSION else "0")
GITHUB_REPOSITORY = "fabriciomatosqa/AURORA-AutoFill"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
GITHUB_LATEST_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases"
