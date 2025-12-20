#!/usr/bin/env python3
"""Shared utilities for positioning mgba-qt windows on specific monitors"""
import subprocess
import time
import shutil
import os

# Default monitor: Monitor 2 (DP-3, second Dell monitor at x=5360)
# Monitor 0 = DP-1 (LG curved, 3440x1440 at x=0)
# Monitor 1 = DP-2 (Dell, 1920x1200 at x=3440)
# Monitor 2 = DP-3 (Dell, 1920x1200 at x=5360) - DEFAULT
DEFAULT_MONITOR = 2

def get_monitor_positions():
    """Get monitor positions from xrandr"""
    try:
        result = subprocess.run(
            ["xrandr", "--listmonitors"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            monitors = {}
            for line in result.stdout.strip().split('\n')[1:]:  # Skip header
                # Format: " 0: +*DP-1 3440/800x1440/335+0+0  DP-1"
                # Or:     " 1: +DP-2 1920/518x1200/324+3440+0  DP-2"
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        monitor_num = int(parts[0].rstrip(':'))
                        # Find the geometry part (contains +X+Y offset)
                        # Look for part with +X+Y pattern (e.g., "+0+0" or "+3440+0")
                        for part in parts[1:]:
                            if '+' in part and part.count('+') >= 2:
                                # Extract x position from +X+Y format
                                # Split by + and get the second element (X position)
                                offset_parts = part.split('+')
                                if len(offset_parts) >= 2:
                                    x_pos = int(offset_parts[1])
                                    monitors[monitor_num] = x_pos
                                    break
                    except (ValueError, IndexError):
                        continue
            return monitors
    except:
        pass
    # Fallback: common monitor setups
    return {0: 0, 1: 1920, 2: 3840}

def get_mgba_env_for_xwayland():
    """Get environment variables to force mgba-qt to run in XWayland mode (so xdotool works)"""
    env = os.environ.copy()
    # Force Qt to use X11 backend instead of Wayland
    env['QT_QPA_PLATFORM'] = 'xcb'
    env['GDK_BACKEND'] = 'x11'
    # Keep DISPLAY for XWayland
    if 'DISPLAY' not in env:
        env['DISPLAY'] = ':0'
    return env

def move_window_to_monitor(window_title="mGBA", monitor_number=None):
    """Move mgba-qt window to a specific monitor
    
    Supports both X11 (xdotool) and Wayland (KDE qdbus, Sway swaymsg)
    For Wayland, attempts to force XWayland mode for better compatibility.
    
    Args:
        window_title: Window title or class to search for (default: "mGBA")
        monitor_number: 0 = first monitor, 1 = second monitor (Dell, default), 2 = third monitor
                       If None, uses DEFAULT_MONITOR
    
    Returns:
        bool: True if window was moved successfully, False otherwise
    """
    if monitor_number is None:
        monitor_number = DEFAULT_MONITOR
    
    # Detect session type
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    is_wayland = session_type == "wayland"
    
    # Detect compositor
    is_kde = shutil.which("kwin_wayland") is not None
    is_sway = shutil.which("swaymsg") is not None
    
    try:
        # Get monitor/output name for Wayland
        monitors = get_monitor_positions()
        if monitor_number not in monitors:
            print(f"   ⚠️  Monitor {monitor_number} not found. Available: {list(monitors.keys())}")
            return False
        
        monitor_offset_x = monitors[monitor_number]
        
        # For Wayland, get output name (DP-2 for monitor 1)
        output_name = None
        if is_wayland:
            try:
                result = subprocess.run(
                    ["xrandr", "--listmonitors"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[1:]
                    for line in lines:
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                mon_num = int(parts[0].rstrip(':'))
                                if mon_num == monitor_number:
                                    # Extract output name (last part, e.g., "DP-2")
                                    output_name = parts[-1]
                                    break
                            except:
                                continue
            except:
                pass
        
        # Always try xdotool first (works for X11, XWayland, and some Wayland windows)
        # Even on Wayland, if app is launched with QT_QPA_PLATFORM=xcb, it will be XWayland
        if not shutil.which("xdotool"):
            print(f"   ⚠️  xdotool not found - cannot position window (install with: sudo apt install xdotool)")
            # Fall back to Wayland methods if available
            if is_wayland and is_kde:
                return _move_window_kde_wayland(window_title, output_name or f"DP-{monitor_number + 1}", monitor_number)
            elif is_wayland and is_sway:
                return _move_window_sway(window_title, output_name or f"DP-{monitor_number + 1}", monitor_number)
            return False
        
        # Get baseline windows before launch (if we can)
        baseline_windows = set()
        try:
            baseline_result = subprocess.run(
                ["xdotool", "search", "--all", "--name", "."],
                capture_output=True,
                text=True,
                timeout=1
            )
            if baseline_result.returncode == 0:
                baseline_windows = set(baseline_result.stdout.strip().split('\n'))
        except:
            pass
        
        # Wait longer on first attempt (window needs time to appear)
        for attempt in range(8):  # More attempts
            wait_time = 1.5 if attempt == 0 else 0.8  # Longer initial wait
            time.sleep(wait_time)
            
            # Strategy 1: Search by class/name patterns
            # Try exact class match first (most reliable for XWayland)
            search_patterns = [
                ("--class", "mgba-qt"),  # Most specific
                ("--class", "mGBA"),
                ("--class", "mgba"),
                ("--name", "mGBA"),
                ("--name", window_title),
                ("--name", "mgba"),
            ]
            
            for search_type, pattern in search_patterns:
                try:
                    result = subprocess.run(
                        ["xdotool", "search", search_type, pattern],
                        capture_output=True,
                        text=True,
                        timeout=1
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        candidates = result.stdout.strip().split('\n')
                        # Take the first valid window ID that's not in baseline
                        for candidate_id in candidates:
                            if candidate_id and candidate_id not in baseline_windows:
                                window_id = candidate_id
                                break
                        if window_id:
                            break
                except:
                    continue
            
            if window_id:
                break
            
            # Strategy 2: Find new windows that appeared after baseline
            try:
                current_result = subprocess.run(
                    ["xdotool", "search", "--all", "--name", "."],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if current_result.returncode == 0:
                    current_windows = set(current_result.stdout.strip().split('\n'))
                    new_windows = current_windows - baseline_windows
                    
                    # Check each new window
                    for win_id in new_windows:
                        if not win_id:
                            continue
                        try:
                            # Check if it's a reasonable size (not a tiny popup)
                            name_result = subprocess.run(
                                ["xdotool", "getwindowname", win_id],
                                capture_output=True,
                                text=True,
                                timeout=0.3
                            )
                            class_result = subprocess.run(
                                ["xdotool", "getwindowclassname", win_id],
                                capture_output=True,
                                text=True,
                                timeout=0.3
                            )
                            
                            name = name_result.stdout.strip().lower() if name_result.returncode == 0 else ""
                            class_name = class_result.stdout.strip().lower() if class_result.returncode == 0 else ""
                            
                            # If name is empty/short or class contains qt/mgba, it might be mgba
                            if (not name or len(name) < 10) or 'qt' in class_name or 'mgba' in class_name:
                                window_id = win_id
                                break
                        except:
                            continue
                    
                    if window_id:
                        break
            except:
                continue
            
            if window_id:
                break  # Found window, exit retry loop
        
        # Move window to specified monitor if found
        if window_id:
            try:
                result = subprocess.run(
                    ["xdotool", "windowmove", window_id, str(monitor_offset_x), "0"],
                    timeout=1,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print(f"   ✓ Positioned window on monitor {monitor_number} (offset: {monitor_offset_x}px)")
                    return True
                else:
                    print(f"   ⚠️  xdotool windowmove failed: {result.stderr}")
            except Exception as e:
                print(f"   ⚠️  Error moving window: {e}")
        
        # If we didn't find it, print debug info
        if not window_id:
            print(f"   ⚠️  Could not find mgba-qt window after {8} attempts")
            if is_wayland:
                print(f"   💡 On Wayland, xdotool may not detect native Wayland windows")
                print(f"   💡 Try setting QT_QPA_PLATFORM=xcb before launching mgba-qt")
                if is_kde:
                    print(f"   💡 Or use KDE window manager (Alt+F3 > More Actions > Move to Output)")
            print(f"   💡 Window may need to be moved manually to Monitor {monitor_number} (x={monitor_offset_x})")
    except Exception as e:
        print(f"   ⚠️  Could not position window: {e}")
        import traceback
        traceback.print_exc()
    
    return False

def _move_window_kde_wayland(window_title, output_name, monitor_number):
    """Move window on KDE Wayland
    
    Note: Native Wayland windows are not accessible via xdotool.
    This function attempts to use xdotool for XWayland windows.
    """
    try:
        monitors = get_monitor_positions()
        monitor_offset_x = monitors[monitor_number]
        
        # Try xdotool (works for XWayland windows)
        if shutil.which("xdotool"):
            for attempt in range(6):
                time.sleep(1.2 if attempt == 0 else 0.8)
                
                # Try multiple search patterns
                for pattern in ["mgba-qt", "mGBA", "mgba"]:
                    result = subprocess.run(
                        ["xdotool", "search", "--class", pattern],
                        capture_output=True,
                        text=True,
                        timeout=1
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        win_id = result.stdout.strip().split('\n')[0]
                        # Verify it's actually mgba by checking name
                        try:
                            name_result = subprocess.run(
                                ["xdotool", "getwindowname", win_id],
                                capture_output=True,
                                text=True,
                                timeout=0.5
                            )
                            # If name is empty or short, it might be mgba (Qt apps sometimes have empty names)
                            name = name_result.stdout.strip()
                            if not name or len(name) < 20:  # Empty or short name = likely mgba
                                subprocess.run(
                                    ["xdotool", "windowmove", win_id, str(monitor_offset_x), "0"],
                                    timeout=1
                                )
                                print(f"   ✓ Positioned window on monitor {monitor_number} (offset: {monitor_offset_x}px)")
                                return True
                        except:
                            # Try moving anyway
                            subprocess.run(
                                ["xdotool", "windowmove", win_id, str(monitor_offset_x), "0"],
                                timeout=1
                            )
                            print(f"   ✓ Positioned window on monitor {monitor_number} (offset: {monitor_offset_x}px)")
                            return True
        
        # For native Wayland windows, we can't programmatically move them
        print(f"   ⚠️  Native Wayland window detected - automatic positioning limited")
        print(f"   💡 Window should be on Monitor {monitor_number} ({output_name})")
        print(f"   💡 If not, use KDE window manager (Alt+F3 > More Actions > Move to Output)")
        print(f"   💡 Or launch with: QT_QPA_PLATFORM=xcb mgba-qt ... to force XWayland mode")
        return False
    except Exception as e:
        return False

def _move_window_sway(window_title, output_name, monitor_number):
    """Move window on Sway using swaymsg"""
    try:
        if not shutil.which("swaymsg"):
            return False
        
        # Wait for window to appear
        time.sleep(2)
        
        # Find window by title/class and move to output
        result = subprocess.run(
            ["swaymsg", f"[class=\"mgba-qt\"]", "move", "to", "output", output_name],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        if result.returncode == 0:
            print(f"   ✓ Positioned window on {output_name} (monitor {monitor_number})")
            return True
        
        return False
    except Exception as e:
        return False
