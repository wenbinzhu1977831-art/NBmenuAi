import sys
import os
import time

print("BOOTING SCRIPT STARTED - DELAYING TO FLUSH LOGS", flush=True)
time.sleep(2)

try:
    print("IMPORTING SERVER...", flush=True)
    import server
    print("SERVER MODULE IMPORTED SUCESSFULLY.", flush=True)
except Exception as e:
    print(f"FATAL BOOT ERROR CAUGHT BY WRAPPER: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    # Keep the container alive briefly to guarantee log transmission to Cloud Logging
    time.sleep(1)
    sys.exit(1)

import uvicorn
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"STARTING UVICORN ON PORT {port}", flush=True)
    try:
        uvicorn.run("server:app", host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        print(f"UVICORN CRASHED: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        time.sleep(1)
        sys.exit(1)

print("BOOT SCRIPT FINISHED.", flush=True)
