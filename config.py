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
        "name": "Global Mobilization",
        "required_mods": [123456789],  # Example mod IDs
        "compat_mod": 987654321,
        "compat_name": "GM Compat",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=987654321"
    },
    "SOG": {
        "name": "S.O.G. Prairie Fire",
        "required_mods": [234567890],
        "compat_mod": 876543210,
        "compat_name": "SOG Compat",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=876543210"
    },
    "CSLA": {
        "name": "CSLA Iron Curtain",
        "required_mods": [345678901],
        "compat_mod": 765432109,
        "compat_name": "CSLA Compat",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=765432109"
    },
    "SPE": {
        "name": "Spearhead 1944",
        "required_mods": [456789012],
        "compat_mod": 654321098,
        "compat_name": "SPE Compat",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=654321098"
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