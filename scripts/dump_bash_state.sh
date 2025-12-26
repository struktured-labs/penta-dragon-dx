#!/bin/bash
# Stub function/command for dump_bash_state to prevent "command not found" errors
# This is a workaround for Cursor agent sessions that may call this function

# If sourced, define as function; if executed, run as script
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    # Being sourced - define as function
    dump_bash_state() {
        # No-op function - just return success
        return 0
    }
    export -f dump_bash_state
else
    # Being executed directly - just exit successfully
    exit 0
fi

