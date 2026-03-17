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
# -yo4    = 4 ROM banks (64KB)
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

# Headless gameplay test (screenshots + input injection)
test: all
	@bash scripts/test_headless.sh $(BINDIR)/$(PROJECT).gbc

# Run for human play (GUI)
play: all
	@bash /home/struktured/projects/penta-dragon-dx-claude/scripts/launch_mgba.sh $(BINDIR)/$(PROJECT).gbc

.PHONY: all clean dirs test play
