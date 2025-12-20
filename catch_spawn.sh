#!/bin/bash
# Monitor for quick_verify processes and show parent tree
while true; do
    PID=$(pgrep -f "quick_verify" | head -1)
    if [ -n "$PID" ]; then
        echo "=== CAUGHT PROCESS $PID ==="
        echo "Full process info:"
        ps -ef | grep $PID | grep -v grep
        echo ""
        echo "Process tree:"
        pstree -p $PID 2>/dev/null || pstree -p $(ps -o ppid= -p $PID | tr -d ' ') 2>/dev/null
        echo ""
        echo "Parent process:"
        PPID=$(ps -o ppid= -p $PID | tr -d ' ')
        ps -ef | grep "^[^ ]* *$PPID " | grep -v grep
        echo ""
        echo "Command line of parent:"
        cat /proc/$PPID/cmdline 2>/dev/null | tr '\0' ' ' || echo "Cannot read"
        echo ""
        break
    fi
    sleep 1
done

