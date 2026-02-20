# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Copyright 2024-2025 kramo

from typing import Any

from gi.repository import (
    Gdk,
    GObject,
    Gst,
    GstPbutils,
    GstPlay,  # pyright: ignore[reportAttributeAccessIssue]
    Gtk,
)

from showtime import system, utils


def gst_play_setup(
    picture: Gtk.Picture,
) -> tuple[Gdk.Paintable, GstPlay.Play, Gst.Element, Gst.Element]:
    """Set up `GstPlay`."""
    sink = paintable_sink = Gst.ElementFactory.make("gtk4paintablesink")
    if not paintable_sink:
        msg = "Cannot make gtk4paintablesink"
        raise RuntimeError(msg)

    paintable = paintable_sink.props.paintable
    picture.props.paintable = paintable

    # OpenGL doesn't work on macOS properly
    if paintable.props.gl_context and system != "Darwin":
        gl_sink = Gst.ElementFactory.make("glsinkbin")
        gl_sink.props.sink = paintable_sink
        sink = gl_sink

    play = GstPlay.Play(
        video_renderer=GstPlay.PlayVideoOverlayVideoRenderer.new_with_sink(None, sink)
    )
    
    pipeline = play.props.pipeline
    
    verifier_state = {"verifier_added": False, "chain_bin": None}
    
    def on_autoplug_select(playbin, pad, caps, factory):
        """Intercept decoder auto-selection to insert dscverifier for H.266"""
        factory_name = factory.get_name()
        
        print(f"[AUTOPLUG] Factory: {factory_name}, Caps: {caps.to_string()[:80]}")
        
        if factory_name == "h266parse":
            caps_str = caps.to_string()
            if "video/x-h266" in caps_str and "byte-stream" in caps_str:
                print(f"[AUTOPLUG] Allowing h266parse to run for AU alignment")
                return 0
        
        if factory_name in ["avdec_h266", "vvcdec", "h266dec"]:
            caps_str = caps.to_string()
            if "video/x-h266" in caps_str:
                print(f"[AUTOPLUG] Found H.266 decoder: {factory_name} - SKIPPING")
                return 2
        
        return 0
    
    def on_deep_element_added(playbin, sub_bin, element):
        """Called when elements are added to internal bins"""
        factory = element.get_factory()
        factory_name = factory.get_name() if factory else "unknown"
        element_name = element.get_name()
        
        print(f"[DEEP-ELEMENT] Added: {element_name} ({factory_name}) to {sub_bin.get_name()}")
        
        # Look for parsebin or decodebin3 where we can intercept
        if factory_name in ["parsebin", "decodebin3", "uridecodebin3"]:
            print(f"[DEEP-ELEMENT] Found decode element: {factory_name}")
            
            # Store reference to this decode element for the pad-added callback
            element_ref = element
            
            def on_pad_added(decode_element, pad):
                """Intercept pads as they're created by decodebin"""
                caps = pad.get_current_caps()
                if not caps:
                    caps = pad.query_caps(None)
                
                if not caps or caps.is_empty():
                    return
                
                structure = caps.get_structure(0)
                caps_name = structure.get_name()
                
                print(f"[PAD-ADDED] Pad: {pad.get_name()}, Caps: {caps_name}")
                
                # Check for H.266 video stream
                if caps_name == "video/x-h266" and not verifier_state["verifier_added"]:
                    print("[PAD-ADDED] H.266 stream detected! Inserting dscverifier...")
                    
                    # Check the stream format and alignment
                    stream_format = structure.get_string("stream-format")
                    alignment = structure.get_string("alignment")
                    print(f"[DEBUG] Stream format: {stream_format}, alignment: {alignment}")
                    
                    
                    parser_pre = Gst.ElementFactory.make("h266parse", "h266-parse-pre-verify")
                    verifier = Gst.ElementFactory.make("dscverifier", "h266-verifier")
                    decoder = Gst.ElementFactory.make("avdec_h266", "h266-decoder")
                    
                    if not parser_pre:
                        print("[ERROR] Could not create h266parse element!")
                        return
                    
                    if not verifier:
                        print("[ERROR] Could not create dscverifier element!")
                        return
                    
                    if not decoder:
                        print("[ERROR] Could not create H.266 decoder!")
                        return
                    
                    key_store_path = os.getenv("DSC_KEY_STORE_PATH", 
                        "/tmp/dsc/keystore/pub/")
                    verifier.set_property("key-store-path", key_store_path)
                    
                    parent_bin = element_ref.get_parent()
                    
                    print(f"[DEBUG] Decode element: {element_ref.get_name()}")
                    print(f"[DEBUG] Decode element parent: {parent_bin.get_name() if parent_bin else 'None'}")
                    
                    if not parent_bin or not isinstance(parent_bin, Gst.Bin):
                        print("[ERROR] Cannot find valid parent bin")
                        return
                    
                    parent_bin.add(parser_pre)
                    parent_bin.add(verifier)
                    parent_bin.add(decoder)
                    
                    print(f"[DEBUG] Added parser, verifier and decoder to {parent_bin.get_name()}")
                    
                    # Set elements to NULL state first
                    parser_pre.set_state(Gst.State.NULL)
                    verifier.set_state(Gst.State.NULL)
                    decoder.set_state(Gst.State.NULL)
                    
                    # Link: parser_pre -> verifier -> decoder
                    if not parser_pre.link(verifier):
                        print("[ERROR] Failed to link parser -> verifier")
                        parent_bin.remove(parser_pre)
                        parent_bin.remove(verifier)
                        parent_bin.remove(decoder)
                        return
                    
                    if not verifier.link(decoder):
                        print("[ERROR] Failed to link verifier -> decoder")
                        parent_bin.remove(parser_pre)
                        parent_bin.remove(verifier)
                        parent_bin.remove(decoder)
                        return
                    
                    # Now sync states
                    parser_pre.sync_state_with_parent()
                    verifier.sync_state_with_parent()
                    decoder.sync_state_with_parent()
                    
                    print("[DEBUG] Elements synced to parent state")
                    
                    # Add buffer probes to debug data flow
                    def verifier_probe(pad, info):
                        print(f"[PROBE] Buffer passing through verifier")
                        return Gst.PadProbeReturn.OK
                    
                    def decoder_probe(pad, info):
                        print(f"[PROBE] Buffer passing through decoder input")
                        return Gst.PadProbeReturn.OK
                    
                    # verifier_src = verifier.get_static_pad("src")
                    # if verifier_src:
                    #     verifier_src.add_probe(Gst.PadProbeType.BUFFER, verifier_probe)
                    #     print("[DEBUG] Added probe to verifier src pad")
                    
                    # decoder_sink = decoder.get_static_pad("sink")
                    # if decoder_sink:
                    #     decoder_sink.add_probe(Gst.PadProbeType.BUFFER, decoder_probe)
                    #     print("[DEBUG] Added probe to decoder sink pad")
                    
                    # Link parsebin pad to parser_pre (will convert vvc1 → byte-stream)
                    parser_sink = parser_pre.get_static_pad("sink")
                    link_result = pad.link(parser_sink)
                    
                    print(f"[LINK] Pad link result: {link_result} ({link_result.value_nick})")
                    
                    if link_result == Gst.PadLinkReturn.OK:
                        print("[SUCCESS] Linked H.266 stream to parser_pre → dscverifier chain!")
                        verifier_state["verifier_added"] = True
                        verifier_state["parser_pre"] = parser_pre
                        verifier_state["verifier"] = verifier
                        verifier_state["decoder"] = decoder
                        
                        def on_decoder_pad_added(dec, dec_pad):
                            print(f"[DECODER] Decoder created pad: {dec_pad.get_name()}, caps: {dec_pad.get_current_caps()}")
                            ghost_pad = Gst.GhostPad.new(f"decoded_src_{dec_pad.get_name()}", dec_pad)
                            ghost_pad.set_active(True)
                            parent_bin.add_pad(ghost_pad)
                            print(f"[DECODER] Added ghost pad to expose decoder output")
                        
                        decoder.connect("pad-added", on_decoder_pad_added)
                        
                        decoder_src = decoder.get_static_pad("src")
                        if decoder_src:
                            print(f"[DECODER] Decoder already has src pad, exposing it")
                            ghost_pad = Gst.GhostPad.new("decoded_src", decoder_src)
                            ghost_pad.set_active(True)
                            parent_bin.add_pad(ghost_pad)
                        
                    else:
                        print(f"[ERROR] Failed to link pad to parser_pre: {link_result.value_nick}")
                        pad.unlink(parser_sink)
                        parser_pre.unlink(verifier)
                        verifier.unlink(decoder)
                        parser_pre.set_state(Gst.State.NULL)
                        verifier.set_state(Gst.State.NULL)
                        decoder.set_state(Gst.State.NULL)
                        parent_bin.remove(parser_pre)
                        parent_bin.remove(verifier)
                        parent_bin.remove(decoder)
                        parent_bin.remove(verifier)
                        parent_bin.remove(decoder)
            
            element.connect("pad-added", on_pad_added)
            
            # Try to connect autoplug-select if this element supports it
            try:
                element.connect("autoplug-select", on_autoplug_select)
                print(f"[DEEP-ELEMENT] Connected autoplug-select to {factory_name}")
            except TypeError:
                # Element doesn't have autoplug-select signal, that's ok
                print(f"[DEEP-ELEMENT] No autoplug-select signal on {factory_name}")
    
    # Track DSC verification state
    verification_status = {"verified": False, "has_dsc": False}
    
    pipeline.connect("deep-element-added", on_deep_element_added)
    
    print(f"[INIT] Connected signals to pipeline: {pipeline.get_name()}")
    
    # Listen for DSC verification messages on the pipeline bus
    def on_pipeline_message(bus, message):
        """Handle messages from the pipeline, including DSC verification results"""
        if message.type == Gst.MessageType.ELEMENT:
            structure = message.get_structure()
            if structure and structure.get_name() == "dsc-verification-result":
                verified = structure.get_boolean("verified")[1]
                verification_status["verified"] = verified
                verification_status["has_dsc"] = True
                
                if verified:
                    print("[DSC-VERIFICATION] ✅ Stream signature verified successfully!")
                else:
                    print("[DSC-VERIFICATION] ❌ Stream signature verification FAILED!")
                
                # Notify the picture widget so it can update the UI
                if hasattr(picture, 'verification_status_changed'):
                    picture.verification_status_changed(verified)
        
        return True
    
    # Connect to pipeline bus to receive DSC verification messages
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", on_pipeline_message)

    video_filter_bin = Gst.Bin.new("video-filter-bin")
    # videobalance = Gst.ElementFactory.make("rsidentity")
    videobalance = Gst.ElementFactory.make("identity")
    # videobalance.set_property("sleep-time", 450000)
    videoflip = Gst.ElementFactory.make("videoflip")
    
    video_filter_bin.add(videobalance)
    video_filter_bin.add(videoflip)
    videobalance.link(videoflip)
    
    sink_pad = videobalance.get_static_pad("sink")
    video_filter_bin.add_pad(Gst.GhostPad.new("sink", sink_pad))
    src_pad = videoflip.get_static_pad("src")
    video_filter_bin.add_pad(Gst.GhostPad.new("src", src_pad))
    
    pipeline.set_property("video-filter", video_filter_bin)

    def set_subtitle_font_desc(*_args: Any) -> None:
        pipeline.props.subtitle_font_desc = utils.get_subtitle_font_desc()

    if settings := Gtk.Settings.get_default():
        settings.connect("notify::gtk-xft-dpi", set_subtitle_font_desc)

    set_subtitle_font_desc()

    return paintable, play, pipeline, paintable_sink, verification_status


class Messenger(GObject.Object):
    """A messenger between GStreamer and the app."""

    __gtype_name__ = "Messenger"

    state_changed = GObject.Signal(name="state-changed", arg_types=(object,))
    duration_changed = GObject.Signal(name="duration-changed", arg_types=(object,))
    position_updated = GObject.Signal(name="position-updated", arg_types=(object,))
    seek_done = GObject.Signal(name="seek-done")
    media_info_updated = GObject.Signal(name="media-info-updated", arg_types=(object,))
    volume_changed = GObject.Signal(name="volume-changed")
    end_of_stream = GObject.Signal(name="end-of-stream")
    warning = GObject.Signal(name="warning", arg_types=(object,))
    error = GObject.Signal(name="error", arg_types=(object,))
    missing_plugin = GObject.Signal(name="missing-plugin", arg_types=(object,))

    def __init__(
        self,
        play: GstPlay.Play,
        pipeline: Gst.Element,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if bus := play.get_message_bus():
            bus.add_signal_watch()
            bus.connect("message", self._on_play_bus_message)

        if bus := pipeline.get_bus():
            bus.add_signal_watch()
            bus.connect("message", self._on_pipeline_bus_message)

    def _on_play_bus_message(self, _bus: Gst.Bus, msg: GstPlay.PlayMessage) -> None:
        #print(msg)
        match GstPlay.PlayMessage.parse_type(msg):
            case GstPlay.PlayMessage.STATE_CHANGED:
                self.emit(
                    "state-changed",
                    GstPlay.PlayMessage.parse_state_changed(msg),
                )

            case GstPlay.PlayMessage.DURATION_CHANGED:
                self.emit(
                    "duration-changed",
                    GstPlay.PlayMessage.parse_duration_changed(msg),
                )

            case GstPlay.PlayMessage.POSITION_UPDATED:
                self.emit(
                    "position-updated",
                    GstPlay.PlayMessage.parse_position_updated(msg),
                )

            case GstPlay.PlayMessage.SEEK_DONE:
                self.emit("seek-done")

            case GstPlay.PlayMessage.MEDIA_INFO_UPDATED:
                self.emit(
                    "media-info-updated",
                    GstPlay.PlayMessage.parse_media_info_updated(msg),
                )

            case GstPlay.PlayMessage.VOLUME_CHANGED:
                self.emit("volume-changed")

            case GstPlay.PlayMessage.END_OF_STREAM:
                self.emit("end-of-stream")

            case GstPlay.PlayMessage.WARNING:
                self.emit("warning", GstPlay.PlayMessage.parse_warning(msg))

            case GstPlay.PlayMessage.ERROR:
                error, _details = GstPlay.PlayMessage.parse_error(msg)
                self.emit("error", error)

    def _on_pipeline_bus_message(self, _bus: Gst.Bus, msg: Gst.Message) -> None:
        #print('Message: ' + str(msg))
        if GstPbutils.is_missing_plugin_message(msg):
            self.emit("missing-plugin", msg)
