# 🎮 Arma 3 Mod Manager Discord Bot
<img src="loadmaster-log.png" width="300px" height="300px">
A powerful Discord bot designed to help Arma 3 communities manage their mod lists. The bot analyzes HTML mod lists exported from the Arma 3 Launcher and provides comprehensive insights about mods, compatibility, and changes.

## ✨ Features

### 📋 Mod List Analysis
- **Automatic Mod Name Lookup**: Extracts mod IDs from HTML and fetches names from Steam Workshop
- **Size Estimation**: Estimates total download size and individual mod sizes
- **Smart Caching**: Caches mod information to reduce API calls and improve performance

### 🔧 CDLC Compatibility Checking
- **Missing Compat Detection**: Automatically detects when CDLC mods are loaded but compatibility mods are missing
- **Direct Steam Links**: Provides direct links to download missing compatibility mods
- **Supported CDLC**: Global Mobilization, S.O.G. Prairie Fire, CSLA Iron Curtain, Spearhead 1944

### 📈 Change Tracking
- **Mod List Comparison**: Compares current upload with previous uploads
- **Change Detection**: Shows added/removed mods between uploads
- **User History**: Tracks mod lists per user and server

### 📱 Mobile-Friendly Interface
- **Responsive Design**: Works great on both desktop and mobile Discord
- **Interactive Buttons**: Easy-to-use buttons for viewing complete mod lists
- **Categorized View**: Organizes mods by type (maps, weapons, vehicles, etc.)

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- Arma 3 Launcher (for exporting mod lists)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd loadmasterbot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp env_example.txt .env
   ```
   Edit `.env` and add your Discord bot token:
   ```
   DISCORD_TOKEN=your_discord_bot_token_here
   ```

4. **Run the bot**
   ```bash
   python discord_bot.py
   ```

### Getting a Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section
4. Create a bot and copy the token
5. Add the bot to your server with appropriate permissions

## 📖 How to Use

### For Users

1. **Export Mod List from Arma 3 Launcher**
   - Open Arma 3 Launcher
   - Go to Mods tab
   - Select your mod list
   - Click "Export" and save as HTML

2. **Upload to Discord**
   - Simply drag and drop the HTML file into your Discord channel
   - The bot will automatically process it

3. **View Results**
   - The bot will show a comprehensive analysis
   - Use the buttons to view complete mod lists or categories
   - Check for any missing compatibility mods

### Commands

- `!modlist` - Show help information
- `!help` - Show general help

## 🔧 Configuration

### CDLC Compatibility Mods

Edit `config.py` to add or modify CDLC compatibility mods:

```python
CDLC_COMPAT_MODS = {
    "GM": {
        "name": "Global Mobilization",
        "required_mods": [123456789],  # CDLC mod IDs
        "compat_mod": 987654321,       # Compatibility mod ID
        "compat_name": "GM Compat",
        "steam_url": "https://steamcommunity.com/sharedfiles/filedetails/?id=987654321"
    },
    # Add more CDLC here...
}
```

### Known Mod Sizes

Add known mod sizes to improve estimation accuracy:

```python
KNOWN_MOD_SIZES = {
    "123456789": 1.2,  # Mod ID: Size in GB
    "987654321": 0.8,
    # Add more mods here...
}
```

## 🏗️ Architecture

### Core Components

- **`discord_bot.py`**: Main bot implementation with Discord.py
- **`steam_workshop.py`**: Steam Workshop API integration and HTML parsing
- **`mod_analyzer.py`**: Mod analysis, compatibility checking, and categorization
- **`database.py`**: SQLite database for caching and user data
- **`config.py`**: Configuration and constants

### Data Flow

1. **HTML Upload** → Parse mod IDs from HTML
2. **Steam API** → Fetch mod names and sizes
3. **Analysis** → Check compatibility, compare with previous uploads
4. **Database** → Cache results and store user data
5. **Discord** → Send formatted results with interactive buttons

## 🔍 Features in Detail

### Mod List Display
- Shows top mods by size with pagination
- Mobile-friendly buttons for viewing complete lists
- Categorized view (maps, weapons, vehicles, etc.)
- Direct links to Steam Workshop pages

### Compatibility Checking
- Automatically detects loaded CDLC mods
- Checks for required compatibility mods
- Provides direct download links for missing mods
- Color-coded warnings (orange for issues, green for success)

### Size Estimation
- Uses cached mod sizes when available
- Estimates unknown mods based on average size
- Shows breakdown of known vs unknown sizes
- Updates cache with new size information

### Change Tracking
- Compares current upload with last upload
- Shows added and removed mods
- Tracks changes per user and server
- Maintains upload history

## 🛠️ Development

### Adding New Features

1. **New CDLC Support**: Add to `CDLC_COMPAT_MODS` in `config.py`
2. **New Commands**: Add to `ModCommands` class in `discord_bot.py`
3. **New Analysis**: Extend `ModAnalyzer` class in `mod_analyzer.py`

### Database Schema

```sql
-- Mod cache table
CREATE TABLE mod_cache (
    mod_id TEXT PRIMARY KEY,
    mod_name TEXT,
    mod_size REAL,
    last_updated INTEGER
);

-- User uploads table
CREATE TABLE user_uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    server_id TEXT,
    upload_time INTEGER,
    mod_list TEXT,
    total_size REAL
);

-- Mod sizes table
CREATE TABLE mod_sizes (
    mod_id TEXT PRIMARY KEY,
    size_gb REAL,
    last_updated INTEGER
);
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Discord.py community for the excellent Discord API wrapper
- Steam Workshop for providing mod information
- Arma 3 community for inspiration and feedback

## 🐛 Troubleshooting

### Common Issues

1. **Bot not responding to uploads**
   - Check bot permissions in Discord
   - Ensure bot has message content intent enabled

2. **Mod names not showing**
   - Check internet connection
   - Steam Workshop might be temporarily unavailable
   - Mod might be private or removed

3. **Database errors**
   - Ensure write permissions in bot directory
   - Check if SQLite is properly installed

### Logs

The bot will print status messages to console. Check for:
- Connection status
- API errors
- Database operations

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the configuration
3. Open an issue on GitHub

---

**Made for Arma 3 communities** 🎮 