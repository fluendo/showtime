# H.266 DSC Verification Integration in Showtime

## Implementation Summary

I've implemented **Solution 3: autoplug-select signal** to integrate `dscverifier` into Showtime's playback pipeline.

### What Was Changed

**File: `/home/dnieto/Projects/showtime/showtime/play.py`**

Added signal handlers to intercept GstPlay's internal playbin3 element creation:

1. **`on_autoplug_select`**: Intercepts when playbin3 tries to auto-plug an H.266 decoder
   - Detects H.266 decoders: `avdec_h266`, `vvcdec`, `h266dec`
   - Returns `SKIP` to prevent auto-plugging, so we can insert our custom chain

2. **`on_deep_element_added`**: Monitors when elements are added to internal bins
   - Finds `parsebin`, `decodebin3`, or `uridecodebin3` elements
   - Connects to their `pad-added` signal

3. **`on_pad_added`** (inside deep-element-added): Inserts verification chain
   - Detects `video/x-h266` caps on pads
   - Creates custom bin with: `dscverifier` → `avdec_h266`
   - Configures dscverifier with keystore path
   - Links the H.266 stream through the verification chain

## How It Works

```
GstPlay.Play
  └─> playbin3
        └─> uridecodebin3
              └─> parsebin
                    └─> h266parse (auto-created)
                          └─> [OUR HOOK HERE]
                                └─> dscverifier (we insert)
                                      └─> avdec_h266 (we control)
                                            └─> videoconvert
                                                  └─> video-filter (existing)
                                                        └─> gtk4paintablesink
```

## Testing

### Method 1: Rebuild and Run Flatpak (Recommended)

```bash
cd /home/dnieto/Projects/showtime

# Rebuild the flatpak with our changes
flatpak-builder --force-clean --install --user build-dir \
  build-aux/flatpak/org.gnome.Showtime.Devel.json

# Run with debug output
GST_DEBUG="3,dscverifier:7,h266parse:5" \
  flatpak run org.gnome.Showtime.Devel \
  /home/dnieto/workspace/VVCSoftware_VTM/bin/str.bin
```

### Method 2: Run Inside Flatpak Shell

```bash
# Enter flatpak environment
flatpak-builder --run build-dir \
  build-aux/flatpak/org.gnome.Showtime.Devel.json \
  /bin/bash

# Then inside the shell:
GST_DEBUG="3,dscverifier:7,h266parse:5" showtime str.bin
```

### Expected Debug Output

You should see messages like:
```
[INIT] Connected autoplug signals to pipeline: playbin3
[AUTOPLUG] Factory: avdec_h266, Caps: video/x-h266...
[AUTOPLUG] Found H.266 decoder: avdec_h266
[DEEP-ELEMENT] Added: parsebin...
[PAD-ADDED] Pad: src_0, Caps: video/x-h266
[PAD-ADDED] H.266 stream detected! Inserting dscverifier...
[SUCCESS] Linked H.266 stream to dscverifier chain!
0:00:01.234 dscverifier: Verifying signature...
0:00:01.235 dscverifier: Signature valid!
```

## Alternative Solutions (If This Doesn't Work)

### Fallback 1: Use `deep-element-added` More Aggressively

If `autoplug-select` doesn't fire, we can modify the `on_deep_element_added` to intercept the decoder element directly after it's created and insert verifier before it.

### Fallback 2: Custom Decoder Element

Create a GStreamer element that wraps h266parse+dscverifier+decoder as a single "decoder" element that playbin will use automatically.

### Fallback 3: Manual Pipeline

Replace `GstPlay.Play` with a manual pipeline construction, giving full control over element ordering.

## Current State

✅ Code implemented in `play.py`
✅ Signal handlers connected
✅ Debug logging added
⏳ Needs testing with proper GStreamer environment (flatpak)

## Next Steps

1. Rebuild showtime flatpak to include the changes
2. Ensure dscverifier plugin is available in the flatpak (may need to add to manifest)
3. Test with H.266 file
4. Monitor debug output
5. If signals don't fire, implement Fallback 1

## Notes

- The flatpak may need the `dscverifier` plugin added to its manifest
- Check `build-aux/flatpak/org.gnome.Showtime.Devel.json` to add gst-plugins-rs
- Keystore path is hardcoded: `/home/dnieto/workspace/VVCSoftware_VTM/cfg/keystore/public/`
  - This path won't exist in flatpak! Need to mount or change path

## Flatpak Plugin Integration

To include dscverifier in the flatpak, add to the JSON manifest:

```json
{
  "name": "gst-plugins-rs-dsc",
  "buildsystem": "simple",
  "build-commands": [
    "install -Dm755 /home/dnieto/workspace/gst-plugins-rs/target/debug/libgstdsc.so /app/lib/gstreamer-1.0/"
  ]
}
```

Or build gst-plugins-rs inside the flatpak properly with cargo.
