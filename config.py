import os
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
BOT_PREFIX = '!'

# Steam Workshop Configuration
STEAM_WORKSHOP_BASE_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id="
STEAM_API_BASE_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

# CDLC and Compat Mods Configuration
CDLC_COMPAT_MODS = {
    "GM": {
        "name": "Global Mobilization - Cold War Germany",
        "required_mods": [1808728802],  # Global Mobilization CDLC mod ID
        "compat_mod": 1776428269,
        "compat_name": "Global Mobilization - Cold War Germany Compatibility Data",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=1776428269",
        "cdlc_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=1776428269"
    },
    "SOG": {
        "name": "S.O.G. Prairie Fire",
        "required_mods": [1224892496],  # S.O.G. Prairie Fire CDLC mod ID
        "compat_mod": 2477276806,
        "compat_name": "S.O.G. Prairie Fire Compatibility Data",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2477276806",
        "cdlc_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2477276806"
    },
    "CSLA": {
        "name": "CSLA Iron Curtain",
        "required_mods": [1294443683],  # CSLA Iron Curtain CDLC mod ID
        "compat_mod": 2503886780,
        "compat_name": "CSLA Iron Curtain Compatibility Data",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2503886780",
        "cdlc_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2503886780"
    },
    "SPE": {
        "name": "Spearhead 1944",
        "required_mods": [1873244913],  # Spearhead 1944 CDLC mod ID
        "compat_mod": 2991828484,
        "compat_name": "Spearhead 1944 Compatibility Data",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2991828484",
        "cdlc_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2991828484"
    },
    "WS": {
        "name": "Western Sahara",
        "required_mods": [1681170],  # Western Sahara CDLC mod ID
        "compat_mod": 2636962953,
        "compat_name": "Western Sahara Compatibility Data",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2636962953",
        "cdlc_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=2636962953"
    },
    "RF": {
        "name": "Reaction Forces",
        "required_mods": [2017047000],  # Reaction Forces CDLC mod ID
        "compat_mod": 3150497912,
        "compat_name": "Reaction Forces Compatibility Data",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=3150497912",
        "cdlc_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=3150497912"
    },
    "EF": {
        "name": "Expeditionary Forces",
        "required_mods": [2017047001],  # Expeditionary Forces CDLC mod ID
        "compat_mod": 3348605126,
        "compat_name": "Expeditionary Forces Compatibility Data",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=3348605126",
        "cdlc_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=3348605126"
    }
}

# Known Mod Sizes (in GB) - will be cached and updated
KNOWN_MOD_SIZES = {
    # Example mod sizes
    "123456789": 1.2,
    "987654321": 0.8,
    "234567890": 2.1,
    "876543210": 1.5,
}

# Bot Settings
MAX_MODS_PER_PAGE = 10
MESSAGE_DELETE_DELAY = 300  # 5 minutes
CACHE_DURATION = 2592000  # 30 days in seconds 