import subprocess, sys
result = subprocess.run(
    [sys.executable, "lia4.py"],
    capture_output=True, text=True, timeout=12,
    encoding="utf-8", errors="replace"
)
print("STDOUT:", result.stdout[:3000])
print("STDERR:", result.stderr[:3000])
