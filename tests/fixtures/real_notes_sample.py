"""Real-world note samples for testing.

These represent the kind of unstructured, stream-of-consciousness input
that Clarion must handle. Notes range from terse single words to emotional
venting to detailed technical plans.

In practice, most of these would arrive as individual notes. Occasionally
a batch of 3-8 related lines arrives at once.
"""

# Individual notes — each would typically be a separate submission
INDIVIDUAL_NOTES = [
    # Terse / cryptic — need context to understand
    "Solar!!!",
    "Duke",
    "Futurama",
    "Pizza steel!!!",
    "Desk mat...",
    "New Shoes.",

    # Shopping — various stores and items
    "Mouthwash and brush and water pick...",
    "Electric toothbrush",
    "Costco for Apple Watch.",
    "Get prime card?!",
    "Get a really nice hand vacuum.",
    "Get nice set of kitchen knives and new cutting boards",
    "Food processor attachment for kitchenaid",
    "Buy cooler and funnel and smaller jar asap...",
    "Get 4 more home depot chairs",
    "Buy the retro chromatic",
    "Soap dispensers...",
    "Vase and flowers",
    "Clip nails and buy nail file",
    "New controllers",
    "Apple watch charging stuff for kenz...",
    "Retracting usb c cables for back of tv...",

    # Home improvement
    "Leds for fence and more magnets...",
    "Lights on my fence posts.",
    "Doorbell and cams!",
    "Put a light in the breezeway and wire up power to the ikea blinds, hardwire...",
    "Mirror doors to the garage.",
    "Fix roof",
    "Hang Towel bar and final monitors.",
    "And Hang board.",
    "Roof and pool!",
    "Garage clean...",
    "Hang Penguin",
    "3d Print coffee stuff and fridge and roomba ramp",
    "Annihilation person statue",
    "Get an NGE picture of pen pen.",
    "Squid game halloween decoration...",
    "Stickers for kitchen org",
    "Also: coasters",
    "Print stickers of all the things that go on shelves...",
    "Fridge plastic, coffee table, higher.",

    # Home automation / tech
    "Garage smart stuff...",
    "Home assistant",
    "Set up home vlans for the smart devices 2.4 network on my router.",
    "Hard code ip addresses for all those things.",
    "Make special routes for tv stuff etc",
    "Set up temp for fridge compressor monitor...",
    "Funnel and home assistant hardware.",
    "Big ass fan.",
    "Save and edit roomba map",
    "Monitor cables, hdmi and displayport for all",
    "Docks at each desk? Desk mats? Etc...",

    # NAS / server
    "45 drives server??? Figure out os for nas zfs stuff...",
    "Truenas, how to add random hard drives easily...",
    "Recertified hard drives...",
    "Temp sensor...",
    "How to set up pxe and nfs without them existing...",
    "Same for dns and dhcp and such...",

    # Work
    "Work tauri!!!",
    "Llm stuff!!!",
    "Make android app for it...",
    "Deploy km thing and window manager thing",
    "Try out deepseek v3...",
    "Work work work tonight!!!",

    # Work — emotional / venting
    "If they blame me for gennady leaving I quit.",
    "I want to know what happened.",
    "This company is so unhealthy from a leadership perspective. Those guys are all ICs deeeeeep in their bones.",

    # Baby / family
    "Crib mobile???",
    "Ceiling stars?",
    "Start thinking about child proofing.",
    "Allergy list again for gwen...",
    "Subscription to huckleberry needs to be 1 year",
    "Photos for the book, fuck",

    # Food / cooking
    "78 degree chamber for sourdough.",
    "Grilled chicken on the grill is next...",
    "Twice a week!",
    "Meal plan more?",
    "Do those meal prep things for like a month",
    "For 1 person...",
    "Make brownies and toss old brownie/cookie stuff",
    "Boos block and nice cutting boards",
    "Bamboo are the cheap crap ones, not plastic?",

    # Media
    "Man on the inside",
    "Hunger Games movies.",
    "Fast movies",
    "Pirates movies",
    "Watch penguin also and peacemaker",
    "GelaG's Stratigraphy, Fossil Hunting Game.",

    # Finance
    "More 401k...",
    "Invest cash harder",

    # Health / personal
    "Get an oura or equivalent ring someday",
    "Nfc ring also...",
    "Buy new shoes",

    # Future house
    "House design stuff",
    "Get a house design to start with and software",
    "Then iterate A LOT",
    "Go through every outlet, light, drawer, etc",
    "Mock the entire thing up and walk around in virtual space",

    # Books
    "Brad Jacob's book.",

    # Vacation
    "Ski Vacation and Mystery Hunt",

    # Pool
    "Clean up pool and try to automate more",
    "Next year really do saltwater pool + automation",

    # Renovations
    "Level Foundation",
    "Fix all doors: seal, level, strike plates",
    "Roof and welder guy for gates",
    "Put extra braces",

    # Misc
    "Screen for Household stuff...",
    "Ltt modmat...",
    "Measurement desk mat...",
    "Get two more sets of house keys and put a smart lock on the gate.",
    "Make more stuff???",
    "Hang up hats and hangboard",
]

# Batch notes — these would arrive as a group
BATCH_NOTES = [
    # Costco shopping batch
    [
        "Costco's sectional.",
        "Costco, Pergola.",
        "Costco dining table.",
        "Costco immersion blender, Vitamix and Vacuum.",
    ],
    # People list (work context)
    [
        "Duke",
        "Shintaro",
        "Awood",
        "Other intern daniel",
        "People in ipa? Bill? Eservin..",
        "Gennady",
    ],
    # Home renovation batch
    [
        "Level Foundation",
        "Fix all doors: seal, level, strike plates",
        "Roof and welder guy for gates",
        "Put extra braces",
    ],
    # House design batch
    [
        "House design stuff",
        "Get a house design to start with and software",
        "Then iterate A LOT",
        "Go through every outlet, light, drawer, etc",
        "Mock the entire thing up and walk around in virtual space",
    ],
]
