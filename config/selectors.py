"""
CSS / XPath selectors for Google Maps elements.

CRITICAL: ALL selectors must live here — never hardcode elsewhere.
When Google changes their HTML, update ONLY this file.

Selector priority: data-* attrs > aria-* labels > stable classes > XPath.
Every element has multiple fallbacks ordered from most to least reliable.
"""

# ============================================================
# SEARCH RESULTS PAGE
# ============================================================

# The scrollable results feed container
RESULTS_FEED_SELECTORS: list[str] = [
    'div[role="feed"]',
    '.m6QErb[aria-label]',
    '.DxyBCb',
    'div[jsaction*="mouseover:pane"]',
]

# Anchor element for each result card (href = business URL)
RESULT_LINK_SELECTORS: list[str] = [
    "a.hfpxzc",
    "a[data-cid]",
    'div.Nv2PK a[href*="maps/place"]',
    'a[href*="/maps/place/"]',
]

# Text that indicates all results have been loaded
END_OF_RESULTS_TEXT: list[str] = [
    "You've reached the end of the list",
    "Reached the end of the list",
    "No more results",
]

END_OF_RESULTS_SELECTORS: list[str] = [
    ".HlvSq",
    ".PbZDve p",
    'p[class*="fontBodyMedium"]',
]

# ============================================================
# BUSINESS DETAIL PAGE
# ============================================================

# Business name
BUSINESS_NAME_SELECTORS: list[str] = [
    "h1.DUwDvf",
    "h1.fontHeadlineLarge",
    ".DUwDvf",
    'h1[class*="fontHeadline"]',
    ".lMbq3e h1",
    "h1",
]

# Primary category / type
CATEGORY_SELECTORS: list[str] = [
    "button.DkEaL",
    ".DkEaL",
    'button[jsaction*="pane.category"]',
    'button[jsaction*="category"]',
    ".mgr77e",
]

# Numeric rating value (e.g., "4.5")
RATING_VALUE_SELECTORS: list[str] = [
    "div.fontDisplayLarge",           # primary: the large rating number
    'div[aria-hidden="true"].fontDisplayLarge',
    ".MW4etd",
    'div[class*="fontDisplayLarge"]', # class-pattern fallback
    'span.ceNzKf[aria-label*="star"]',
    'span[aria-label*="stars"]',      # aria label variant
    'span[aria-label*="Star rating"]',
    'div[aria-hidden="true"][class*="fontDisplay"]',
    'span[aria-label*="Rated"]',
    # Rating inside the review button (aria-label like "4.7 stars, 1,099 reviews")
    'button[aria-label*="stars"] span.fontDisplayLarge',
    'button[aria-label*="star"] span',
    'div[jsaction*="pane.rating"] span.fontDisplayLarge',
]

# Total review count (e.g., "1,234 reviews" or "(1,234)")
# Targets the VISIBLE rendered count only — NOT button aria-labels, which carry
# Google's all-languages total (often higher than the displayed filtered count).
REVIEW_COUNT_SELECTORS: list[str] = [
    ".lyplG span",           # current Google Maps: count lives inside .lyplG
    ".lyplG a",              # sometimes wrapped in an anchor
    ".lyplG",                # fallback: the container itself
    ".FUc4fe span",          # parent of lyplG
    "span.UY7F9",            # legacy class name (still present on some layouts)
    'button[jsaction*="pane.rating"] span.UY7F9',
    'div[jsaction*="pane.rating"] span.UY7F9',
    # Newer Google Maps layouts (2025+)
    'span[aria-label*="review"]',
    'a[aria-label*="review"]',
    'button[aria-label*="review"]',
    '. fontBodyLarge span',  # review count in the overview panel
    # JS-evaluated fallback: scan for "(N)" pattern near the rating stars
    'span.ceNzKf',
    '.MW4etd + span',
    'div.fontBodyLarge span',
]

# Full address text
ADDRESS_SELECTORS: list[str] = [
    'button[data-item-id="address"] .Io6YTe',
    '[data-tooltip="Copy address"] .Io6YTe',
    '[aria-label^="Address:"] .Io6YTe',
    'button[data-item-id="address"]',
    '[data-tooltip="Copy address"]',
    'button[aria-label*="Address"]',
]

# Phone number
PHONE_SELECTORS: list[str] = [
    'button[data-item-id*="phone"] .Io6YTe',
    '[data-tooltip="Copy phone number"] .Io6YTe',
    '[aria-label^="Phone:"] .Io6YTe',
    'button[data-item-id*="phone"]',
    '[data-tooltip="Copy phone number"]',
    'button[aria-label*="Phone"]',
]

# Website URL
WEBSITE_SELECTORS: list[str] = [
    'a[data-item-id="authority"]',
    '[data-tooltip="Open website"]',
    'a[aria-label^="Website:"]',
    'a[data-item-id="authority"] .Io6YTe',
    'a[aria-label*="website"]',
]

# Hours section button (click to expand)
HOURS_BUTTON_SELECTORS: list[str] = [
    '[data-item-id="oh"]',
    'button[jsaction*=":oh"]',
    '[data-section-id="Oh"] button',
    'div[data-attrid="kc:/location/location:hours"] button',
    ".t39EBf",
    ".OMl5r",
    # Newer layouts — the hours row itself is the clickable button
    'div[role="button"][jsaction*="pane.openhours"]',
    'button[jsaction*="openhours"]',
    '[data-item-id="oh"] button',
    # aria-label contains the current open/closed status + hours hint
    'button[aria-label*="hour"]',
    'button[aria-label*="Hours"]',
    'button[aria-expanded][aria-label*="AM"]',
    'button[aria-expanded][aria-label*="PM"]',
    'button[aria-expanded][aria-label*="Closed"]',
    'button[aria-expanded][aria-label*="Open"]',
    # Fallback: any button near the clock icon (aria-label containing time patterns)
    'button[aria-label*="Monday"]',
    'button[aria-label*="Sunday"]',
]

# Selectors that confirm the hours panel has fully expanded after clicking
HOURS_EXPANDED_SELECTORS: list[str] = [
    'button[aria-expanded="true"][data-item-id="oh"]',
    'button[aria-expanded="true"][jsaction*=":oh"]',
    'button[aria-expanded="true"][jsaction*="openhours"]',
    'button[aria-expanded="true"][aria-label*="Monday"]',
    'button[aria-expanded="true"][aria-label*="Sunday"]',
    "table.eK4R0e",
    ".y0skZc",
    ".eLasMc",
    ".mxowUb",   # hours popup wrapper (newer layout)
    ".t39EBf + div table",
    '[aria-expanded="true"][aria-label*=";"]',
]

# Hours open/closed status text
HOURS_STATUS_SELECTORS: list[str] = [
    ".o0Svhf",
    ".ZdKrc span",
    ".OqCZI .ZDu9vd",
    '[data-item-id="oh"] .Io6YTe',
    ".ehuGue",
]

# Business description
DESCRIPTION_SELECTORS: list[str] = [
    ".PYvSYb",                                  # primary description span
    ".xt2b0d .PYvSYb",                          # description inside about section
    '[data-attrid="kc:/local:description"] span',
    ".WgFkxc",
    ".PYvSYb span",
    # Newer Google Maps layouts
    ".WeS02d span",
    ".iP2t7d .PYvSYb",
    '[data-section-id="description"] span',
    # Note: ".HlvSq" removed — it also matches the "reached end of list" text
    # on the search results page and causes false positives there.
    # 2025+ layouts
    'div[data-attrid*="description"]',
    'span[data-attrid*="description"]',
    '.LBgpqf',
    '.m6QErb div.fontBodyMedium',
    'div[role="main"] span.PYvSYb',
]

# Price level (e.g., "$", "$$")
PRICE_SELECTORS: list[str] = [
    # Aria-label chips (most reliable — Google encodes the price tier here)
    'span[aria-label*="Inexpensive"]',
    'span[aria-label*="Moderately expensive"]',
    'span[aria-label*="Expensive"]',
    'span[aria-label*="Very expensive"]',
    # Price chip button (newer layout)
    'button[aria-label*="Price"]',
    'button[aria-label*="price"]',
    # Price as text beside category (e.g. "Restaurant · $$")
    ".ZkKOFe",
    ".mgr77e",                           # can be category OR price — check for "$"
    '[data-attrid="price_range"] span',
    # Generic span containing $ symbols
    'span[aria-label*="$"]',
    # Newer Google Maps layouts — overview/subheader area
    ".bJzME",
    ".F7nice span",
    ".YhemCb",
    ".LBgpqf",
    # Any element with aria-label that includes "price" (case-insensitive)
    '[aria-label*="price" i]',
    '[aria-label*="Price" i]',
]

# Main / hero image
MAIN_IMAGE_SELECTORS: list[str] = [
    'button[data-photo-index="0"] img',
    ".t5wEmd img",
    ".RZ66Rb img",
    'button[jsaction*="photo"] img',
    ".ZKCDEc img",
]

# All photo buttons / thumbnails
ALL_PHOTOS_SELECTORS: list[str] = [
    "button[data-photo-index] img",   # primary: indexed photo buttons in header
    "[data-photo-index] img",
    ".t5wEmd img",
    ".ZKCDEc img",
    ".RZ66Rb img",
    ".aoRNLd img",                    # sometimes used for gallery strip
    'img[src*="googleusercontent.com"][src*="=w"]',   # all Google-hosted images with size param
]

# ============================================================
# ATTRIBUTES / AMENITIES SECTION
# ============================================================

# Attribute section container
ATTRIBUTES_SECTION_SELECTORS: list[str] = [
    ".m6QErb[aria-label*='Amenities']",
    ".LTs0Rc",
    "[aria-label*='About']",
    ".iP2t7d",
]

# Individual attribute item — labels inside amenity / service chips
# These appear in the "About" section (requires clicking About tab first).
ATTRIBUTE_ITEM_SELECTORS: list[str] = [
    ".CK16pd .RiRi5e",              # chip label inside About section
    ".iP2t7d .RiRi5e",
    ".hpLkke .RiRi5e",
    ".CK16pd span.fontBodyMedium",
    ".iP2t7d span.fontBodyMedium",
    ".iP2t7d span",
    ".hpLkke span",
    # Newer Google Maps layouts
    ".e2moi span",
    ".Qqlxhb span",
    '[aria-label*="Amenities"] span',
    '[aria-label*="Highlights"] span',
    '[aria-label*="Offerings"] span',
    '[aria-label*="Accessibility"] span',
    '[aria-label*="Planning"] span',
    # Fallback: any span inside the About panel container
    ".m6QErb[aria-label*='About'] span.fontBodyMedium",
    # 2025+ layouts
    'div[data-section-id="Amenities"] span',
    'div[data-section-id="Highlights"] span',
    'div[data-section-id="Service options"] span',
    'div[data-section-id="Accessibility"] span',
    'div[aria-label*="Amenities"] div.fontBodyMedium',
    'div[aria-label*="Highlights"] div.fontBodyMedium',
    '.e2moi div.fontBodyMedium',
    '.CK16pd div.fontBodyMedium',
]

# ============================================================
# REVIEWS SECTION
# ============================================================

# "About" tab button — click to reveal amenities, accessibility, service options, etc.
# These attributes are NOT in the DOM until this tab is active.
ABOUT_TAB_SELECTORS: list[str] = [
    'button[aria-label*="About"]',
    'button[data-tab-index="3"]',
    'button[data-tab-index="2"]',   # layout varies: sometimes About is index 2
    '.hh2c6[aria-label*="About"]',
    'div[role="tablist"] button:nth-child(4)',
    'div[role="tablist"] button:nth-child(3)',
]

# Reviews tab button
REVIEWS_TAB_SELECTORS: list[str] = [
    'button[aria-label*="Reviews"]',
    'button[aria-label*="reviews"]',
    'button[data-tab-index="1"]',
    '.hh2c6[data-tab-index="1"]',
    '.hh2c6[aria-label*="Review"]',
    'div[role="tablist"] button:nth-child(2)',
]

# Individual review card
REVIEW_ITEM_SELECTORS: list[str] = [
    ".jftiEf",
    ".GHT2ce",
    "[data-review-id]",
    ".lRecsd",
    ".WMbnJf",
    ".bwb7ce",
    ".d4r55 + div",   # review card starting after author name
    'div[data-google-review-count] .jftiEf',
    # Newer Google Maps layouts
    '.Rv6GBb',
    '.Dh6h6e',
    '.yDd9Nb',
    'div[role="article"]',
    'div[data-review-id]',
]

# Review author name
REVIEW_AUTHOR_SELECTORS: list[str] = [
    ".d4r55",
    ".W8nwCe",
    ".kvMYJc + .W8nwCe",
    "button[data-href*='contrib'] span",
]

# Review text body
REVIEW_TEXT_SELECTORS: list[str] = [
    ".wiI7pd",
    ".MyEned",
    "span[data-expandable-section]",
    ".Jtu6Td",
]

# Review star rating (aria-label contains the score)
REVIEW_RATING_SELECTORS: list[str] = [
    'span.kvMYJc[aria-label*="star"]',
    'span[aria-label*="star"]',
]

# Review relative date (e.g., "2 weeks ago")
REVIEW_DATE_SELECTORS: list[str] = [
    ".rsqaWe",
    ".dehysf",
    ".xRkPPb",
]

# ============================================================
# CONSENT / COOKIE POPUPS
# ============================================================

CONSENT_BUTTON_SELECTORS: list[str] = [
    'button[aria-label="Accept all"]',
    'button[aria-label="Agree to all"]',
    "#L2AGLb",                             # Classic Google "I agree"
    "button.tHlp8d",
    'form[action*="consent"] button[value="2"]',
    'button[aria-label*="Accept all"]',
    'button[aria-label*="Agree"]',
    'div.lssxud button:first-child',
    "#W0wltc",
]

# ============================================================
# CAPTCHA DETECTION
# ============================================================

CAPTCHA_SELECTORS: list[str] = [
    "#recaptcha",
    ".g-recaptcha",
    'iframe[src*="recaptcha"]',
    'iframe[title*="reCAPTCHA"]',
    "form#captcha-form",
    'h1:has-text("unusual traffic")',
    'p:has-text("not a robot")',
]
