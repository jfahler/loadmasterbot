from typing import List, Dict, Set, Tuple
from config import CDLC_COMPAT_MODS
from steam_workshop import SteamWorkshopAPI
from database import ModDatabase

class ModAnalyzer:
    def __init__(self, steam_api: SteamWorkshopAPI, database: ModDatabase):
        self.steam_api = steam_api
        self.database = database

    def check_cdlc_compatibility(
        self,
        mod_ids: List[str],
        mod_info: Dict[str, Dict] = {},
    ) -> Dict:
        """Check if any mods require CDLC."""
        detected_cdlc = []
        mods_require_cdlc = []
        mod_set = set(mod_ids)

        # Check if any CDLC mods are present
        for cdlc_key, cdlc_info in CDLC_COMPAT_MODS.items():
            cdlc_mods_present = any(str(mod_id) in mod_set for mod_id in cdlc_info['required_mods'])
            if cdlc_mods_present:
                detected_cdlc.append(cdlc_info['name'])

        # Check if any mods require CDLC (by name, description, or required_items)
        if mod_info:
            for mod in mod_info.values():
                # Check mod name and description for CDLC references
                for cdlc_key, cdlc_info in CDLC_COMPAT_MODS.items():
                    cdlc_name = cdlc_info['name'].lower()
                    if cdlc_name in mod['name'].lower() or (mod.get('description') and cdlc_name in mod['description'].lower()):
                        if cdlc_info['name'] not in detected_cdlc:
                            mods_require_cdlc.append(cdlc_info['name'])
                
                # Check required_items for CDLC names
                required_items = mod.get('required_items', [])
                for required in required_items:
                    if not required.isdigit():  # It's a CDLC name, not a mod ID
                        required_lower = required.lower()
                        for cdlc_key, cdlc_info in CDLC_COMPAT_MODS.items():
                            cdlc_name = cdlc_info['name'].lower()
                            if (required_lower in cdlc_name or 
                                cdlc_name in required_lower or
                                any(keyword in cdlc_name for keyword in required_lower.split()) or
                                any(keyword in required_lower for keyword in cdlc_name.split())):
                                if cdlc_info['name'] not in detected_cdlc and cdlc_info['name'] not in mods_require_cdlc:
                                    mods_require_cdlc.append(cdlc_info['name'])
                
                # Check enhanced DLC requirements
                dlc_requirements = mod.get('dlc_requirements', {})
                for cdlc_key, cdlc_info in CDLC_COMPAT_MODS.items():
                    cdlc_name = cdlc_info['name'].lower()
                    
                    # Check required DLC
                    if cdlc_name in dlc_requirements.get('required', []):
                        if cdlc_info['name'] not in detected_cdlc and cdlc_info['name'] not in mods_require_cdlc:
                            mods_require_cdlc.append(cdlc_info['name'])
                    
                    # Check optional DLC (treat as potential requirement)
                    elif cdlc_name in dlc_requirements.get('optional', []):
                        if cdlc_info['name'] not in detected_cdlc and cdlc_info['name'] not in mods_require_cdlc:
                            mods_require_cdlc.append(cdlc_info['name'])

        return {
            'detected_cdlc': detected_cdlc,
            'mods_require_cdlc': list(set(mods_require_cdlc)),
            'has_issues': len(mods_require_cdlc) > 0
        }
    
    def check_workshop_requirements(self, mod_info: Dict[str, Dict]) -> Dict:
        """Check if all required workshop items are included in the mod list"""
        all_mod_ids = set(mod_info.keys())
        missing_requirements = []
        all_requirements_met = True
        
        for mod_id, info in mod_info.items():
            required_items = info.get('required_items', [])
            for required in required_items:
                # Only check for actual mod IDs, not CDLC names
                if required.isdigit():
                    # It's a mod ID
                    if required not in all_mod_ids:
                        missing_requirements.append({
                            'mod_name': info['name'],
                            'required_item': required,
                            'type': 'mod'
                        })
                        all_requirements_met = False
                # Skip CDLC names - they're handled in CDLC compatibility check
        
        return {
            'all_requirements_met': all_requirements_met,
            'missing_requirements': missing_requirements
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
        compatibility_check = self.check_cdlc_compatibility(mod_ids, mod_info)
        
        # Check workshop requirements
        workshop_requirements = self.check_workshop_requirements(mod_info)
        
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
            'workshop_requirements': workshop_requirements,
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

    def format_mod_list_for_display_3columns(self, mod_info: Dict[str, Dict], max_display: int = 30) -> Dict:
        """Format mod list for Discord display in a clean list format"""
        mod_list = list(mod_info.values())
        
        # Sort by size (largest first) if available
        mod_list.sort(key=lambda x: x.get('size_gb', 0) or 0, reverse=True)
        
        # Prepare display lists
        display_mods = mod_list[:max_display]
        remaining_mods = mod_list[max_display:] if len(mod_list) > max_display else []
        
        # Format display text as a clean list
        display_text = ""
        for i, mod in enumerate(display_mods, 1):
            name = mod['name']
            size_text = f"{mod.get('size_gb', 'Unknown'):.1f}GB" if mod.get('size_gb') else "Unknown"
            # Truncate very long names
            if len(name) > 50:
                name = name[:47] + "..."
            display_text += f"{i:2d}. **{name}** ({size_text})\n"
        
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

    def format_compact_mod_list(self, mod_info: Dict[str, Dict], max_display: int = 50) -> Dict:
        """Format mod list for Discord display in a compact format"""
        mod_list = list(mod_info.values())
        
        # Sort by size (largest first) if available
        mod_list.sort(key=lambda x: x.get('size_gb', 0) or 0, reverse=True)
        
        # Prepare display lists
        display_mods = mod_list[:max_display]
        remaining_mods = mod_list[max_display:] if len(mod_list) > max_display else []
        
        # Format display text in a more compact format
        display_text = ""
        for i, mod in enumerate(display_mods, 1):
            name = mod['name']
            size_text = f"{mod.get('size_gb', 'Unknown'):.1f}GB" if mod.get('size_gb') else "Unknown"
            # Truncate very long names more aggressively
            if len(name) > 35:
                name = name[:32] + "..."
            display_text += f"{i:2d}. {name} ({size_text})\n"
        
        if remaining_mods:
            display_text += f"\n... and {len(remaining_mods)} more mods"
        
        return {
            'display_text': display_text,
            'total_mods': len(mod_list),
            'displayed_count': len(display_mods),
            'remaining_count': len(remaining_mods),
            'all_mods': mod_list
        }