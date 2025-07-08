import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
from typing import Dict, Optional, List
import time
from config import STEAM_WORKSHOP_BASE_URL, STEAM_API_BASE_URL, KNOWN_MOD_SIZES

class SteamWorkshopAPI:
    def __init__(self):
        self.session = None
        self.cache = {}
        self.cache_duration = 86400  # 24 hours
    
    async def get_session(self):
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def extract_mod_id_from_url(self, url: str) -> Optional[str]:
        """Extract mod ID from Steam Workshop URL"""
        pattern = r'filedetails/\?id=(\d+)'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    
    async def get_mod_info(self, mod_id: str) -> Optional[Dict]:
        """Get mod information from Steam Workshop"""
        # Check cache first
        cache_key = f"mod_{mod_id}"
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                return cached_data
        
        session = await self.get_session()
        url = f"{STEAM_WORKSHOP_BASE_URL}{mod_id}"
        
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Extract mod name
                    title_elem = soup.find('div', class_='workshopItemTitle')
                    mod_name = title_elem.get_text(strip=True) if title_elem else f"Mod {mod_id}"
                    
                    # Extract mod size from description
                    mod_size = self.extract_mod_size_from_description(soup)
                    
                    # If not found in description, try to get from known sizes
                    if mod_size is None:
                        mod_size = KNOWN_MOD_SIZES.get(mod_id)
                    
                    mod_info = {
                        'id': mod_id,
                        'name': mod_name,
                        'size_gb': mod_size,
                        'url': url
                    }
                    
                    # Cache the result
                    self.cache[cache_key] = (mod_info, time.time())
                    
                    return mod_info
                else:
                    print(f"Failed to fetch mod {mod_id}: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            print(f"Error fetching mod {mod_id}: {e}")
            return None
    
    def extract_mod_size_from_description(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract mod size from Steam Workshop page description"""
        # Look for size patterns in the description
        description = soup.get_text()
        
        # Common size patterns
        size_patterns = [
            r'(\d+(?:\.\d+)?)\s*GB',
            r'(\d+(?:\.\d+)?)\s*Gigabytes',
            r'Size:\s*(\d+(?:\.\d+)?)\s*GB',
            r'(\d+(?:\.\d+)?)\s*GB\s*required',
        ]
        
        for pattern in size_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    async def get_multiple_mod_info(self, mod_ids: List[str]) -> Dict[str, Dict]:
        """Get information for multiple mods concurrently"""
        tasks = [self.get_mod_info(mod_id) for mod_id in mod_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        mod_info_dict = {}
        for i, result in enumerate(results):
            if isinstance(result, dict):
                mod_info_dict[mod_ids[i]] = result
            else:
                # Fallback for failed requests
                mod_info_dict[mod_ids[i]] = {
                    'id': mod_ids[i],
                    'name': f"Mod {mod_ids[i]}",
                    'size_gb': KNOWN_MOD_SIZES.get(mod_ids[i]),
                    'url': f"{STEAM_WORKSHOP_BASE_URL}{mod_ids[i]}"
                }
        
        return mod_info_dict
    
    def parse_html_modlist(self, html_content: str) -> List[str]:
        """Parse HTML content to extract mod IDs"""
        soup = BeautifulSoup(html_content, 'html.parser')
        mod_ids = []
        
        # Look for Steam Workshop links
        links = soup.find_all('a', href=True)
        for link in links:
            href = link['href']
            mod_id = self.extract_mod_id_from_url(href)
            if mod_id and mod_id not in mod_ids:
                mod_ids.append(mod_id)
        
        # Also look for mod ID patterns in text
        text_content = soup.get_text()
        id_pattern = r'(\d{9,})'  # Steam Workshop IDs are typically 9+ digits
        matches = re.findall(id_pattern, text_content)
        
        for match in matches:
            if match not in mod_ids:
                mod_ids.append(match)
        
        return mod_ids
    
    async def estimate_total_size(self, mod_ids: List[str]) -> Dict:
        """Estimate total size of mod list"""
        mod_info = await self.get_multiple_mod_info(mod_ids)
        
        total_size = 0.0
        known_sizes = 0
        unknown_sizes = 0
        
        for mod_id, info in mod_info.items():
            if info.get('size_gb'):
                total_size += info['size_gb']
                known_sizes += 1
            else:
                unknown_sizes += 1
        
        # Estimate unknown sizes (average of known sizes or default 1.5GB)
        if known_sizes > 0:
            avg_size = total_size / known_sizes
        else:
            avg_size = 1.5  # Default estimate
        
        estimated_unknown = unknown_sizes * avg_size
        total_estimated = total_size + estimated_unknown
        
        return {
            'total_size_gb': total_estimated,
            'known_size_gb': total_size,
            'unknown_count': unknown_sizes,
            'known_count': known_sizes,
            'average_size_gb': avg_size
        } 