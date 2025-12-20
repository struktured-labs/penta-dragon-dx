#!/usr/bin/env python3
import subprocess
import time
import socket
import sys
from pathlib import Path

def get_pc(s):
    try:
        s.sendall(b"$g#67")
        data = s.recv(1024).decode('ascii', errors='ignore')
        # In mGBA GDB stub for Game Boy:
        # Registers: A, F, B, C, D, E, H, L, SP, PC
        # Each is 2 hex chars (1 byte), except SP and PC which are 4 hex chars (2 bytes).
        # Packet format: $ (data) # (checksum)
        if data.startswith('$') and '#' in data:
            regs = data[1:data.find('#')]
            # PC is the last 4 characters
            return regs[-4:]
    except:
        return None
    return None

def verify_rom(rom_path):
    print(f"🔍 Headless Debugging: {rom_path}")
    
    # Start mgba with GDB stub
    proc = subprocess.Popen(["/usr/local/bin/mgba", "-g", rom_path], 
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(3) # Give it time to initialize
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(("127.0.0.1", 2345))
        s.sendall(b"+") # Ack
        
        print("🚀 Executing...")
        s.sendall(b"$c#63") # Continue
        
        # Monitor for 5 seconds
        history = []
        for i in range(10):
            time.sleep(1)
            # Break execution to read PC
            s.sendall(b"\x03") 
            time.sleep(0.1)
            pc = get_pc(s)
            if pc:
                print(f"  Frame {i}: PC=0x{pc}")
                history.append(pc)
            # Resume
            s.sendall(b"$c#63")
            
        s.close()
        proc.terminate()
        
        if len(history) < 2:
            print("❌ FAILED: Could not read PC history.")
            return False
            
        # If PC is always the same, it's frozen
        if len(set(history)) == 1:
            print(f"❌ FAILED: Frozen at PC=0x{history[0]}")
            return False
            
        # Check if PC is in a "crash" range (like 0000 or FFxx)
        last_pc = int(history[-1], 16)
        if last_pc == 0 or last_pc >= 0xFF00:
            print(f"❌ FAILED: Crashed at PC=0x{last_pc:04X}")
            return False

        print("✅ SUCCESS: Game is running and Program Counter is moving.")
        return True

    except Exception as e:
        print(f"💥 Error connecting to GDB: {e}")
        proc.terminate()
        return False

if __name__ == "__main__":
    rom = "rom/working/penta_dragon_cursor_dx.gb"
    if not verify_rom(rom):
        sys.exit(1)
    sys.exit(0)

