"""English half of the block help; the Russian half lives in block_help.py.

The two are a pair: block_help._table() picks one of them by language and
merges it into the catalog, so this module must expose exactly the same keys
as its Russian twin -- every block type, every field, and every entry in
SHARED. block_help.missing("en") walks both tables and reports whatever this
one has not filled in, so a half-finished translation surfaces as a test
failure instead of as blank tooltips in the UI.

Nothing outside these two dicts needs touching to change the wording.
"""

# type -> {"desc": str, "fields": {key: str}}
HELP = {
    # ------------------------------------------------------------- mouse
    "click": {
        "desc": "Clicks the mouse at a point. Coordinates are relative to the "
                "target window (or to the screen, when the target is the whole "
                "screen). The Pick button captures a coordinate from your next "
                "click.",
        "fields": {
            "x": "Horizontal coordinate, from the left edge of the target window.",
            "y": "Vertical coordinate, from the top edge of the target window.",
            "button": "Which mouse button to press.",
            "clicks": "How many clicks in a row. 2 is a double-click.",
            "hold_ms": "How long to keep the button down. Some applications "
                       "ignore clicks that are too quick.",
        },
    },
    "move": {
        "desc": "Moves the cursor without clicking. Needed when the target "
                "reacts to hover -- tooltips, buttons that light up.",
        "fields": {
            "x": "Horizontal coordinate to land on.",
            "y": "Vertical coordinate to land on.",
            "duration_ms": "0 is an instant jump. Anything above zero glides "
                           "over that time; it looks more natural and triggers "
                           "hover effects more reliably.",
        },
    },
    "drag": {
        "desc": "Presses a button, drags the cursor to another point and "
                "releases. For sliders, moving items around, selecting.",
        "fields": {
            "x": "Where to start -- horizontal.",
            "y": "Where to start -- vertical.",
            "x2": "Where to end up -- horizontal.",
            "y2": "Where to end up -- vertical.",
            "button": "Which button to drag with.",
            "duration_ms": "How long the trip takes. Many applications never "
                           "notice a drag that happens too fast.",
        },
    },
    "scroll": {
        "desc": "Turns the mouse wheel. If coordinates are given the cursor "
                "moves there first -- scrolling happens under the cursor.",
        "fields": {
            "amount": "One wheel notch = 120. Negative scrolls down, positive "
                      "scrolls up.",
            "x": "Where to put the cursor before scrolling.",
            "y": "Where to put the cursor before scrolling.",
        },
    },

    # ---------------------------------------------------------- keyboard
    "send_key": {
        "desc": "Presses and releases one key. What gets sent is the physical "
                "key position, so it works on any keyboard layout.",
        "fields": {
            "key": "Click the field, then press the key you want -- it gets "
                   "recorded.",
            "hold_ms": "How long to hold it. Games sometimes need 50-100 ms; "
                       "an instant tap may not register at all.",
            "modifiers": "Modifiers held down together with the key. "
                         "Ctrl + C, Shift + Tab and the like.",
        },
    },
    "type_text": {
        "desc": "Types text verbatim, as Unicode. The layout does not matter: "
                "\"Привет\" comes out as \"Привет\" even on an English one.",
        "fields": {
            "text": "What to type. A line break is Enter, a tab is Tab.",
            "delay_ms": "Pause between characters. Zero is instant, but some "
                        "applications drop characters when typed that fast.",
        },
    },
    "hold_key": {
        "desc": "Holds a key down for a set time and releases it. For walking "
                "in games, sprinting, holding aim. Stop interrupts the hold and "
                "releases the key.",
        "fields": {
            "key": "Click the field, then press the key you want.",
            "hold_ms": "How long to keep it held down.",
        },
    },

    # ------------------------------------------------------------ timing
    "wait_ms": {
        "desc": "Simply waits. Stop lands inside the wait rather than after "
                "it -- even a long pause is cut short immediately.",
        "fields": {"ms": "How many milliseconds to wait. 1000 = 1 second."},
    },
    "wait_random": {
        "desc": "Waits a random time inside a range. Makes the rhythm less "
                "machine-like than a fixed pause.",
        "fields": {
            "min_ms": "Shortest the pause can be.",
            "max_ms": "Longest the pause can be.",
        },
    },

    # ------------------------------------------------------------ vision
    "wait_image": {
        "desc": "Waits until an image shows up on screen. This is how a macro "
                "adapts to how fast the application actually is, instead of "
                "guessing at pauses. Images are captured on the Images tab.",
        "fields": {
            "template": "Name of a saved image. The + button opens the image "
                        "manager.",
            "timeout_ms": "How long to wait at most. 0 checks once and does "
                          "not wait.",
            "threshold": "Match threshold, 0-1. Lower is more forgiving of "
                         "differences, but the risk of a false match grows. "
                         "0.88 is a sensible starting point.",
            "region": "Search only inside this rectangle. Speeds the search up "
                      "a lot and rules out false hits elsewhere.",
            "on_fail": "What to do if the image never showed up: carry on, "
                       "abandon the remaining blocks of this pass, or stop the "
                       "macro.",
        },
    },
    "click_image": {
        "desc": "Waits for an image and clicks its centre. Works even when the "
                "button lands somewhere different every time -- no coordinates "
                "needed.",
        "fields": {
            "template": "Name of a saved image. The + button opens the image "
                        "manager.",
            "timeout_ms": "How long to wait for it to appear. 0 checks once "
                          "and does not wait.",
            "threshold": "Match threshold, 0-1. Lower is more forgiving of "
                         "differences, but the risk of clicking the wrong "
                         "thing grows.",
            "region": "Search only inside this rectangle. Speeds the search up "
                      "and rules out false hits.",
            "button": "Which button to click the match with.",
            "offset_x": "Shifts the click right of the image centre. Useful "
                        "when the label is what can be recognised but the thing "
                        "to press sits next to it.",
            "offset_y": "Shifts the click down from the image centre.",
            "on_fail": "What to do if the image is not found: carry on, "
                       "abandon the remaining blocks of this pass, or stop the "
                       "macro.",
        },
    },
    "wait_image_gone": {
        "desc": "Waits until an image DISAPPEARS. For loading screens, "
                "spinners, popups -- \"wait until it goes away\".",
        "fields": {
            "template": "Name of a saved image.",
            "timeout_ms": "How long to wait for it to go away.",
            "threshold": "Match threshold, 0-1. The same threshold that "
                         "decides whether the image counts as present.",
            "region": "Search only inside this rectangle.",
            "on_fail": "What to do if the image is still on screen: carry on, "
                       "abandon the remaining blocks of this pass, or stop the "
                       "macro.",
        },
    },
    "wait_color": {
        "desc": "Waits until the pixel at a point turns a given colour. "
                "Cheaper than an image search -- good for indicators, health "
                "bars, highlights.",
        "fields": {
            "x": "Horizontal coordinate of the pixel.",
            "y": "Vertical coordinate of the pixel.",
            "color": "The colour to wait for. Pick takes the colour from your "
                     "next click.",
            "confidence": "How closely the colour has to match, 0-1, applied "
                          "as a tolerance on each channel. 1.0 is pixel-exact; "
                          "0.92 survives anti-aliasing and a slight gradient; "
                          "below 0.8 it starts catching unrelated shades.",
            "timeout_ms": "How long to wait at most.",
            "on_fail": "What to do if the colour never appeared.",
        },
    },
    "click_color": {
        "desc": "Finds the largest blob of a given colour and clicks its "
                "centre. Cheaper than an image search and survives a change of "
                "shape: a highlighted tile, a coloured button at a different "
                "size.",
        "fields": {
            "color": "Which colour to look for. Pick takes the colour from "
                     "your next click.",
            "confidence": "How closely the colour has to match, 0-1, applied "
                          "as a tolerance on each channel. 1.0 is pixel-exact; "
                          "0.90 survives gradients and softened edges; lower "
                          "starts pulling unrelated shades into the same blob.",
            "min_pixels": "Blobs smaller than this are ignored. Filters out "
                          "stray pixels of a similar shade.",
            "region": "Search only inside this rectangle.",
            "timeout_ms": "How long to wait for the colour to appear.",
            "button": "Which button to click with.",
            "offset_x": "Shifts the click right of the blob centre.",
            "offset_y": "Shifts the click down from the blob centre.",
            "on_fail": "What to do if the colour is not found: carry on, "
                       "abandon the remaining blocks of this pass, or stop the "
                       "macro.",
        },
    },
    "wait_text": {
        "desc": "Reads the text in a region and waits for the string you want. "
                "Uses the OCR built into Windows. Slower than an image search, "
                "but it survives a change of font or background.",
        "fields": {
            "text": "Which string to wait for.",
            "region": "Where to read. The smaller the area, the faster and the "
                      "more accurate.",
            "timeout_ms": "How long to wait at most.",
            "confidence": "How close the recognised text has to be, 0-1. If "
                          "your string is found literally it always counts. "
                          "The threshold only comes into play when there is no "
                          "literal match: OCR regularly confuses a Latin C with "
                          "a Cyrillic С, or drops a letter.",
            "match": "contains -- the string turns up somewhere inside, with "
                     "Confidence as the allowance for OCR slips; exact -- the "
                     "recognised text matches in full and literally.",
            "on_fail": "What to do if the text is not found.",
        },
    },
    "click_text": {
        "desc": "Finds text on screen and clicks it. No coordinates needed -- "
                "the button can be anywhere as long as the label is readable. "
                "The most robust option when the interface moves its elements "
                "around.",
        "fields": {
            "text": "Which label to find and press.",
            "region": "Search only inside this rectangle. Much faster, and it "
                      "rules out matches elsewhere on screen.",
            "timeout_ms": "How long to wait for the text to appear.",
            "confidence": "How close the recognised text has to be, 0-1. A "
                          "literal match always counts; the threshold only "
                          "matters when OCR got a couple of letters wrong. "
                          "Lower is more forgiving, but the risk of pressing "
                          "the wrong label grows. 0.75 is a sensible start.",
            "button": "Which button to click with.",
            "offset_x": "Shifts the click right of the label centre.",
            "offset_y": "Shifts the click down from the label centre.",
            "on_fail": "What to do if the text is not found: carry on, abandon "
                       "the remaining blocks of this pass, or stop the macro.",
        },
    },
    "read_text": {
        "desc": "Reads the text in a region and writes it to the log. Waits "
                "for nothing and affects nothing -- it is there to help you "
                "dial in a region and check what OCR actually sees.",
        "fields": {"region": "Which area to read."},
    },

    # -------------------------------------------------------------- flow
    "loop_start": {
        "desc": "Start of a repeated stretch. Everything between this block "
                "and Loop End runs the given number of times. Nesting works.",
        "fields": {"count": "How many times to repeat the stretch."},
    },
    "loop_end": {
        "desc": "End of the repeated stretch opened by a Loop Start block.",
        "fields": {},
    },
    "playback": {
        "desc": "Plays a saved recording as-is, at its own timing. Unlike a "
                "recording that has been broken up into blocks, this keeps the "
                "exact rhythm -- useful for camera drags and any sequence that "
                "is sensitive to timing.",
        "fields": {
            "recording": "Which saved recording to play. Recordings are made "
                         "on the Record tab.",
            "speed": "Speed multiplier. 2 is twice as fast, 0.5 is half speed.",
        },
    },
    "focus_window": {
        "desc": "Brings the target window to the front and, if asked, puts it "
                "at a set size and position.\n\n"
                "Put this in Setup: a macro recorded at one window size will "
                "miss at another, and this block guarantees the window is the "
                "same every time.",
        "fields": {
            "resize": "Whether to resize the window at all.",
            "width": "Width of the client area -- the one every coordinate "
                     "in the macro is measured against. The border and title "
                     "bar are added on top automatically.",
            "height": "Height of the client area.",
            "move": "Whether to move the window to a given point on screen.",
            "x": "Where to put the left edge of the window.",
            "y": "Where to put the top edge of the window.",
        },
    },
    "log": {
        "desc": "Writes a line to the journal at the bottom. Affects nothing "
                "-- it helps you see how far the macro got.",
        "fields": {"text": "What to write to the journal."},
    },

    # ------------------------------------------------------------ notify
    "send_webhook": {
        "desc": "Sends a message to Discord and, if you want, attaches a "
                "screenshot. The webhook address is set once on the Setup tab "
                "-- it is not in the block itself, so the macro can be handed "
                "to someone else without giving away the link.\n\n"
                "Nothing is sent while the webhook is switched off in Settings.",
        "fields": {
            "message": "The message text. Up to 2000 characters.",
            "source": "What to attach as a picture:\n"
                      "• none — text only;\n"
                      "• target window — a shot of the target window;\n"
                      "• whole screen — the whole screen;\n"
                      "• region — a given rectangle;\n"
                      "• saved image — a picture from Assets.",
            "region": "Which area to capture. Only for the region mode.",
            "template": "Which saved image to attach. Only for the saved image "
                        "mode.",
        },
    },
}


# Fields shared by every Vision block. Defined once here rather than repeated
# in each entry above, and used as the fallback when a block does not spell
# them out itself.
SHARED = {
    "on_fail": "What to do when the block did not find what it was looking "
               "for:\n"
               "• continue — just carry on;\n"
               "• run blocks — run a fallback sequence (set up with the button "
               "next to it);\n"
               "• restart phase — begin the current phase again from its first "
               "block;\n"
               "• skip rest — abandon the remaining blocks of this pass;\n"
               "• stop — stop the macro.",
    "on_fail_blocks": "The fallback sequence for the run blocks mode. The "
                      "button opens an editor where you build it exactly like "
                      "an ordinary phase. Only has an effect when On fail = "
                      "run blocks.",
    "on_fail_after": "What to do once the fallback sequence has finished:\n"
                     "• continue main — go back to the main sequence and carry "
                     "on from the same place;\n"
                     "• restart phase — begin the current phase again;\n"
                     "• restart macro — restart the whole macro, Setup "
                     "included;\n"
                     "• stop — stop.",
}
