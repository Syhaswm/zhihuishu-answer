"""Create Gitee + GitHub release and upload Setup.exe."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from publish_release import main  # noqa: E402

if __name__ == "__main__":
    main()
