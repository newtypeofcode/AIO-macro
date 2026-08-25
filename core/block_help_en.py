"""English half of the block help; the Russian half lives in block_help.py.

The two are a pair: block_help._table() picks one of them by language and
merges it into the catalog, so this module must expose exactly the same keys
as its Russian twin -- every block type, every field, and every entry in
SHARED, each with a label and a help string. block_help.missing("en") walks
both tables and reports whatever this one has not filled in, so a
half-finished translation surfaces as a test failure instead of as blank
tooltips in the UI.

Nothing outside these two dicts needs touching to change the wording.
"""

# type -> {"label": str, "desc": str,
#          "fields": {key: {"label": str, "help": str}}}
HELP = {
    # ------------------------------------------------------------- mouse
    "click": {
        "label": "Click",
        "desc": "Clicks the mouse at a point. Coordinates are relative to the "
                "target window (or to the screen, when the target is the whole "
                "screen). The Pick button captures a coordinate from your next "
                "click.",
        "fields": {
            "x": {
                "label": "X",
                "help": "Horizontal coordinate, from the left edge of the "
                        "target window.",
            },
            "y": {
                "label": "Y",
                "help": "Vertical coordinate, from the top edge of the "
                        "target window.",
            },
            "button": {
                "label": "Button",
                "help": "Which mouse button to press.",
            },
            "clicks": {
                "label": "Clicks",
                "help": "How many clicks in a row. 2 is a double-click.",
            },
            "hold_ms": {
                "label": "Hold ms",
                "help": "How long to keep the button down. Some applications "
                        "ignore clicks that are too quick.",
            },
        },
    },
    "move": {
        "label": "Move Mouse",
        "desc": "Moves the cursor without clicking. Needed when the target "
                "reacts to hover -- tooltips, buttons that light up.",
        "fields": {
            "x": {
                "label": "X",
                "help": "Horizontal coordinate to land on.",
            },
            "y": {
                "label": "Y",
                "help": "Vertical coordinate to land on.",
            },
            "duration_ms": {
                "label": "Duration ms",
                "help": "0 is an instant jump. Anything above zero glides "
                        "over that time; it looks more natural and triggers "
                        "hover effects more reliably.",
            },
        },
    },
    "move_by": {
        "label": "Move Mouse By",
        "desc": "Moves the cursor BY an offset from wherever it is now, "
                "rather than to a fixed point. A 0 on an axis leaves "
                "that axis alone: X 0 with Y 200 drops the cursor 200 "
                "pixels straight down. Negative values go left and up.",
        "fields": {
            "dx": {
                "label": "Offset X",
                "help": "Pixels to the right. Negative goes left, 0 "
                        "leaves this axis untouched.",
            },
            "dy": {
                "label": "Offset Y",
                "help": "Pixels down. Negative goes up, 0 leaves this "
                        "axis untouched.",
            },
            "duration_ms": {
                "label": "Duration ms",
                "help": "0 is an instant shift. Above zero glides over "
                        "that time.",
            },
        },
    },
    "drag": {
        "label": "Drag",
        "desc": "Presses a button, drags the cursor to another point and "
                "releases. For sliders, moving items around, selecting.",
        "fields": {
            "from_mode": {
                "label": "Start",
                "help": "\"point\" starts at the X and Y below. "
                        "\"current\" starts wherever the cursor already "
                        "is, and X and Y are then ignored.",
            },
            "to_mode": {
                "label": "End",
                "help": "\"point\" drags to the To X/Y coordinates. "
                        "\"offset\" drags BY that many pixels from the "
                        "start: 0 and 200 is 200 pixels straight down, "
                        "negatives go left and up.",
            },
            "x": {
                "label": "From X",
                "help": "Where to start -- horizontal.",
            },
            "y": {
                "label": "From Y",
                "help": "Where to start -- vertical.",
            },
            "x2": {
                "label": "To X",
                "help": "Where to end up -- horizontal.",
            },
            "y2": {
                "label": "To Y",
                "help": "Where to end up -- vertical.",
            },
            "button": {
                "label": "Button",
                "help": "Which button to drag with.",
            },
            "duration_ms": {
                "label": "Duration ms",
                "help": "How long the trip takes. Many applications never "
                        "notice a drag that happens too fast.",
            },
        },
    },
    "place_unit": {
        "label": "Place Unit",
        "desc": "Presses the unit's hotkey, then clicks the spot picked on "
                "the map. The map is your own screenshot from the Maps "
                "folder; the spot is stored together with that picture's "
                "size and rescaled to whatever size the game window is now.",
        "fields": {
            "unit": {
                "label": "Unit key",
                "help": "The hotkey that selects the unit in game (usually "
                        "1-5). Without it the game never enters placement "
                        "mode and the click does nothing.",
            },
            "location": {
                "label": "Map location",
                "help": "Opens the map picture and lets you click where the "
                        "unit goes. Dots mark the units other blocks already "
                        "place on the same map, so two do not land on the "
                        "same spot.",
            },
            "key_delay_ms": {
                "label": "Wait after key, ms",
                "help": "Pause between the hotkey and the click. The game "
                        "needs this long to enter placement mode -- click "
                        "sooner and nothing is placed at all.",
            },
            "clicks": {
                "label": "Clicks",
                "help": "How many times to click the spot. Two by default: "
                        "the first click often only aims the placement "
                        "ghost, and one click leaves the unit unplaced.",
            },
            "after_ms": {
                "label": "Wait after, ms",
                "help": "How long to wait after placing -- the game needs "
                        "time for the animation, or the next unit fails to "
                        "go down.",
            },
        },
    },
    "mouse_look": {
        "label": "Camera Setup (mouse look)",
        "desc": "Holds a mouse button and streams RELATIVE deltas -- how "
                "a game camera is turned (Roblox and the like). Plain "
                "Move and Drag cannot do it: such a game hides the "
                "cursor, recenters it every frame and reads raw deltas "
                "rather than the cursor position, so an absolute jump "
                "registers as no movement at all.\n\nHow far the camera "
                "turns per pixel is the game's own sensitivity, so a "
                "measured turn lands somewhere different on every machine. "
                "Leave the mode on 'to limit' and the camera is pushed "
                "into its own stop instead, which is the same place "
                "everywhere.",
        "fields": {
            "button": {
                "label": "Button",
                "help": "Which button to hold while looking. Right for "
                        "Roblox. \"none\" just sends the deltas, for "
                        "games that already captured the cursor.",
            },
            "mode": {
                "label": "Mode",
                "help": "'to limit' sends far more travel than any "
                        "sensitivity needs, so the camera runs into its "
                        "own stop and ends there -- the same result on "
                        "every PC, VM and mouse setting. Use it for "
                        "'look all the way down'. 'exact' moves the "
                        "measured amount instead, which depends on the "
                        "game's sensitivity.",
            },
            "dx": {
                "label": "Step X",
                "help": "Pixels right on EACH step. Negative goes left. "
                        "Note that a sideways sweep has no stop to run "
                        "into -- the camera spins forever -- so left and "
                        "right cannot be made sensitivity-proof this way.",
            },
            "dy": {
                "label": "Step Y",
                "help": "Pixels down on EACH step. Negative goes up. "
                        "Down is the one with a hard stop, which is what "
                        "'to limit' aims at.",
            },
            "sweep_px": {
                "label": "Sweep px",
                "help": "Total travel in 'to limit' mode. Deliberately "
                        "far more than needed: past the stop the extra "
                        "deltas do nothing, so a large number costs "
                        "nothing and covers the lowest sensitivity. "
                        "Raise it if a very low sensitivity still stops "
                        "short.",
            },
            "steps": {
                "label": "Steps",
                "help": "'exact' mode only: how many deltas to send. The "
                        "game reads a stream of small ones, so 40 steps "
                        "of 80 turn the camera while a single step of "
                        "3200 barely does.",
            },
            "step_delay_ms": {
                "label": "Step delay ms",
                "help": "Wait between deltas. Around 8-12ms is about "
                        "one frame; much faster and the game drops some "
                        "of them.",
            },
            "centre_first": {
                "label": "Centre first",
                "help": "Move the cursor to the middle of the target "
                        "window before pressing, so the button lands "
                        "inside the game and not on whatever is next to "
                        "it.",
            },
            "settle_ms": {
                "label": "Settle ms",
                "help": "Pause after the button goes down and before it "
                        "comes up, giving the game time to enter and "
                        "leave look mode.",
            },
        },
    },
    "scroll": {
        "label": "Scroll",
        "desc": "Turns the mouse wheel. If coordinates are given the cursor "
                "moves there first -- scrolling happens under the cursor.",
        "fields": {
            "amount": {
                "label": "Amount",
                "help": "One wheel notch = 120. Negative scrolls down, "
                        "positive scrolls up.",
            },
            "x": {
                "label": "X",
                "help": "Where to put the cursor before scrolling.",
            },
            "y": {
                "label": "Y",
                "help": "Where to put the cursor before scrolling.",
            },
        },
    },

    # ---------------------------------------------------------- keyboard
    "roblox_rejoin": {
        "label": "Rejoin Server",
        "desc": "Closes Roblox and joins the server again through the "
                "launcher's roblox:// link. Roblox has no reconnect of its "
                "own, and a client that is still running swallows the link "
                "and stays where it is -- so the old client is killed first. "
                "When the game is back its new window becomes the target, "
                "because the old window died with the old process and every "
                "coordinate in the macro is measured against the target.",
        "fields": {
            "share_link": {
                "label": "Share link",
                "help": "Paste a roblox.com/share link (the one that looks "
                        "like .../share?code=...&type=Server) and leave the "
                        "two fields below empty -- the link is the whole "
                        "invite, so there is no id or code to dig out by "
                        "hand. The client resolves it itself, exactly as it "
                        "does when you click the link in a browser. Empty "
                        "means the link saved in Settings is used, if there "
                        "is one.",
            },
            "place_id": {
                "label": "Place id",
                "help": "The game's id, for the older form of joining. You "
                        "can paste the whole game link -- the number is "
                        "picked out of it. Ignored while a share link is "
                        "set. Empty uses the one in Settings, so one edit "
                        "fixes every rejoin block you have.",
            },
            "link_code": {
                "label": "Private server code",
                "help": "The linkCode from your private server link. Paste "
                        "the link itself if that is easier. Empty means the "
                        "public game (or the code saved in Settings).",
            },
            "close_first": {
                "label": "Close Roblox first",
                "help": "Kill the running client before joining. Keep this "
                        "on: a live client ignores the join link, and the "
                        "block would just wait out its timeout.",
            },
            "close_wait_ms": {
                "label": "Pause after closing, ms",
                "help": "How long to wait once the client is gone before "
                        "launching again. Too short and the launcher meets "
                        "the dying process and does nothing.",
            },
            "timeout_ms": {
                "label": "Wait for the window, ms",
                "help": "How long to keep watching for the game window. A "
                        "cold start plus the launcher can take a minute on a "
                        "slow machine, so this is generous by default.",
            },
            "settle_ms": {
                "label": "Pause after it appears, ms",
                "help": "The window shows up long before the place is "
                        "loaded and playable. This is the wait for the game "
                        "itself -- clicking into a half-loaded place is what "
                        "makes a rejoin look like it worked and do nothing.",
            },
            "retarget": {
                "label": "Use the new window as target",
                "help": "Point the macro at the window that just opened. "
                        "Leave it on unless you deliberately target "
                        "something else -- the old window no longer exists.",
            },
            "on_fail": {
                "label": "If the rejoin fails",
                "help": "What to do when the game does not come back in "
                        "time, or there is no place id to join.",
            },
            "on_fail_blocks": {
                "label": "Blocks to run",
                "help": "The blocks to run when the rejoin failed -- send a "
                        "webhook, wait longer, try again.",
            },
            "on_fail_after": {
                "label": "Then",
                "help": "Where to carry on once those blocks are done.",
            },
        },
    },
    "send_key": {
        "label": "Send Key",
        "desc": "Presses and releases one key. What gets sent is the physical "
                "key position, so it works on any keyboard layout.",
        "fields": {
            "key": {
                "label": "Key",
                "help": "Click the field, then press the key you want -- it "
                        "gets recorded.",
            },
            "hold_ms": {
                "label": "Hold ms",
                "help": "How long to hold it. Games sometimes need 50-100 "
                        "ms; an instant tap may not register at all.",
            },
            "modifiers": {
                "label": "Modifiers",
                "help": "Modifiers held down together with the key. "
                        "Ctrl + C, Shift + Tab and the like.",
            },
        },
    },
    "type_text": {
        "label": "Type Text",
        "desc": "Types text verbatim, as Unicode. The layout does not matter: "
                "\"Привет\" comes out as \"Привет\" even on an English one.",
        "fields": {
            "text": {
                "label": "Text",
                "help": "What to type. A line break is Enter, a tab is Tab.",
            },
            "delay_ms": {
                "label": "Per-char ms",
                "help": "Pause between characters. Zero is instant, but some "
                        "applications drop characters when typed that fast.",
            },
        },
    },
    "hold_key": {
        "label": "Hold Key",
        "desc": "Holds a key down for a set time and releases it. For walking "
                "in games, sprinting, holding aim. Stop interrupts the hold and "
                "releases the key.",
        "fields": {
            "key": {
                "label": "Key",
                "help": "Click the field, then press the key you want.",
            },
            "hold_ms": {
                "label": "Hold ms",
                "help": "How long to keep it held down.",
            },
        },
    },

    # ------------------------------------------------------------ timing
    "wait_ms": {
        "label": "Wait (ms)",
        "desc": "Simply waits. Stop lands inside the wait rather than after "
                "it -- even a long pause is cut short immediately.",
        "fields": {
            "ms": {
                "label": "Milliseconds",
                "help": "How many milliseconds to wait. 1000 = 1 second.",
            },
        },
    },
    "wait_random": {
        "label": "Wait Random",
        "desc": "Waits a random time inside a range. Makes the rhythm less "
                "machine-like than a fixed pause.",
        "fields": {
            "min_ms": {
                "label": "Min ms",
                "help": "Shortest the pause can be.",
            },
            "max_ms": {
                "label": "Max ms",
                "help": "Longest the pause can be.",
            },
        },
    },

    # ------------------------------------------------------------ vision
    "wait_image": {
        "label": "Wait for Image",
        "desc": "Waits until an image shows up on screen. This is how a macro "
                "adapts to how fast the application actually is, instead of "
                "guessing at pauses. Images are captured on the Images tab.",
        "fields": {
            "template": {
                "label": "Image",
                "help": "Name of a saved image. The + button opens the image "
                        "manager.",
            },
            "timeout_ms": {
                "label": "Timeout ms",
                "help": "How long to wait at most. 0 checks once and does "
                        "not wait.",
            },
            "threshold": {
                "label": "Confidence",
                "help": "Match threshold, 0-1. Lower is more forgiving of "
                        "differences, but the risk of a false match grows. "
                        "0.88 is a sensible starting point.",
            },
            "region": {
                "label": "Region",
                "help": "Search only inside this rectangle. Speeds the "
                        "search up a lot and rules out false hits elsewhere.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do if the image never showed up: carry on, "
                        "abandon the remaining blocks of this pass, or stop "
                        "the macro.",
            },
        },
    },
    "click_image": {
        "label": "Click Image",
        "desc": "Waits for an image and clicks its centre. Works even when the "
                "button lands somewhere different every time -- no coordinates "
                "needed.",
        "fields": {
            "template": {
                "label": "Image",
                "help": "Name of a saved image. The + button opens the image "
                        "manager.",
            },
            "timeout_ms": {
                "label": "Timeout ms",
                "help": "How long to wait for it to appear. 0 checks once "
                        "and does not wait.",
            },
            "threshold": {
                "label": "Confidence",
                "help": "Match threshold, 0-1. Lower is more forgiving of "
                        "differences, but the risk of clicking the wrong "
                        "thing grows.",
            },
            "region": {
                "label": "Region",
                "help": "Search only inside this rectangle. Speeds the "
                        "search up and rules out false hits.",
            },
            "button": {
                "label": "Button",
                "help": "Which button to click the match with.",
            },
            "offset_x": {
                "label": "Offset X",
                "help": "Shifts the click right of the image centre. Useful "
                        "when the label is what can be recognised but the "
                        "thing to press sits next to it.",
            },
            "offset_y": {
                "label": "Offset Y",
                "help": "Shifts the click down from the image centre.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do if the image is not found: carry on, "
                        "abandon the remaining blocks of this pass, or stop "
                        "the macro.",
            },
        },
    },
    "wait_image_gone": {
        "label": "Wait Image Gone",
        "desc": "Waits until an image DISAPPEARS. For loading screens, "
                "spinners, popups -- \"wait until it goes away\".",
        "fields": {
            "template": {
                "label": "Image",
                "help": "Name of a saved image.",
            },
            "timeout_ms": {
                "label": "Timeout ms",
                "help": "How long to wait for it to go away.",
            },
            "threshold": {
                "label": "Confidence",
                "help": "Match threshold, 0-1. The same threshold that "
                        "decides whether the image counts as present.",
            },
            "region": {
                "label": "Region",
                "help": "Search only inside this rectangle.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do if the image is still on screen: carry "
                        "on, abandon the remaining blocks of this pass, or "
                        "stop the macro.",
            },
        },
    },
    "wait_color": {
        "label": "Wait for Color",
        "desc": "Waits until the pixel at a point turns a given colour. "
                "Cheaper than an image search -- good for indicators, health "
                "bars, highlights.",
        "fields": {
            "x": {
                "label": "X",
                "help": "Horizontal coordinate of the pixel.",
            },
            "y": {
                "label": "Y",
                "help": "Vertical coordinate of the pixel.",
            },
            "color": {
                "label": "Color",
                "help": "The colour to wait for. Pick takes the colour from "
                        "your next click.",
            },
            "confidence": {
                "label": "Confidence",
                "help": "How closely the colour has to match, 0-1, applied "
                        "as a tolerance on each channel. 1.0 is pixel-exact; "
                        "0.92 survives anti-aliasing and a slight gradient; "
                        "below 0.8 it starts catching unrelated shades.",
            },
            "timeout_ms": {
                "label": "Timeout ms",
                "help": "How long to wait at most.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do if the colour never appeared.",
            },
        },
    },
    "click_color": {
        "label": "Click Color",
        "desc": "Finds the largest blob of a given colour and clicks its "
                "centre. Cheaper than an image search and survives a change of "
                "shape: a highlighted tile, a coloured button at a different "
                "size.",
        "fields": {
            "color": {
                "label": "Color",
                "help": "Which colour to look for. Pick takes the colour "
                        "from your next click.",
            },
            "confidence": {
                "label": "Confidence",
                "help": "How closely the colour has to match, 0-1, applied "
                        "as a tolerance on each channel. 1.0 is pixel-exact; "
                        "0.90 survives gradients and softened edges; lower "
                        "starts pulling unrelated shades into the same blob.",
            },
            "min_pixels": {
                "label": "Min pixels",
                "help": "Blobs smaller than this are ignored. Filters out "
                        "stray pixels of a similar shade.",
            },
            "region": {
                "label": "Region",
                "help": "Search only inside this rectangle.",
            },
            "timeout_ms": {
                "label": "Timeout ms",
                "help": "How long to wait for the colour to appear.",
            },
            "button": {
                "label": "Button",
                "help": "Which button to click with.",
            },
            "offset_x": {
                "label": "Offset X",
                "help": "Shifts the click right of the blob centre.",
            },
            "offset_y": {
                "label": "Offset Y",
                "help": "Shifts the click down from the blob centre.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do if the colour is not found: carry on, "
                        "abandon the remaining blocks of this pass, or stop "
                        "the macro.",
            },
        },
    },
    "wait_text": {
        "label": "Wait for Text",
        "desc": "Reads the text in a region and waits for the string you want. "
                "Uses the OCR built into Windows. Slower than an image search, "
                "but it survives a change of font or background.",
        "fields": {
            "text": {
                "label": "Text",
                "help": "Which string to wait for.",
            },
            "region": {
                "label": "Region",
                "help": "Where to read. The smaller the area, the faster and "
                        "the more accurate.",
            },
            "timeout_ms": {
                "label": "Timeout ms",
                "help": "How long to wait at most.",
            },
            "confidence": {
                "label": "Confidence",
                "help": "How close the recognised text has to be, 0-1. If "
                        "your string is found literally it always counts. "
                        "The threshold only comes into play when there is no "
                        "literal match: OCR regularly confuses a Latin C "
                        "with a Cyrillic С, or drops a letter.",
            },
            "match": {
                "label": "Match",
                "help": "contains -- the string turns up somewhere inside, "
                        "with Confidence as the allowance for OCR slips; "
                        "exact -- the recognised text matches in full and "
                        "literally.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do if the text is not found.",
            },
        },
    },
    "click_text": {
        "label": "Click Text",
        "desc": "Finds text on screen and clicks it. No coordinates needed -- "
                "the button can be anywhere as long as the label is readable. "
                "The most robust option when the interface moves its elements "
                "around.",
        "fields": {
            "text": {
                "label": "Text",
                "help": "Which label to find and press.",
            },
            "region": {
                "label": "Region",
                "help": "Search only inside this rectangle. Much faster, and "
                        "it rules out matches elsewhere on screen.",
            },
            "timeout_ms": {
                "label": "Timeout ms",
                "help": "How long to wait for the text to appear.",
            },
            "confidence": {
                "label": "Confidence",
                "help": "How close the recognised text has to be, 0-1. A "
                        "literal match always counts; the threshold only "
                        "matters when OCR got a couple of letters wrong. "
                        "Lower is more forgiving, but the risk of pressing "
                        "the wrong label grows. 0.75 is a sensible start.",
            },
            "button": {
                "label": "Button",
                "help": "Which button to click with.",
            },
            "offset_x": {
                "label": "Offset X",
                "help": "Shifts the click right of the label centre.",
            },
            "offset_y": {
                "label": "Offset Y",
                "help": "Shifts the click down from the label centre.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do if the text is not found: carry on, "
                        "abandon the remaining blocks of this pass, or stop "
                        "the macro.",
            },
        },
    },
    "read_text": {
        "label": "Read Text",
        "desc": "Reads the text in a region and writes it to the log. With "
                "Compare set it also checks what it read -- equal, contains, "
                "greater, less -- and runs the On fail policy when the check "
                "does not hold.",
        "fields": {
            "region": {
                "label": "Region",
                "help": "Which area to read.",
            },
            "confidence": {
                "label": "Confidence",
                "help": "Minimum similarity (0..1) when OCR returns a fuzzy match (same scale as click text and wait text). Lower values are more lenient.",
            },
            "compare": {
                "label": "Compare",
                "help": "How to check what was read against Value. 'off' "
                        "only logs the text. The number comparisons pull a "
                        "number out of the text, so 'Wave 12' is greater "
                        "than 9.",
            },
            "expect": {
                "label": "Value",
                "help": "What to compare the read text with.",
            },
            "on_fail": {
                "label": "On fail",
                "help": "What to do when the check does not hold: carry on, "
                        "run fallback blocks, restart the loop, restart the "
                        "whole macro, abandon the rest of this pass, or stop.",
            },
            "on_fail_blocks": {
                "label": "Fallback",
                "help": "Blocks to run instead, for 'run blocks'.",
            },
            "on_fail_after": {
                "label": "Then",
                "help": "What happens once the fallback blocks have run.",
            },
        },
    },

    # ----------------------------------------------------------- system
    "open_app": {
        "label": "Open App",
        "desc": "Launches an application from the given path. "
               "Optional command-line arguments and a post-launch pause are supported.",
        "fields": {
            "path": {
                "label": "Path",
                "help": "Full path to the executable, e.g. C:\\Game\\game.exe.",
            },
            "args": {
                "label": "Arguments",
                "help": "Optional command-line arguments, space-separated.",
            },
            "wait_ms": {
                "label": "Wait after (ms)",
                "help": "How many milliseconds to wait after launching (0 = do not wait).",
            },
        },
    },
    "kill_process": {
        "label": "Kill Process",
        "desc": "Terminates every process whose name contains the given string. "
               "A partial name is enough -- 'chrome' matches chrome.exe.",
        "fields": {
            "name": {
                "label": "Process name",
                "help": "Part of the process name to match, e.g. 'chrome' kills chrome.exe.",
            },
            "force": {
                "label": "Force kill",
                "help": "On: SIGKILL (instant). Off: SIGTERM (graceful).",
            },
        },
    },

        # -------------------------------------------------------------- flow
    "if_else": {
        "label": "If / Else",
        "desc": "Evaluates a condition and runs either the Then or Else block list.",
        "fields": {
            "condition": {"label": "Condition", "help": "The condition to evaluate."},
            "then_blocks": {"label": "Then blocks", "help": "Blocks to run when the condition is true."},
            "else_blocks": {"label": "Else blocks", "help": "Blocks to run when the condition is false."},
        },
    },
    "while_loop": {
        "label": "While Loop",
        "desc": "Repeats its block list while the condition remains true.",
        "fields": {
            "condition": {"label": "Condition", "help": "The condition checked before each iteration."},
            "blocks": {"label": "Loop blocks", "help": "Blocks to run on every iteration."},
            "max_iter": {"label": "Max iterations", "help": "Safety limit that prevents an endless loop."},
        },
    },
    "repeat_until": {
        "label": "Repeat Until",
        "desc": "Runs its block list until the condition becomes true.",
        "fields": {
            "condition": {"label": "Condition", "help": "The condition checked after each iteration."},
            "blocks": {"label": "Loop blocks", "help": "Blocks to run on every iteration."},
            "max_iter": {"label": "Max iterations", "help": "Safety limit that prevents an endless loop."},
        },
    },
    "loop_start": {
        "label": "Loop Start",
        "desc": "Start of a repeated stretch. Everything between this block "
                "and Loop End runs the given number of times. Nesting works.",
        "fields": {
            "count": {
                "label": "Times",
                "help": "How many times to repeat the stretch.",
            },
        },
    },
    "loop_end": {
        "label": "Loop End",
        "desc": "End of the repeated stretch opened by a Loop Start block.",
        "fields": {},
    },
    "restart_loop": {
        "label": "Restart Phase",
        "desc": "Abandons the rest of this pass and starts the phase it sits "
                "in again from its first block. In Loop that means a fresh "
                "loop pass; in Watch it re-runs the watch pass.",
        "fields": {},
    },
    "restart_macro": {
        "label": "Restart Macro",
        "desc": "Starts the whole macro over, Setup included -- the way to "
                "get back to a known state after something went wrong.",
        "fields": {},
    },
    "playback": {
        "label": "Play Recording",
        "desc": "Plays a saved recording as-is, at its own timing. Unlike a "
                "recording that has been broken up into blocks, this keeps the "
                "exact rhythm -- useful for camera drags and any sequence that "
                "is sensitive to timing.",
        "fields": {
            "recording": {
                "label": "Recording",
                "help": "Which saved recording to play. Recordings are made "
                        "on the Record tab.",
            },
            "speed": {
                "label": "Speed",
                "help": "Speed multiplier. 2 is twice as fast, 0.5 is half "
                        "speed.",
            },
        },
    },
    "focus_window": {
        "label": "Focus Target",
        "desc": "Brings the target window to the front and, if asked, puts it "
                "at a set size and position.\n\n"
                "Put this in Setup: a macro recorded at one window size will "
                "miss at another, and this block guarantees the window is the "
                "same every time.",
        "fields": {
            "resize": {
                "label": "Resize",
                "help": "Whether to resize the window at all.",
            },
            "width": {
                "label": "Width",
                "help": "Width of the client area -- the one every "
                        "coordinate in the macro is measured against. The "
                        "border and title bar are added on top automatically.",
            },
            "height": {
                "label": "Height",
                "help": "Height of the client area.",
            },
            "move": {
                "label": "Move",
                "help": "Whether to move the window to a given point on "
                        "screen.",
            },
            "x": {
                "label": "X",
                "help": "Where to put the left edge of the window.",
            },
            "y": {
                "label": "Y",
                "help": "Where to put the top edge of the window.",
            },
        },
    },
    "log": {
        "label": "Log Message",
        "desc": "Writes a line to the journal at the bottom. Affects nothing "
                "-- it helps you see how far the macro got.",
        "fields": {
            "text": {
                "label": "Message",
                "help": "What to write to the journal.",
            },
        },
    },

    # ------------------------------------------------------------ notify
    "send_webhook": {
        "label": "Send Webhook",
        "desc": "Sends a message to Discord and, if you want, attaches a "
                "screenshot. The webhook address is set once on the Setup tab "
                "-- it is not in the block itself, so the macro can be handed "
                "to someone else without giving away the link.\n\n"
                "Nothing is sent while the webhook is switched off in Settings.",
        "fields": {
            "message": {
                "label": "Message",
                "help": "The message text. Up to 2000 characters.",
            },
            "title": {"label": "Title", "help": "Embed title. Leave empty to use the default."},
            "color": {"label": "Color", "help": "Embed color in #RRGGBB format. Leave empty for the default."},
            "footer": {"label": "Footer", "help": "Small text at the bottom of the embed."},
            "timestamp": {"label": "Timestamp", "help": "Show the sending time in the embed."},
            "source": {
                "label": "Attach",
                "help": "What to attach as a picture:\n"
                        "• none — text only;\n"
                        "• target window — a shot of the target window;\n"
                        "• whole screen — the whole screen;\n"
                        "• region — a given rectangle;\n"
                        "• saved image — a picture from Assets.",
            },
            "region": {
                "label": "Region",
                "help": "Which area to capture. Only for the region mode.",
            },
            "template": {
                "label": "Image",
                "help": "Which saved image to attach. Only for the saved "
                        "image mode.",
            },
        },
    },
}


# Fields shared by every Vision block. Defined once here rather than repeated
# in each entry above, and used as the fallback when a block does not spell
# them out itself.
SHARED = {
    "on_fail": {
        "label": "On fail",
        "help": "What to do when the block did not find what it was looking "
                "for:\n"
                "• continue — just carry on;\n"
                "• run blocks — run a fallback sequence (set up with the "
                "button next to it);\n"
                "• restart phase — begin the current phase again from its "
                "first block;\n"
                "• skip rest — abandon the remaining blocks of this pass;\n"
                "• stop — stop the macro.",
    },
    "on_fail_blocks": {
        "label": "Fallback",
        "help": "The fallback sequence for the run blocks mode. The button "
                "opens an editor where you build it exactly like an ordinary "
                "phase. Only has an effect when On fail = run blocks.",
    },
    "on_fail_after": {
        "label": "Then",
        "help": "What to do once the fallback sequence has finished:\n"
                "• continue main — go back to the main sequence and carry on "
                "from the same place;\n"
                "• restart phase — begin the current phase again;\n"
                "• restart macro — restart the whole macro, Setup included;\n"
                "• stop — stop.",
    },
}
