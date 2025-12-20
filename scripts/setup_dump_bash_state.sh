#!/bin/bash
# Setup script to ensure dump_bash_state is available
# Run this if you continue to see "dump_bash_state: command not found" errors

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.local/bin"

# Create target directory if it doesn't exist
mkdir -p "$TARGET_DIR"

# Create symlink
ln -sf "$SCRIPT_DIR/dump_bash_state.sh" "$TARGET_DIR/dump_bash_state"

# Make sure it's executable
chmod +x "$SCRIPT_DIR/dump_bash_state.sh"

echo "✓ Created symlink: $TARGET_DIR/dump_bash_state"
echo "✓ Command should now be available in PATH"
echo ""
echo "If you still see errors, try:"
echo "  1. Restart your terminal/Cursor"
echo "  2. Run: source ~/.bashrc (if ~/.local/bin is in your PATH)"
echo "  3. Or manually add to PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""


