#!/usr/bin/env python3
"""
Utilities for positioning mgba-qt windows on specific monitors/desktops
Supports X11, Wayland (Sway/i3), and various window managers
"""
import subprocess
import time
import shutil
import os
import re

def get_monitor_geometry(monitor_num=3):
    """Get geometry of specific monitor using xrandr"""
    try:
        result = subprocess.run(
            ["xrandr"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        lines = result.stdout.splitlines()
        connected = [l for l in lines if "connected" in l]
        
        if monitor_num <= len(connected):
            monitor_line = connected[monitor_num - 1]
            # Parse: DP-1 connected primary 3440x1440+0+0
            match = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', monitor_line)
            if match:
                width, height, x, y = map(int, match.groups())
                return (x, y, width, height)
    except Exception:
        pass
    
    # Fallback: estimate based on common setup
    # Assuming 1920px wide monitors side-by-side
    return ((monitor_num - 1) * 1920, 0, 1920, 1080)

def get_wayland_outputs():
    """Get list of Wayland outputs using wlr-randr or swaymsg"""
    outputs = []
    
    # Try swaymsg first (Sway/i3)
    swaymsg = shutil.which("swaymsg")
    if swaymsg:
        try:
            result = subprocess.run(
                ["swaymsg", "-t", "get_outputs"],
                capture_output=True,
                text=True,
                timeout=2
            )
            # Parse JSON output for output names
            import json
            data = json.loads(result.stdout)
            outputs = [out["name"] for out in data]
        except Exception:
            pass
    
    # Try wlr-randr
    if not outputs:
        wlr_randr = shutil.which("wlr-randr")
        if wlr_randr:
            try:
                result = subprocess.run(
                    ["wlr-randr"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                # Parse output names from wlr-randr
                for line in result.stdout.splitlines():
                    if " connected" in line:
                        outputs.append(line.split()[0])
            except Exception:
                pass
    
    return outputs

def try_wmctrl(window_name, desktop_num=3):
    """Try to move window using wmctrl (X11 desktops/workspaces)"""
    wmctrl = shutil.which("wmctrl")
    if not wmctrl:
        return False
    
    try:
        # List windows
        result = subprocess.run(
            ["wmctrl", "-l"],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        for line in result.stdout.splitlines():
            if window_name.lower() in line.lower() or "mgba" in line.lower():
                win_id = line.split()[0]
                # Move to desktop (0-indexed)
                subprocess.run(
                    ["wmctrl", "-i", "-r", win_id, "-t", str(desktop_num - 1)],
                    timeout=2
                )
                print(f"   ✓ Moved window to desktop {desktop_num} using wmctrl")
                return True
    except Exception:
        pass
    
    return False

def try_xdotool(window_name, x_offset=3840, y_offset=0):
    """Try to move window using xdotool (X11 positioning)"""
    xdotool = shutil.which("xdotool")
    if not xdotool:
        return False
    
    try:
        # Find window by name
        result = subprocess.run(
            ["xdotool", "search", "--name", window_name],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        if not result.stdout.strip():
            # Try partial match
            result = subprocess.run(
                ["xdotool", "search", "--class", "mgba-qt"],
                capture_output=True,
                text=True,
                timeout=2
            )
        
        if result.stdout.strip():
            win_id = result.stdout.strip().split()[0]
            subprocess.run(
                ["xdotool", "windowmove", win_id, str(x_offset), str(y_offset)],
                timeout=2
            )
            print(f"   ✓ Moved window to position ({x_offset}, {y_offset}) using xdotool")
            return True
    except Exception:
        pass
    
    return False

def try_swaymsg(window_name, monitor_num=3):
    """Try to move window using swaymsg (Sway/i3 Wayland)"""
    swaymsg = shutil.which("swaymsg")
    if not swaymsg:
        return False
    
    try:
        # Get output name for monitor
        outputs = get_wayland_outputs()
        if monitor_num <= len(outputs):
            output_name = outputs[monitor_num - 1]
        else:
            # Fallback: try DP-{num} naming convention
            output_name = f"DP-{monitor_num}"
        
        # Move window to output
        subprocess.run(
            ["swaymsg", f'[app_id="mgba-qt"]', "move", "to", "output", output_name],
            timeout=2
        )
        print(f"   ✓ Moved window to output {output_name} using swaymsg")
        return True
    except Exception:
        pass
    
    return False

def move_window_to_monitor(window_name="mGBA", monitor_num=3):
    """Move window to specific monitor using available tools"""
    # Get monitor geometry for X11 positioning
    geo = get_monitor_geometry(monitor_num)
    x_offset = geo[0]
    
    # Try different methods in order of preference
    methods = [
        lambda: try_wmctrl(window_name, monitor_num),  # Desktop switching
        lambda: try_xdotool(window_name, x_offset),    # X11 positioning
        lambda: try_swaymsg(window_name, monitor_num), # Wayland (Sway/i3)
    ]
    
    for method in methods:
        if method():
            return True
    
    print(f"   ⚠️  Could not automatically move window")
    print(f"   💡 Window should appear - please move it to monitor {monitor_num} manually")
    return False

def get_mgba_env_for_positioning(monitor_num=3):
    """Get environment variables for launching mgba-qt with initial positioning"""
    env = os.environ.copy()
    
    # Get monitor geometry
    geo = get_monitor_geometry(monitor_num)
    x_pos, y_pos = geo[0], geo[1]
    
    # Force Qt to use X11 backend (XWayland) for better window control
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        env.setdefault("QT_QPA_PLATFORM", "xcb")
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"
    
    # Set X11 window position hints (for X11/XWayland)
    # These are read by window managers before window appears
    env["_NET_WM_USER_TIME"] = "0"  # Prevent focus stealing
    
    # For X11: Set initial position using X11 properties
    # Note: Qt doesn't directly support geometry env vars, but we can try
    # Some window managers respect these
    
    return env, (x_pos, y_pos)

def get_mgba_env_for_xwayland():
    """Get environment variables for launching mgba-qt with XWayland support"""
    env, _ = get_mgba_env_for_positioning()
    return env

def create_position_wrapper_script(app_cmd, monitor_num=3):
    """Create a wrapper script that positions window immediately after launch"""
    import tempfile
    
    geo = get_monitor_geometry(monitor_num)
    x_pos, y_pos = geo[0], geo[1]
    
    # Try to get Wayland output name
    outputs = get_wayland_outputs()
    output_name = None
    if monitor_num <= len(outputs):
        output_name = outputs[monitor_num - 1]
    
    wrapper_content = f"""#!/bin/bash
# Wrapper script to launch app and position window immediately

# Launch app in background
{' '.join(app_cmd)} &
APP_PID=$!

# Wait for window to appear (but position immediately)
sleep 0.1

# Try to position window immediately using multiple methods
"""
    
    # Add swaymsg positioning (Wayland)
    if output_name:
        wrapper_content += f"""
# Method 1: Sway/i3 Wayland
if command -v swaymsg >/dev/null 2>&1; then
    swaymsg '[app_id="mgba-qt"] move to output {output_name}' 2>/dev/null || true
fi
"""
    
    # Add xdotool positioning (X11)
    wrapper_content += f"""
# Method 2: xdotool (X11)
if command -v xdotool >/dev/null 2>&1; then
    WIN_ID=$(xdotool search --pid $APP_PID --class "mgba-qt" 2>/dev/null | head -1)
    if [ -n "$WIN_ID" ]; then
        xdotool windowmove $WIN_ID {x_pos} {y_pos} 2>/dev/null || true
    fi
fi

# Method 3: wmctrl (X11 desktops)
if command -v wmctrl >/dev/null 2>&1; then
    sleep 0.2
    wmctrl -r "mGBA" -t {monitor_num - 1} 2>/dev/null || true
fi

# Wait for app to finish
wait $APP_PID
"""
    
    # Write wrapper script
    wrapper_path = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
    wrapper_path.write(wrapper_content)
    wrapper_path.close()
    
    # Make executable
    import stat
    os.chmod(wrapper_path.name, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)
    
    return wrapper_path.name
