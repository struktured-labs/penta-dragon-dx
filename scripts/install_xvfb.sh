#!/bin/bash
# Install Xvfb for headless screenshot support
echo "Installing Xvfb for virtual display support..."
sudo apt-get update
sudo apt-get install -y xvfb
echo "✅ Xvfb installed. Screenshots should now work with mgba-qt."



