import sqlite3
import json
import time
from typing import List, Dict, Optional, Tuple

class ModDatabase:
    def __init__(self, db_path: str = "arma_mods.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table for storing mod information cache
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mod_cache (
                    mod_id TEXT PRIMARY KEY,
                    mod_name TEXT,
                    mod_size REAL,
                    last_updated INTEGER
                )
            ''')
            
            # Table for storing user uploads
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    server_id TEXT,
                    upload_time INTEGER,
                    mod_list TEXT,
                    total_size REAL
                )
            ''')
            
            # Table for storing mod size estimates
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mod_sizes (
                    mod_id TEXT PRIMARY KEY,
                    size_gb REAL,
                    last_updated INTEGER
                )
            ''')
            
            # Table for storing bot message IDs for cleanup
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT,
                    message_id TEXT,
                    user_id TEXT,
                    server_id TEXT,
                    message_type TEXT,
                    created_time INTEGER
                )
            ''')
            
            # Table for storing active mod lists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_mod_lists (
                    list_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    guild_id TEXT,
                    mods TEXT,
                    download_url TEXT,
                    timestamp INTEGER
                )
            ''')
            
            conn.commit()
    
    def cache_mod_info(self, mod_id: str, mod_name: str, mod_size: Optional[float] = None):
        """Cache mod information"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO mod_cache (mod_id, mod_name, mod_size, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (mod_id, mod_name, mod_size, int(time.time())))
            conn.commit()
    
    def get_cached_mod_info(self, mod_id: str) -> Optional[Dict]:
        """Get cached mod information"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT mod_name, mod_size, last_updated FROM mod_cache
                WHERE mod_id = ?
            ''', (mod_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'mod_name': result[0],
                    'mod_size': result[1],
                    'last_updated': result[2]
                }
            return None
    
    def save_user_upload(self, user_id: str, server_id: str, mod_list: List[str], total_size: float):
        """Save a user's mod list upload"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_uploads (user_id, server_id, upload_time, mod_list, total_size)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, server_id, int(time.time()), json.dumps(mod_list), total_size))
            conn.commit()
    
    def get_last_upload(self, user_id: str, server_id: str) -> Optional[Dict]:
        """Get the last upload for a user in a specific server"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT mod_list, total_size, upload_time FROM user_uploads
                WHERE user_id = ? AND server_id = ?
                ORDER BY upload_time DESC
                LIMIT 1
            ''', (user_id, server_id))
            
            result = cursor.fetchone()
            if result:
                return {
                    'mod_list': json.loads(result[0]),
                    'total_size': result[1],
                    'upload_time': result[2]
                }
            return None
    
    def save_mod_size(self, mod_id: str, size_gb: float):
        """Save mod size information"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO mod_sizes (mod_id, size_gb, last_updated)
                VALUES (?, ?, ?)
            ''', (mod_id, size_gb, int(time.time())))
            conn.commit()
    
    def get_mod_size(self, mod_id: str) -> Optional[float]:
        """Get cached mod size"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT size_gb FROM mod_sizes WHERE mod_id = ?
            ''', (mod_id,))
            
            result = cursor.fetchone()
            return result[0] if result else None
    
    def save_bot_message(self, channel_id: str, message_id: str, user_id: str, server_id: str, message_type: str = "modlist"):
        """Save a bot message ID for later cleanup"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bot_messages (channel_id, message_id, user_id, server_id, message_type, created_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (channel_id, message_id, user_id, server_id, message_type, int(time.time())))
            conn.commit()
    
    def get_bot_messages_for_channel(self, channel_id: str, message_type: str = "modlist") -> List[Tuple[str, str]]:
        """Get bot message IDs for a specific channel and type"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT message_id, user_id FROM bot_messages
                WHERE channel_id = ? AND message_type = ?
                ORDER BY created_time DESC
            ''', (channel_id, message_type))
            
            return cursor.fetchall()
    
    def delete_bot_message(self, message_id: str):
        """Delete a bot message record from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM bot_messages WHERE message_id = ?
            ''', (message_id,))
            conn.commit()
    
    def cleanup_old_bot_messages(self, max_age: int = 86400):  # 24 hours default
        """Clean up old bot message records"""
        cutoff_time = int(time.time()) - max_age
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM bot_messages WHERE created_time < ?
            ''', (cutoff_time,))
            conn.commit()
    
    def cleanup_old_cache(self, max_age: int = 2592000):  # 30 days default
        """Clean up old cache entries"""
        cutoff_time = int(time.time()) - max_age
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM mod_cache WHERE last_updated < ?
            ''', (cutoff_time,))
            cursor.execute('''
                DELETE FROM mod_sizes WHERE last_updated < ?
            ''', (cutoff_time,))
            conn.commit()
    
    def save_active_mod_list(self, list_id: str, user_id: int, guild_id: Optional[int], mods: List[Dict], download_url: Optional[str]):
        """Save an active mod list to the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO active_mod_lists 
                (list_id, user_id, guild_id, mods, download_url, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                list_id,
                str(user_id),
                str(guild_id) if guild_id else None,
                json.dumps(mods),
                download_url,
                int(time.time())
            ))
            conn.commit()
    
    def get_active_mod_list(self, list_id: str) -> Optional[Dict]:
        """Get an active mod list from the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, guild_id, mods, download_url, timestamp
                FROM active_mod_lists
                WHERE list_id = ?
            ''', (list_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'user_id': int(result[0]),
                    'guild_id': int(result[1]) if result[1] else None,
                    'mods': json.loads(result[2]),
                    'download_url': result[3],
                    'timestamp': result[4]
                }
            return None
    
    def get_recent_mod_list(self, user_id: int, guild_id: Optional[int]) -> Optional[Tuple[str, Dict]]:
        """Get the most recent mod list for a user in a guild"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT list_id, user_id, guild_id, mods, download_url, timestamp
                FROM active_mod_lists
                WHERE user_id = ? AND (guild_id = ? OR guild_id IS NULL)
                ORDER BY timestamp DESC
                LIMIT 1
            ''', (str(user_id), str(guild_id) if guild_id else None))
            
            result = cursor.fetchone()
            if result:
                return (result[0], {
                    'user_id': int(result[1]),
                    'guild_id': int(result[2]) if result[2] else None,
                    'mods': json.loads(result[3]),
                    'download_url': result[4],
                    'timestamp': result[5]
                })
            return None
    
    def cleanup_old_mod_lists(self, max_age: int = 86400):  # 24 hours default
        """Clean up old mod lists"""
        cutoff_time = int(time.time()) - max_age
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM active_mod_lists WHERE timestamp < ?
            ''', (cutoff_time,))
            conn.commit()
    
    def refresh_mod_list(self, list_id: str) -> bool:
        """Refresh the timestamp of a mod list to keep it active"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # First check if the mod list exists
            cursor.execute('SELECT COUNT(*) FROM active_mod_lists WHERE list_id = ?', (list_id,))
            if cursor.fetchone()[0] == 0:
                return False
                
            # Update the timestamp
            cursor.execute('''
                UPDATE active_mod_lists
                SET timestamp = ?
                WHERE list_id = ?
            ''', (int(time.time()), list_id))
            conn.commit()
            return True