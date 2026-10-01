/* Issue #16: retain unresampled native mGBA GB PCM plus full-frame/state data.
 * Diagnostic LD_PRELOAD adapter for the pinned core, not an emulator launcher.
 * The checked-in single-flight launcher must still own the emulator process.
 * Compile against that exact core's headers AND compile definitions.
 */
#include <mgba/core/core.h>
#include <mgba/core/thread.h>
#include <dlfcn.h>
#include <errno.h>
#include <unistd.h>
#include <stdatomic.h>

static struct mCore *owner;
static bool (*real_init)(struct mCore *);
static void (*real_set_stream)(struct mCore *, struct mAVStream *);
static bool (*real_load_state)(struct mCore *, const void *);
static struct mAVStream tap, *downstream;
static FILE *pcm, *video, *states, *timeline;
static FILE *lifecycle;
static unsigned width, height, rate;
static uint64_t samples, frames;
static void *state_buffer;
static size_t state_size;
static void finish(void);
static ThreadCallback saved_reset_callback;
static struct mCoreThread *startup_thread;
static const char *startup_marker;
static bool restored;
static atomic_bool startup_blocked;
static void (*real_run_loop)(struct mCore *);
static void (*real_step)(struct mCore *);

/* The debugger dispatch can execute before thread.c services a pending pause.
 * Prevent that execution, rather than dropping its audio or rewinding it. */
static void gated_run_loop(struct mCore *core) {
    if (!atomic_load(&startup_blocked)) real_run_loop(core);
}

static void gated_step(struct mCore *core) {
    if (!atomic_load(&startup_blocked)) real_step(core);
}

/* #43: opt-in replay barrier. Pause before the first CPU loop, restore through
 * Qt's normal path, then release only after the probe explicitly finishes its
 * initialization. This changes host startup ordering, not emulated timing. */
static void startup_reset(struct mCoreThread *context) {
    mCoreThreadPauseFromThread(context);
    if (saved_reset_callback) saved_reset_callback(context);
    context->resetCallback = saved_reset_callback;
}

void mCoreThreadContinue(struct mCoreThread *context) {
    void (*resume)(struct mCoreThread *) = dlsym(RTLD_NEXT, "mCoreThreadContinue");
    if (!resume) _exit(74);
    resume(context);
    if (context == startup_thread && startup_marker &&
        access(startup_marker, F_OK) == 0 && context->impl->interruptDepth == 0) {
        if (!restored || samples || frames) {
            fprintf(stderr, "native AV startup rejected: restored=%d samples=%" PRIu64
                    " frames=%" PRIu64 " interrupt_depth=%d\n",
                    restored, samples, frames, context->impl->interruptDepth);
            _exit(74);
        }
        startup_marker = NULL;
        startup_thread = NULL;
        atomic_store(&startup_blocked, false);
        mCoreThreadUnpause(context);
    }
}

/* Explicit #43 negative control only. Qt calls loadState after thread start;
 * delaying its GUI thread exposes that startup window without editing ROMs. */
bool mCoreThreadStart(struct mCoreThread *context) {
    bool (*start)(struct mCoreThread *) = dlsym(RTLD_NEXT, "mCoreThreadStart");
    if (!start) _exit(74);
    const char *marker = getenv("ENTRY_NATIVE_START_GATE");
    if (owner && marker) {
        if (!*marker || access(marker, F_OK) == 0) _exit(74);
        startup_thread = context;
        startup_marker = marker;
        atomic_store(&startup_blocked, true);
        saved_reset_callback = context->resetCallback;
        context->resetCallback = startup_reset;
    }
    bool ok = start(context);
    const char *delay = getenv("ENTRY_NATIVE_START_DELAY_US");
    if (!delay) delay = getenv("PENTA_NATIVE_AV_START_DELAY_US");
    if (ok && owner && delay) {
        char *end;
        unsigned long value = strtoul(delay, &end, 10);
        if (!*delay || *end || value > 10000) _exit(74);
        usleep(value);
    }
    return ok;
}

/* The probe terminates from mGBA's CPU thread. libc exit() starts Qt global
 * destruction while its GUI/painter threads are still running (verified GDB
 * trace in issue #16). Finalize this recorder synchronously, then terminate
 * the entire diagnostic process without racing Qt destructors. No emulated
 * frame/audio is added, and all probe receipts are already closed by Lua. */
__attribute__((noreturn)) void exit(int status) {
    if (pcm) {
        finish();
        _exit(status);
    }
    void (*real_exit)(int) = dlsym(RTLD_NEXT, "exit");
    if (real_exit) real_exit(status);
    _exit(status);
}

static void die(const char *message) {
    fprintf(stderr, "native AV tap: %s (errno=%d)\n", message, errno);
    _exit(74);
}

static FILE *open_output(const char *prefix, const char *suffix) {
    char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s%s", prefix, suffix) >= (int)sizeof(path))
        die("output path too long");
    FILE *file = fopen(path, "wbx");
    if (!file) die("cannot exclusively create output");
    return file;
}

static void write_bytes(FILE *file, const void *data, size_t size) {
    if (fwrite(data, 1, size, file) != size) die("incomplete capture write");
}

static void dimensions(struct mAVStream *self, unsigned w, unsigned h) {
    (void)self;
    width = w; height = h;
    /* Before ROM load the frontend may announce an uninitialized size.
     * Only actual delivered frames must satisfy the native GB dimensions. */
    if (downstream && downstream->videoDimensionsChanged)
        downstream->videoDimensionsChanged(downstream, w, h);
}

static void audio_rate(struct mAVStream *self, unsigned value) {
    (void)self;
    if (rate && rate != value) die("sample rate changed during capture");
    rate = value;
    if (downstream && downstream->audioRateChanged)
        downstream->audioRateChanged(downstream, value);
}

static void sample(struct mAVStream *self, int16_t left, int16_t right) {
    (void)self;
    const unsigned char bytes[4] = {
        (uint16_t)left & 255, (uint16_t)left >> 8,
        (uint16_t)right & 255, (uint16_t)right >> 8
    };
    write_bytes(pcm, bytes, sizeof(bytes));
    ++samples;
    if (downstream && downstream->postAudioFrame)
        downstream->postAudioFrame(downstream, left, right);
}

static void audio_buffer(struct mAVStream *self, struct mAudioBuffer *buffer) {
    (void)self;
    /* Never drain or resample the frontend's audio buffer. */
    if (downstream && downstream->postAudioBuffer)
        downstream->postAudioBuffer(downstream, buffer);
}

static void frame(struct mAVStream *self, const mColor *pixels, size_t stride) {
    (void)self;
    owner->currentVideoSize(owner, &width, &height);
    if (width != 160 || height != 144 || stride < width)
        die("unsupported delivered frame dimensions");
    for (unsigned y = 0; y < height; ++y)
        write_bytes(video, pixels + y * stride, width * sizeof(mColor));
    if (!state_buffer) {
        state_size = owner->stateSize(owner);
        state_buffer = calloc(1, state_size);
        if (!state_buffer || !state_size) die("state buffer allocation failed");
    }
    memset(state_buffer, 0, state_size);
    if (!owner->saveState(owner, state_buffer)) die("state capture failed");
    write_bytes(states, state_buffer, state_size);
    if (fprintf(timeline, "%" PRIu64 "\t%u\t%" PRIu64 "\t%u\n",
                frames, owner->frameCounter(owner), samples, owner->getKeys(owner)) < 0)
        die("timeline write failed");
    ++frames;
    if (downstream && downstream->postVideoFrame)
        downstream->postVideoFrame(downstream, pixels, stride);
}

static void set_stream(struct mCore *core, struct mAVStream *stream) {
    if (core != owner || stream == &tap) die("unexpected stream owner");
    downstream = stream;
    real_set_stream(core, &tap);
}

/* #43: retain capture epochs rather than silently treating pre-restore audio
 * as part of the replay. This observes boundaries only; no samples are cut. */
static bool load_state(struct mCore *core, const void *state) {
    if (fprintf(lifecycle, "load_begin\t%u\t%" PRIu64 "\t%" PRIu64 "\t-1\n",
                core->frameCounter(core), frames, samples) < 0)
        die("lifecycle write failed");
    bool ok = real_load_state(core, state);
    restored = ok;
    if (fprintf(lifecycle, "load_end\t%u\t%" PRIu64 "\t%" PRIu64 "\t%d\n",
                core->frameCounter(core), frames, samples, ok) < 0 || fflush(lifecycle))
        die("lifecycle write failed");
    return ok;
}

static bool initialize(struct mCore *core) {
    if (!real_init(core)) return false;
    const char *prefix = getenv("PENTA_NATIVE_AV_PREFIX");
    pcm = open_output(prefix, ".s16le");
    video = open_output(prefix, ".video");
    states = open_output(prefix, ".states");
    timeline = open_output(prefix, ".timeline.tsv");
    lifecycle = open_output(prefix, ".lifecycle.tsv");
    fputs("event\temulator_frame\tvideo_frames\tpcm_samples\tsuccess\n", lifecycle);
    fputs("sample\temulator_frame\tpcm_samples\tkeys\n", timeline);
    tap = (struct mAVStream){dimensions, audio_rate, frame, sample, audio_buffer};
    set_stream(core, NULL);
    return true;
}

struct mCore *GBCoreCreate(void) {
    struct mCore *(*create)(void) = dlsym(RTLD_NEXT, "GBCoreCreate");
    if (!create) die("GBCoreCreate lookup failed");
    struct mCore *core = create();
    if (!getenv("PENTA_NATIVE_AV_PREFIX")) return core;
    if (!getenv("PENTA_MGBA_SINGLEFLIGHT")) die("single-flight guard required");
    if (owner || !core) die("multiple/missing GB cores are unsupported");
    owner = core;
    real_init = core->init;
    real_set_stream = core->setAVStream;
    real_load_state = core->loadState;
    real_run_loop = core->runLoop;
    real_step = core->step;
    core->runLoop = gated_run_loop;
    core->step = gated_step;
    core->init = initialize;
    core->setAVStream = set_stream;
    core->loadState = load_state;
    return core;
}

__attribute__((destructor)) static void finish(void) {
    if (!pcm) return;
    if (fclose(pcm) || fclose(video) || fclose(states) || fclose(timeline) || fclose(lifecycle))
        die("capture close failed");
    pcm = NULL;
    FILE *meta = open_output(getenv("PENTA_NATIVE_AV_PREFIX"), ".meta.json");
    fprintf(meta, "{\"sample_rate\":%u,\"channels\":2,\"sample_bytes\":2,"
                 "\"samples\":%" PRIu64 ",\"frames\":%" PRIu64 ","
                 "\"width\":%u,\"height\":%u,\"pixel_bytes\":%zu,"
                 "\"state_bytes\":%zu}\n",
            rate, samples, frames, width, height, sizeof(mColor), state_size);
    if (fclose(meta)) die("metadata close failed");
    free(state_buffer);
}
