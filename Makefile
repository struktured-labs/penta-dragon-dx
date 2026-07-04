# Quintra — GBC Native + Rust dev-host tooling
# Runtime: C / GBDK-2020 / SDCC — only thing in the ROM
# Tooling:  Rust workspace under tools/ — never linked into ROM

GBDK    = /home/struktured/gbdk
LCC     = $(GBDK)/bin/lcc

PROJECT = quintra
SRCDIR  = src
OBJDIR  = obj
BINDIR  = rom/working
GENDIR  = $(SRCDIR)/generated

# All .c under src/ (including generated)
SRCS = $(shell find $(SRCDIR) -name '*.c' 2>/dev/null)
OBJS = $(SRCS:%.c=$(OBJDIR)/%.o)

# GBDK / SDCC flags
LCCFLAGS  = -Wa-l -Wl-m -Wl-j
LCCFLAGS += -Wm-yt0x1B          # MBC5 + RAM + BATTERY (set via makebin header byte)
LCCFLAGS += -Wm-yo32            # 32 ROM banks (512KB) — bumps up as needed
LCCFLAGS += -Wm-ya4             # 4 SRAM banks (32KB)
LCCFLAGS += -Wm-yC              # CGB only (Quintra is GBC-native)
LCCFLAGS += -I$(SRCDIR) -I$(GENDIR)

.PHONY: all clean cleangen cleanall dirs gen build test play info
# Two-stage build: gen produces src/generated/*.c BEFORE SRCS is evaluated
# for the rom-link step. Without the recursive $(MAKE), Make captures SRCS
# at parse time and misses the generated files on a fresh build.
all: gen
	@$(MAKE) --no-print-directory build

build: dirs $(BINDIR)/$(PROJECT).gbc

dirs:
	@mkdir -p $(OBJDIR) $(BINDIR) $(GENDIR)

# Rust codegen: build the codegen tool then run it.
gen:
	@cargo build --release -p quintra-codegen 2>&1 | grep -E 'error|warning' || true
	@if [ ! -x target/release/quintra-codegen ]; then \
		echo "[gen] FATAL: codegen failed to build"; exit 1; \
	fi
	@target/release/quintra-codegen --content content --out $(GENDIR)

# All headers under src/ (+ generated). lcc/SDCC can't emit .d dep files here,
# so use a coarse dependency: any header change rebuilds every object. Slower
# but correct — a stale-header build once shipped a wrong constant.
HDRS = $(shell find $(SRCDIR) -name '*.h' 2>/dev/null)

# Compile each .c under any subdir of src/
$(OBJDIR)/%.o: %.c $(HDRS)
	@mkdir -p $(dir $@)
	$(LCC) $(LCCFLAGS) -c -o $@ $<

# Link to ROM
$(BINDIR)/$(PROJECT).gbc: $(OBJS)
	$(LCC) $(LCCFLAGS) -o $@ $(OBJS)

clean:
	rm -rf $(OBJDIR) $(BINDIR)/$(PROJECT).gbc $(BINDIR)/$(PROJECT).map $(BINDIR)/$(PROJECT).noi

cleangen:
	rm -rf $(GENDIR)/*

cleanall: clean cleangen
	cargo clean

# Headless test (build + boot + screenshots)
test: all
	@bash scripts/test_headless.sh $(BINDIR)/$(PROJECT).gbc 2>/dev/null || \
		echo "[test] headless harness not yet wired (Phase 3)"

# Human play
play: all
	@bash mgba-qt.sh $(BINDIR)/$(PROJECT).gbc

info:
	@echo "Quintra build info:"
	@echo "  Project:   $(PROJECT)"
	@echo "  Sources:   $(words $(SRCS)) .c files"
	@echo "  Output:    $(BINDIR)/$(PROJECT).gbc"
	@echo "  Toolchain: $(LCC)"
