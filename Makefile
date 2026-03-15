# Penta Dragon DX Remake - GBDK-2020 Makefile
GBDK    = /home/struktured/gbdk
LCC     = $(GBDK)/bin/lcc

# Project
PROJECT = penta_dragon_dx
SRCDIR  = src
OBJDIR  = obj
BINDIR  = rom/working
ASSETDIR = assets/extracted

# Flags
LCCFLAGS  = -Wa-l -Wl-m -Wl-j -Wl-yt0x1B -Wl-yo4 -Wl-ya4
# -yt0x1B = MBC5+RAM+BATTERY
# -yo4    = 4 ROM banks (64KB, expandable)
# -ya4    = 4 RAM banks

# CGB mode flag
LCCFLAGS += -Wm-yc
# -yc = CGB compatible (works on both DMG and CGB)
# Use -Wm-yC for CGB-only

# Source files
SRCS = $(wildcard $(SRCDIR)/*.c)
OBJS = $(SRCS:$(SRCDIR)/%.c=$(OBJDIR)/%.o)

# Default target
all: dirs $(BINDIR)/$(PROJECT).gbc

dirs:
	@mkdir -p $(OBJDIR) $(BINDIR)

# Compile C to object
$(OBJDIR)/%.o: $(SRCDIR)/%.c
	$(LCC) $(LCCFLAGS) -c -o $@ $<

# Link to ROM
$(BINDIR)/$(PROJECT).gbc: $(OBJS)
	$(LCC) $(LCCFLAGS) -o $@ $(OBJS)

clean:
	rm -rf $(OBJDIR) $(BINDIR)/$(PROJECT).gbc $(BINDIR)/$(PROJECT).map $(BINDIR)/$(PROJECT).noi

# Run in emulator (headless for testing)
test: all
	@echo "Running headless test..."
	@rm -f tmp/test_done.txt
	@unset DISPLAY && unset WAYLAND_DISPLAY && \
	QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
	timeout 10 xvfb-run -a mgba-qt $(BINDIR)/$(PROJECT).gbc \
		--script tmp/screenshot_test.lua -l 0 || true
	@echo "Screenshot saved to tmp/remake_test.png"

# Run for human play (GUI)
play: all
	./mgba-qt.sh $(BINDIR)/$(PROJECT).gbc &

.PHONY: all clean dirs test play
