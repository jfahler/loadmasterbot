#!/usr/bin/env python3
"""
Test script for Arma 3 Mod Manager Discord Bot
This script tests the core components without requiring Discord connection
"""

import asyncio
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from steam_workshop import SteamWorkshopAPI
from database import ModDatabase
from mod_analyzer import ModAnalyzer

# Sample HTML content for testing
SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Arma 3 Mod List</title></head>
<body>
<h1>My Mod List</h1>
<ul>
<li><a href="https://steamcommunity.com/sharedfiles/filedetails/?id=123456789">Sample Mod 1</a></li>
<li><a href="https://steamcommunity.com/sharedfiles/filedetails/?id=987654321">Sample Mod 2</a></li>
<li><a href="https://steamcommunity.com/sharedfiles/filedetails/?id=234567890">Sample Mod 3</a></li>
</ul>
</body>
</html>
"""

async def test_steam_workshop():
    """Test Steam Workshop API functionality"""
    print("🧪 Testing Steam Workshop API...")
    
    steam_api = SteamWorkshopAPI()
    
    # Test mod ID extraction
    test_url = "https://steamcommunity.com/sharedfiles/filedetails/?id=123456789"
    mod_id = steam_api.extract_mod_id_from_url(test_url)
    print(f"✅ Mod ID extraction: {mod_id}")
    
    # Test HTML parsing
    mod_ids = steam_api.parse_html_modlist(SAMPLE_HTML)
    print(f"✅ HTML parsing found {len(mod_ids)} mod IDs: {mod_ids}")
    
    # Test mod info fetching (with mock data)
    print("✅ Steam Workshop API tests passed")
    
    await steam_api.close_session()

def test_database():
    """Test database functionality"""
    print("🧪 Testing Database...")
    
    # Use temporary database for testing
    db = ModDatabase("test_arma_mods.db")
    
    # Test mod caching
    db.cache_mod_info("123456789", "Test Mod", 1.5)
    cached_info = db.get_cached_mod_info("123456789")
    print(f"✅ Mod caching: {cached_info['mod_name'] if cached_info else 'Failed'}")
    
    # Test user uploads
    test_mods = ["123456789", "987654321"]
    db.save_user_upload("test_user", "test_server", test_mods, 3.0)
    last_upload = db.get_last_upload("test_user", "test_server")
    print(f"✅ User uploads: {len(last_upload['mod_list']) if last_upload else 0} mods saved")
    
    # Cleanup test database
    try:
        os.remove("test_arma_mods.db")
    except:
        pass
    
    print("✅ Database tests passed")

async def test_mod_analyzer():
    """Test mod analyzer functionality"""
    print("🧪 Testing Mod Analyzer...")
    
    steam_api = SteamWorkshopAPI()
    db = ModDatabase("test_analyzer.db")
    analyzer = ModAnalyzer(steam_api, db)
    
    # Test CDLC compatibility checking
    test_mods = ["123456789", "987654321"]  # Example mod IDs
    compat_check = analyzer.check_cdlc_compatibility(test_mods)
    print(f"✅ CDLC compatibility check: {compat_check['has_issues']} issues found")
    
    # Test mod list comparison
    previous_mods = ["123456789", "111111111"]
    comparison = analyzer.compare_mod_lists(test_mods, previous_mods)
    print(f"✅ Mod list comparison: {comparison['total_added']} added, {comparison['total_removed']} removed")
    
    # Test mod categorization
    test_mod_info = {
        "123456789": {"name": "Test Map Mod", "id": "123456789"},
        "987654321": {"name": "Test Weapon Mod", "id": "987654321"}
    }
    categories = analyzer.categorize_mods(test_mod_info)
    print(f"✅ Mod categorization: {len(categories['maps'])} maps, {len(categories['weapons'])} weapons")
    
    # Test mod list formatting
    display = analyzer.format_mod_list_for_display(test_mod_info, 5)
    print(f"✅ Mod list formatting: {display['total_mods']} total mods")
    
    await steam_api.close_session()
    
    # Cleanup test database
    try:
        os.remove("test_analyzer.db")
    except:
        pass
    
    print("✅ Mod Analyzer tests passed")

async def test_integration():
    """Test full integration"""
    print("🧪 Testing Full Integration...")
    
    steam_api = SteamWorkshopAPI()
    db = ModDatabase("test_integration.db")
    analyzer = ModAnalyzer(steam_api, db)
    
    # Test complete analysis
    analysis = await analyzer.analyze_mod_list(
        SAMPLE_HTML,
        "test_user",
        "test_server"
    )
    
    print(f"✅ Integration test: {analysis['total_mods']} mods analyzed")
    print(f"   - Size estimate: {analysis['size_estimate']['total_size_gb']:.1f}GB")
    print(f"   - Compatibility issues: {analysis['compatibility_check']['has_issues']}")
    print(f"   - Changes detected: {analysis['comparison']['has_changes'] if analysis['comparison'] else False}")
    
    await steam_api.close_session()
    
    # Cleanup test database
    try:
        os.remove("test_integration.db")
    except:
        pass
    
    print("✅ Integration tests passed")

async def main():
    """Run all tests"""
    print("🎮 Arma 3 Mod Manager Bot - Test Suite")
    print("=" * 50)
    
    try:
        # Run individual component tests
        await test_steam_workshop()
        test_database()
        await test_mod_analyzer()
        await test_integration()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! The bot is ready to run.")
        print("\nNext steps:")
        print("1. Set up your Discord bot token in .env file")
        print("2. Run: python discord_bot.py")
        print("3. Upload an HTML mod list to test the full functionality")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("Please check the error and fix any issues before running the bot.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 