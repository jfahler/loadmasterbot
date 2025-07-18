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