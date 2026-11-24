import subprocess
import time
from pathlib import Path

log = Path("/opt/ai-workbench/rebuild.log")

for i in range(80):
    text = log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
    if "REBUILD_DONE" in text:
        print("FOUND_DONE")
        print(text[-2500:])
        raise SystemExit(0)
    r1 = subprocess.run(["pgrep", "-f", "remote-rebuild.sh"], capture_output=True)
    r2 = subprocess.run(["pgrep", "-f", "compose build"], capture_output=True)
    if r1.returncode != 0 and r2.returncode != 0:
        print("PROCESS_ENDED")
        print(text[-3000:])
        raise SystemExit(1)
    print(f"WAIT {i + 1}")
    time.sleep(15)

print("TIMEOUT")
print(log.read_text(encoding="utf-8", errors="ignore")[-2500:])
raise SystemExit(2)
