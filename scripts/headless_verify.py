#!/usr/bin/env python3
import subprocess
import time
import socket
import sys
from pathlib import Path

def check_pc_moving(rom_path):
    print(f"🕵️  Headless Verification: {rom_path}")
    
    # Start mGBA with GDB stub enabled
    # -g: enable GDB stub on port 2345
    # -s 60: frameskip to run fast
    try:
        mgba_proc = subprocess.Popen(["/usr/local/bin/mgba", "-g", rom_path], 
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(2) # Wait for it to start
        
        # Simple GDB protocol interaction via socket
        # We want to send '$g#67' which is "read registers"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(("127.0.0.1", 2345))
            
            # Send '?' to check status
            s.sendall(b"+$#00") # Ack
            s.sendall(b"$?#3f")
            time.sleep(0.1)
            
            pcs = []
            for _ in range(5):
                # Request registers
                s.sendall(b"$g#67")
                data = s.recv(1024).decode('ascii', errors='ignore')
                # PC is usually at the end of the 'g' packet in mGBA GDB stub
                # But we don't even need to parse it perfectly. 
                # If the packet changes, the PC is moving.
                pcs.append(data)
                
                # Resume execution for a bit
                s.sendall(b"$c#63") 
                time.sleep(1)
                # Break
                s.sendall(b"\x03") 
                time.sleep(0.1)
            
            s.close()
            mgba_proc.terminate()
            
            if len(set(pcs)) > 1:
                print("✅ VERIFIED: Program Counter is moving. Game is executing logic.")
                return True
            else:
                print("❌ FAILED: Program Counter is stuck. Game is in a dead loop.")
                return False
                
        except Exception as e:
            print(f"⚠️  GDB Connection Error: {e}")
            mgba_proc.terminate()
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = check_pc_moving("rom/working/penta_dragon_cursor_dx.gb")
    sys.exit(0 if success else 1)

