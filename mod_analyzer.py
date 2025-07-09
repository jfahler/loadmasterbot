from typing import List, Dict, Set, Tuple
from config import CDLC_COMPAT_MODS
from steam_workshop import SteamWorkshopAPI
from database import ModDatabase

class ModAnalyzer:
    def __init__(self, steam_api: SteamWorkshopAPI, database: ModDatabase):
        self.steam_api = steam_api
        self.database = database
    
    def check_cdlc_compatibility(self, mod_ids: List[str]) -> Dict:
        """Check for missing CDLC compatibility mods"""
        missing_compat = []
        detected_cdlc = []
        
        # Convert mod_ids to set for faster lookup
        mod_set = set(mod_ids)
        
        for cdlc_key, cdlc_info in CDLC_COMPAT_MODS.items():
            # Check if any CDLC mods are present
            cdlc_mods_present = any(str(mod_id) in mod_set for mod_id in cdlc_info['required_mods'])
            
            if cdlc_mods_present:
                detected_cdlc.append(cdlc_info['name'])
                
                # Check if compat mod is missing
                compat_mod_id = str(cdlc_info['compat_mod'])
                if compat_mod_id not in mod_set:
                    missing_compat.append({
                        'cdlc_name': cdlc_info['name'],
                        'compat_name': cdlc_info['compat_name'],
                        'compat_mod_id': compat_mod_id,
                        'steam_url': cdlc_info['steam_url']
                    })
        
        return {
            'missing_compat_mods': missing_compat,
            'detected_cdlc': detected_cdlc,
            'has_issues': len(missing_compat) > 0
        }
    
    def compare_mod_lists(self, current_mods: List[str], previous_mods: List[str]) -> Dict:
        """Compare current mod list with previous upload"""
        current_set = set(current_mods)
        previous_set = set(previous_mods)
        
        added_mods = list(current_set - previous_set)
        removed_mods = list(previous_set - current_set)
        unchanged_mods = list(current_set & previous_set)
        
        return {
            'added_mods': added_mods,
            'removed_mods': removed_mods,
            'unchanged_mods': unchanged_mods,
            'total_added': len(added_mods),
            'total_removed': len(removed_mods),
            'total_unchanged': len(unchanged_mods),
            'has_changes': len(added_mods) > 0 or len(removed_mods) > 0
        }
    
    async def analyze_mod_list(self, html_content: str, user_id: str, server_id: str) -> Dict:
        """Complete analysis of a mod list"""
        # Parse mod IDs from HTML
        mod_ids = self.steam_api.parse_html_modlist(html_content)
        
        # Get mod information
        mod_info = await self.steam_api.get_multiple_mod_info(mod_ids)
        
        # Check CDLC compatibility
        compatibility_check = self.check_cdlc_compatibility(mod_ids)
        
        # Get previous upload for comparison
        last_upload = self.database.get_last_upload(user_id, server_id)
        comparison = None
        if last_upload:
            comparison = self.compare_mod_lists(mod_ids, last_upload['mod_list'])
        
        # Estimate total size
        size_estimate = await self.steam_api.estimate_total_size(mod_ids)
        
        # Save to database
        self.database.save_user_upload(user_id, server_id, mod_ids, size_estimate['total_size_gb'])
        
        # Cache mod information
        for mod_id, info in mod_info.items():
            size_gb = info.get('size_gb')
            if size_gb is not None:
                self.database.cache_mod_info(mod_id, info['name'], size_gb)
                self.database.save_mod_size(mod_id, size_gb)
            else:
                self.database.cache_mod_info(mod_id, info['name'], 0.0)
        
        return {
            'mod_ids': mod_ids,
            'mod_info': mod_info,
            'compatibility_check': compatibility_check,
            'comparison': comparison,
            'size_estimate': size_estimate,
            'total_mods': len(mod_ids)
        }
    
    def categorize_mods(self, mod_info: Dict[str, Dict]) -> Dict[str, List[Dict]]:
        """Categorize mods by type based on name patterns"""
        categories = {
            'maps': [],
            'weapons': [],
            'vehicles': [],
            'units': [],
            'compatibility': [],
            'other': []
        }
        
        for mod_id, info in mod_info.items():
            name = info['name'].lower()
            
            # Simple categorization based on common keywords
            if any(keyword in name for keyword in ['map', 'terrain', 'island', 'world']):
                categories['maps'].append(info)
            elif any(keyword in name for keyword in ['weapon', 'gun', 'rifle', 'pistol', 'ammo']):
                categories['weapons'].append(info)
            elif any(keyword in name for keyword in ['vehicle', 'car', 'tank', 'helicopter', 'plane', 'aircraft']):
                categories['vehicles'].append(info)
            elif any(keyword in name for keyword in ['unit', 'soldier', 'infantry', 'uniform']):
                categories['units'].append(info)
            elif any(keyword in name for keyword in ['compat', 'compatibility', 'patch']):
                categories['compatibility'].append(info)
            else:
                categories['other'].append(info)
        
        return categories
    
    def format_mod_list_for_display(self, mod_info: Dict[str, Dict], max_display: int = 10) -> Dict:
        """Format mod list for Discord display"""
        mod_list = list(mod_info.values())
        
        # Sort by size (largest first) if available
        mod_list.sort(key=lambda x: x.get('size_gb', 0) or 0, reverse=True)
        
        # Prepare display lists
        display_mods = mod_list[:max_display]
        remaining_mods = mod_list[max_display:] if len(mod_list) > max_display else []
        
        # Format display text
        display_text = ""
        for i, mod in enumerate(display_mods, 1):
            size_text = f" ({mod.get('size_gb', 'Unknown'):.1f}GB)" if mod.get('size_gb') else ""
            display_text += f"{i}. **{mod['name']}**{size_text}\n"
        
        if remaining_mods:
            display_text += f"\n... and {len(remaining_mods)} more mods"
        
        return {
            'display_text': display_text,
            'total_mods': len(mod_list),
            'displayed_count': len(display_mods),
            'remaining_count': len(remaining_mods),
            'all_mods': mod_list
        } 

    def get_last_analysis(self, user_id: str, server_id: str):
        """Retrieve the last analysis for a user in a server."""
        last_upload = self.database.get_last_upload(user_id, server_id)
        if not last_upload:
            return None
        mod_ids = last_upload['mod_list']
        # Synchronously get mod info for debug (assume this is for debug, not production)
        # In production, this should be async, but for debug command, we can use cached info
        mod_info = {}
        for mod_id in mod_ids:
            cached = self.database.get_cached_mod_info(mod_id)
            if cached:
                mod_info[mod_id] = {
                    'id': mod_id,
                    'name': cached['mod_name'],
                    'size_gb': cached['mod_size']
                }
            else:
                mod_info[mod_id] = {
                    'id': mod_id,
                    'name': f"Mod {mod_id}",
                    'size_gb': None
                }
        return {
            'mod_info': list(mod_info.values()),
            'total_mods': len(mod_ids)
        } 