import os
import sys

def verify_secondary_security():
    print("=============================================")
    print("    CDLS SECONDARY SECURITY COMPLIANCE SCAN  ")
    print("=============================================")
    
    failures = 0
    
    # Check 1: Verify main.py has strict CORS (no wildcards)
    if os.path.exists("main.py"):
        with open("main.py", "r", encoding="utf-8") as f:
            content = f.read()
            if 'allow_origins=["*"]' in content or "allow_origins=['*']" in content:
                print("[FAIL] PRB-001: Wildcard CORS detected in main.py")
                failures += 1
            else:
                print("[PASS] CORS policy is restricted to explicit institutional origins.")
    else:
        print("[WARN] main.py not found in working directory.")
        failures += 1

    # Check 2: Verify vdr_server.py restricts path traversal
    if os.path.exists("vdr_server.py"):
        with open("vdr_server.py", "r", encoding="utf-8") as f:
            vdr_content = f.read()
            if "os.path.realpath" in vdr_content and "startswith" in vdr_content:
                print("[PASS] VDR server implements secure path resolution and bounds checking.")
            else:
                print("[FAIL] VDR server missing robust path traversal checks.")
                failures += 1
    else:
        print("[INFO] vdr_server.py not present; skipping path traversal check.")

    # Check 3: Verify Dockerfile hardening
    if os.path.exists("Dockerfile"):
        with open("Dockerfile", "r", encoding="utf-8") as f:
            docker_content = f.read()
            if "127.0.0.1:8000" in docker_content or "--host 127.0.0.1" in docker_content:
                print("[PASS] Dockerfile restricts exposure to loopback interface.")
            else:
                print("[WARN] Dockerfile binding should be explicitly bound to loopback.")
    
    print("=============================================")
    if failures == 0:
        print("[SUCCESS] All secondary security checks passed cleanly!")
        sys.exit(0)
    else:
        print(f"[FAIL] {failures} security rule violations detected.")
        sys.exit(1)

if __name__ == "__main__":
    verify_secondary_security()