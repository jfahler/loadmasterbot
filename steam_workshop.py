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
                    
                    # Extract mod size from workshop page first, then description
                    mod_size = self.extract_file_size_from_workshop(soup)
                    if mod_size is None:
                        mod_size = self.extract_mod_size_from_description(soup)
                    
                    # If not found in description, try to get from known sizes
                    if mod_size is None:
                        mod_size = KNOWN_MOD_SIZES.get(mod_id)
                    
                    # Extract required items and DLC requirements
                    required_items = self.extract_required_items(soup)
                    dlc_requirements = self.extract_dlc_requirements(soup)
                    
                    mod_info = {
                        'id': mod_id,
                        'name': mod_name,
                        'size_gb': mod_size,
                        'url': url,
                        'required_items': required_items,
                        'dlc_requirements': dlc_requirements
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
        
        # Common size patterns - more comprehensive
        size_patterns = [
            r'(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)',
            r'Size[:\s]*(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)',
            r'File[:\s]*(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)',
            r'Download[:\s]*(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)',
            r'(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)\s*required',
            r'(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)\s*needed',
        ]
        
        for pattern in size_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                try:
                    size_value = float(match.group(1).replace(',', ''))
                    unit = match.group(2).upper()
                    if unit in ['KB', 'KILOBYTES', 'KILOBYTE']:
                        return size_value / (1024 * 1024)  # Convert KB to GB
                    elif unit in ['MB', 'MEGABYTES', 'MEGABYTE']:
                        return size_value / 1024  # Convert MB to GB
                    elif unit in ['GB', 'GIGABYTES', 'GIGABYTE']:
                        return size_value
                except ValueError:
                    continue
        
        return None

    def extract_required_items(self, soup: BeautifulSoup) -> List[str]:
        """Extract required items (mods/CDLC) from Steam Workshop page"""
        required_items = []
        
        # Look for "Required Items" section
        required_section = soup.find('div', class_='requiredItems')
        if required_section:
            links = required_section.find_all('a', href=True)
            for link in links:
                href = link['href']
                mod_id = self.extract_mod_id_from_url(href)
                if mod_id:
                    required_items.append(mod_id)
        
        # Look for "Required Items" in different possible locations
        for selector in ['div.requiredItems', 'div.workshopItemDetails', 'div.workshopItemDetailsRight']:
            section = soup.select_one(selector)
            if section:
                # Look for CDLC mentions in the required items section
                section_text = section.get_text().lower()
                cdlc_keywords = [
                    'global mobilization', 's.o.g. prairie fire', 'csla iron curtain',
                    'spearhead 1944', 'western sahara', 'reaction forces', 'expeditionary forces',
                    'gm', 'sog', 'csla', 'spearhead', 'western sahara', 'reaction forces', 'expeditionary forces'
                ]
                
                for keyword in cdlc_keywords:
                    if keyword in section_text:
                        required_items.append(keyword)
        
        # Enhanced description scanning for DLC requirements
        description = soup.get_text().lower()
        
        # Look for specific DLC requirement patterns
        dlc_patterns = [
            r'requires?\s+(?:the\s+)?(?:cdlc\s+)?(?:arma\s+3\s+)?(?:dlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(?:cdlc|dlc)\s+(?:required|needed|dependency).*?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)\s+(?:cdlc|dlc)\s+(?:required|needed)',
            r'compatible\s+with\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
        ]
        
        for pattern in dlc_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                if match not in required_items:
                    required_items.append(match.lower())
        
        # Also check for general CDLC mentions that might indicate requirements
        general_cdlc_patterns = [
            r'requires?\s+(?:a\s+)?(?:cdlc|dlc)',
            r'(?:cdlc|dlc)\s+(?:required|needed|dependency)',
            r'this\s+mod\s+(?:requires|needs)\s+(?:a\s+)?(?:cdlc|dlc)',
        ]
        
        for pattern in general_cdlc_patterns:
            if re.search(pattern, description, re.IGNORECASE):
                # If we find general CDLC requirements, look for specific CDLC names
                cdlc_names = [
                    'global mobilization', 's.o.g. prairie fire', 'csla iron curtain',
                    'spearhead 1944', 'western sahara', 'reaction forces', 'expeditionary forces'
                ]
                for cdlc_name in cdlc_names:
                    if cdlc_name in description and cdlc_name not in required_items:
                        required_items.append(cdlc_name)
                break
        
        return required_items
    
    def extract_dlc_requirements(self, soup: BeautifulSoup) -> Dict[str, List[str]]:
        """Extract DLC requirements with distinction between required and optional"""
        dlc_requirements = {
            'required': [],
            'optional': [],
            'compatible': []
        }
        
        description = soup.get_text().lower()
        
        # CDLC names to look for
        cdlc_names = [
            'global mobilization', 's.o.g. prairie fire', 'csla iron curtain',
            'spearhead 1944', 'western sahara', 'reaction forces', 'expeditionary forces'
        ]
        
        # Patterns that indicate REQUIRED DLC
        required_patterns = [
            r'requires?\s+(?:the\s+)?(?:cdlc\s+)?(?:arma\s+3\s+)?(?:dlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(?:cdlc|dlc)\s+(?:required|needed|dependency).*?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)\s+(?:cdlc|dlc)\s+(?:required|needed)',
            r'this\s+mod\s+(?:requires|needs)\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'mandatory\s+(?:cdlc|dlc).*?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(?:you\s+need|player\s+needs?)\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(?:must\s+have|must\s+own)\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
        ]
        
        # Patterns that indicate OPTIONAL DLC
        optional_patterns = [
            r'optional\s+(?:cdlc|dlc).*?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(?:cdlc|dlc)\s+(?:optional|recommended).*?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'recommended\s+(?:cdlc|dlc).*?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(?:you\s+can|players?\s+can)\s+(?:also\s+)?(?:use|have)\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'(?:works\s+better\s+with|enhanced\s+by)\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
        ]
        
        # Patterns that indicate COMPATIBLE DLC
        compatible_patterns = [
            r'compatible\s+with\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'works\s+with\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
            r'supports?\s+(?:the\s+)?(?:cdlc\s+)?(global mobilization|s\.o\.g\. prairie fire|csla iron curtain|spearhead 1944|western sahara|reaction forces|expeditionary forces)',
        ]
        
        # Check for required DLC
        for pattern in required_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                cdlc_name = match.lower()
                if cdlc_name not in dlc_requirements['required']:
                    dlc_requirements['required'].append(cdlc_name)
        
        # Check for optional DLC
        for pattern in optional_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                cdlc_name = match.lower()
                if cdlc_name not in dlc_requirements['optional'] and cdlc_name not in dlc_requirements['required']:
                    dlc_requirements['optional'].append(cdlc_name)
        
        # Check for compatible DLC
        for pattern in compatible_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                cdlc_name = match.lower()
                if (cdlc_name not in dlc_requirements['compatible'] and 
                    cdlc_name not in dlc_requirements['optional'] and 
                    cdlc_name not in dlc_requirements['required']):
                    dlc_requirements['compatible'].append(cdlc_name)
        
        return dlc_requirements

    def extract_file_size_from_workshop(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract actual file size from Steam Workshop page"""
        # Look for file size in various locations on the workshop page
        size_selectors = [
            'div.workshopItemDetails',
            'div.workshopItemDetailsRight',
            'div.workshopItemDetailsLeft',
            'div.workshopItemDetailsHeader',
            'div.workshopItemDetailsHeaderRight'
        ]
        
        for selector in size_selectors:
            size_elem = soup.select_one(selector)
            if size_elem:
                size_text = size_elem.get_text()
                # Look for size patterns like "1.2 GB", "1,200 MB", "1.2GB", "108.346 KB", etc.
                size_patterns = [
                    r'(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)',
                    r'Size[:\s]*(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)',
                    r'File[:\s]*(\d+(?:,\d+)?(?:\.\d+)?)\s*(GB|MB|KB|Gigabytes?|Megabytes?|Kilobytes?)',
                ]
                
                for pattern in size_patterns:
                    size_match = re.search(pattern, size_text, re.IGNORECASE)
                    if size_match:
                        try:
                            size_value = float(size_match.group(1).replace(',', ''))
                            unit = size_match.group(2).upper()
                            if unit in ['KB', 'KILOBYTES', 'KILOBYTE']:
                                return size_value / (1024 * 1024)  # Convert KB to GB
                            elif unit in ['MB', 'MEGABYTES', 'MEGABYTE']:
                                return size_value / 1024  # Convert MB to GB
                            elif unit in ['GB', 'GIGABYTES', 'GIGABYTE']:
                                return size_value
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