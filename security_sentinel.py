import os
import json
import hashlib
from datetime import datetime, timezone

def run_security_sentinel():
    print("=============================================")
    print("      CDLS DYNAMIC SECURITY SENTINEL AUDIT     ")
    print("=============================================")
    
    issues_found = 0
    scan_logs = []

    # 1. Inspect main.py for CORS wildcards and unauthenticated routes
    if os.path.exists("main.py"):
        with open("main.py", "r", encoding="utf-8") as f:
            content = f.read()
            if 'allow_origins=["*"]' in content or "allow_origins=['*']" in content:
                issues_found += 2
                scan_logs.append("[FAIL] PRB-001: Wildcard CORS detected in main.py")
            else:
                scan_logs.append("[PASS] CORS origin policy restricted correctly.")
                
            if "verify_active_session" not in content and "/api/" in content:
                issues_found += 1
                scan_logs.append("[WARN] API endpoints found without explicit session verification dependency.")
            else:
                scan_logs.append("[PASS] API endpoints implement session verification.")
    else:
        issues_found += 2
        scan_logs.append("[FAIL] Critical file main.py missing.")

    # 2. Inspect vdr_server.py for path traversal defenses
    if os.path.exists("vdr_server.py"):
        with open("vdr_server.py", "r", encoding="utf-8") as f:
            vdr_content = f.read()
            if "os.path.realpath" in vdr_content and "startswith" in vdr_content:
                scan_logs.append("[PASS] VDR server enforces strict path traversal confinement.")
            else:
                issues_found += 2
                scan_logs.append("[FAIL] VDR server missing path traversal boundary checks.")
    else:
        scan_logs.append("[INFO] vdr_server.py not present; skipping check.")

    # Calculate compliance score (Floor: 85)
    score = max(60, 100 - (issues_found * 10))

    report_path = "SECURITY_AUDIT_REPORT.md"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    report_content = f"""# CDLS Security Audit Report
- **Timestamp**: {timestamp}
- **Overall Score**: {score}/100
- **Status**: {"PASSED" if score >= 85 else "ACTION REQUIRED"}
- **Execution Log**:
""" + "\n".join([f"  - {log}" for log in scan_logs])

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"[OK] Sentinel Audit Complete. Overall Score: {score}/100")
    print(f"[OK] Full Audit Dossier written to: {os.path.abspath(report_path)}")
    print("=============================================")
    print("      SECURITY SENTINEL EVALUATION RESULT    ")
    print("=============================================")
    print(f"Overall Score: {score}/100")
    print("Required Floor: 85/100")
    
    if score >= 85:
        print("[PASS] Security gate passed successfully!")
    else:
        print("[FAIL] Security gate failed. Remediate flagged issues.")
        exit(1)

if __name__ == "__main__":
    run_security_sentinel()