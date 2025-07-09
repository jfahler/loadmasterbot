import discord
from discord.ext import commands
import asyncio
import io
import tempfile
import os
from typing import Optional
import time

from config import DISCORD_TOKEN, BOT_PREFIX, MAX_MODS_PER_PAGE, MESSAGE_DELETE_DELAY
from database import ModDatabase
from steam_workshop import SteamWorkshopAPI
from mod_analyzer import ModAnalyzer

class ArmaModBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        
        super().__init__(command_prefix=BOT_PREFIX, intents=intents)
        
        # Initialize components
        self.database = ModDatabase()
        self.steam_api = SteamWorkshopAPI()
        self.analyzer = ModAnalyzer(self.steam_api, self.database)
        
        # Store active mod lists for button interactions
        self.active_mod_lists = {}
    
    async def setup_hook(self):
        """Setup hook for bot initialization"""
        await self.add_cog(ModCommands(self))
    
    async def on_ready(self):
        """Called when bot is ready"""
        print(f'{self.user} has connected to Discord!')
        print(f'Bot is in {len(self.guilds)} guilds')
        
        # Set bot status
        await self.change_presence(activity=discord.Game(name="Arma 3 Mod Manager"))
    
    async def close(self):
        """Cleanup when bot shuts down"""
        await self.steam_api.close_session()
        await super().close()

class ModCommands(commands.Cog):
    def __init__(self, bot: ArmaModBot):
        self.bot = bot
    
    @commands.command(name='modlist', aliases=['ml', 'mods'])
    async def modlist(self, ctx: commands.Context):
        """Show help for modlist commands"""
        embed = discord.Embed(
            title="🎮 Arma 3 Mod Manager",
            description="Upload your Arma 3 mod list HTML file to analyze your mods!",
            color=0x00ff00
        )
        
        embed.add_field(
            name="📁 How to use",
            value="1. Export your mod list from Arma 3 Launcher\n"
                  "2. Upload the HTML file here\n"
                  "3. Use `/modlist upload` or just upload the file",
            inline=False
        )
        
        embed.add_field(
            name="🔍 What I'll check",
            value="• List all mods with names and sizes\n"
                  "• Check for missing CDLC compatibility mods\n"
                  "• Compare with your last upload\n"
                  "• Estimate total download size",
            inline=False
        )
        
        embed.add_field(
            name="📋 Commands",
            value="`!modlist` - Show this help\n"
                  "`!bothelp` - Show all commands",
            inline=False
        )
        
        embed.set_footer(text="Made for Arma 3 communities")
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle file uploads and commands, but prevent duplicate command processing."""
        if message.author.bot:
            return
        # If a file upload is handled, do NOT process commands
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.lower().endswith('.html'):
                    await self.handle_html_upload(message, attachment)
                    return  # Prevents double-processing
        # Only process commands if not handled above
        await self.bot.process_commands(message)
    
    async def handle_html_upload(self, message: discord.Message, attachment: discord.Attachment):
        """Handle HTML file upload"""
        # Send initial response
        loading_embed = discord.Embed(
            title="🔄 Processing Mod List",
            description="Downloading and analyzing your mod list...",
            color=0xffff00
        )
        loading_msg = await message.channel.send(embed=loading_embed)
        
        try:
            # Download the HTML file
            html_content = await attachment.read()
            html_text = html_content.decode('utf-8')
            
            # Analyze the mod list
            analysis = await self.bot.analyzer.analyze_mod_list(
                html_text, 
                str(message.author.id), 
                str(message.guild.id)
            )
            
            # Create and send the results
            await self.send_mod_analysis(message.channel, analysis, message.author)
            
            # Delete loading message
            await loading_msg.delete()
            
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error Processing Mod List",
                description=f"An error occurred while processing your mod list:\n```{str(e)}```",
                color=0xff0000
            )
            await loading_msg.edit(embed=error_embed)
    
    async def send_mod_analysis(self, channel, analysis: dict, user: discord.Member):
        """Send comprehensive mod analysis"""
        # Create main embed
        embed = discord.Embed(
            title="📋 Mod List Analysis",
            description=f"Analysis for {user.mention}'s mod list",
            color=0x00ff00
        )
        
        # Add mod count and size
        embed.add_field(
            name="📊 Summary",
            value=f"**Total Mods:** {analysis['total_mods']}\n"
                  f"**Estimated Size:** {analysis['size_estimate']['total_size_gb']:.1f}GB\n"
                  f"**Known Sizes:** {analysis['size_estimate']['known_count']} mods\n"
                  f"**Unknown Sizes:** {analysis['size_estimate']['unknown_count']} mods",
            inline=False
        )
        
        # Add compatibility warnings
        if analysis['compatibility_check']['has_issues']:
            compat_text = ""
            for missing in analysis['compatibility_check']['missing_compat_mods']:
                compat_text += f"⚠️ **{missing['cdlc_name']}** - Missing {missing['compat_name']}\n"
                compat_text += f"   [Download Here]({missing['steam_url']})\n\n"
            
            embed.add_field(
                name="⚠️ Missing Compatibility Mods",
                value=compat_text,
                inline=False
            )
            embed.color = 0xff6600  # Orange for warnings
        else:
            embed.add_field(
                name="✅ Compatibility Check",
                value="All detected CDLC have compatibility mods installed!",
                inline=False
            )
        
        # Add changes from previous upload
        if analysis['comparison'] and analysis['comparison']['has_changes']:
            changes_text = ""
            if analysis['comparison']['total_added'] > 0:
                changes_text += f"➕ **Added:** {analysis['comparison']['total_added']} mods\n"
            if analysis['comparison']['total_removed'] > 0:
                changes_text += f"➖ **Removed:** {analysis['comparison']['total_removed']} mods\n"
            
            embed.add_field(
                name="📈 Changes from Last Upload",
                value=changes_text,
                inline=False
            )
        
        # Format mod list for display
        mod_display = self.bot.analyzer.format_mod_list_for_display(
            analysis['mod_info'], 
            MAX_MODS_PER_PAGE
        )
        
        embed.add_field(
            name=f"📦 Mod List ({mod_display['displayed_count']}/{mod_display['total_mods']})",
            value=mod_display['display_text'],
            inline=False
        )
        
        # Store mod list for button interactions
        list_id = f"{user.id}_{int(time.time())}"
        self.bot.active_mod_lists[list_id] = {
            'mods': mod_display['all_mods'],
            'timestamp': time.time()
        }
        
        # Create view with buttons
        view = ModListView(list_id, mod_display['total_mods'])
        
        # Send the embed
        await channel.send(embed=embed, view=view)
        
        # Auto-delete after delay if in a lobby channel
        if 'lobby' in channel.name.lower():
            await asyncio.sleep(MESSAGE_DELETE_DELAY)
            try:
                await channel.last_message.delete()
            except:
                pass
    
    @commands.command(name='bothelp', aliases=['bh'])
    async def bothelp_command(self, ctx: commands.Context):
        """Show help information"""
        embed = discord.Embed(
            title="🎮 Arma 3 Mod Manager - Help",
            description="A Discord bot to help manage your Arma 3 mod lists",
            color=0x0099ff
        )
        
        embed.add_field(
            name="📁 File Upload",
            value="Simply upload an HTML file exported from Arma 3 Launcher",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Commands",
            value="`!modlist` - Show mod manager help\n"
                  "`!bothelp` - Show this help message\n"
                  "`!help` - Show Discord.py help",
            inline=False
        )
        
        embed.add_field(
            name="✨ Features",
            value="• Automatic mod name lookup\n"
                  "• CDLC compatibility checking\n"
                  "• Mod list comparison\n"
                  "• Size estimation\n"
                  "• Mobile-friendly interface",
            inline=False
        )
        
        embed.set_footer(text="Made for Arma 3 communities")
        
        await ctx.send(embed=embed)

    @commands.command(name='modsize_debug')
    async def modsize_debug(self, ctx: commands.Context):
        """Show a breakdown of mod sizes for the last uploaded list."""
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id)
        # Try to get the last analysis for this user/guild
        if hasattr(self.bot.analyzer, 'get_last_analysis'):
            last_analysis = self.bot.analyzer.get_last_analysis(user_id, guild_id)
        else:
            last_analysis = None
        if not last_analysis:
            await ctx.send("No mod list analysis found for you yet.")
            return

        mod_info = last_analysis['mod_info']
        lines = []
        total_size = 0
        known_count = 0
        unknown_count = 0
        for mod in mod_info:
            size = mod.get('size_gb')
            if size is not None:
                known_count += 1
                total_size += size
                lines.append(f"{mod['name']} ({mod['id']}): {size:.2f} GB")
            else:
                unknown_count += 1
                lines.append(f"{mod['name']} ({mod['id']}): Unknown size")

        summary = (
            f"**Total Mods:** {len(mod_info)}\n"
            f"**Known Sizes:** {known_count}\n"
            f"**Unknown Sizes:** {unknown_count}\n"
            f"**Total Known Size:** {total_size:.2f} GB"
        )
        await ctx.send(summary + "\n\n" + "\n".join(lines[:30]) + ("\n...and more." if len(lines) > 30 else ""))

class ModListView(discord.ui.View):
    def __init__(self, list_id: str, total_mods: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.list_id = list_id
        self.total_mods = total_mods
        self.current_page = 0
        self.mods_per_page = 10
    
    @discord.ui.button(label="📋 Show All Mods", style=discord.ButtonStyle.primary)
    async def show_all_mods(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all mods in a new message"""
        bot = interaction.client
        if self.list_id not in bot.active_mod_lists:
            await interaction.response.send_message("❌ Mod list has expired. Please upload again.", ephemeral=True)
            return
        
        mods = bot.active_mod_lists[self.list_id]['mods']
        
        # Create a comprehensive mod list
        all_mods_text = "**Complete Mod List:**\n\n"
        for i, mod in enumerate(mods, 1):
            size_text = f" ({mod.get('size_gb', 'Unknown'):.1f}GB)" if mod.get('size_gb') else ""
            all_mods_text += f"{i}. **{mod['name']}**{size_text}\n"
            all_mods_text += f"   ID: {mod['id']} | [Steam Page]({mod['url']})\n\n"
        
        # Split if too long
        if len(all_mods_text) > 2000:
            chunks = [all_mods_text[i:i+1900] for i in range(0, len(all_mods_text), 1900)]
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"📋 Complete Mod List (Part {i+1}/{len(chunks)})",
                    description=chunk,
                    color=0x00ff00
                )
                await interaction.channel.send(embed=embed)
        else:
            embed = discord.Embed(
                title="📋 Complete Mod List",
                description=all_mods_text,
                color=0x00ff00
            )
            await interaction.channel.send(embed=embed)
        
        await interaction.response.send_message("✅ Complete mod list sent!", ephemeral=True)
    
    @discord.ui.button(label="📊 Mod Categories", style=discord.ButtonStyle.secondary)
    async def show_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show mods categorized by type"""
        bot = interaction.client
        if self.list_id not in bot.active_mod_lists:
            await interaction.response.send_message("❌ Mod list has expired. Please upload again.", ephemeral=True)
            return
        
        mods = bot.active_mod_lists[self.list_id]['mods']
        mod_info = {mod['id']: mod for mod in mods}
        
        categories = bot.analyzer.categorize_mods(mod_info)
        
        embed = discord.Embed(
            title="📊 Mod Categories",
            description="Mods organized by type",
            color=0x0099ff
        )
        
        for category, mod_list in categories.items():
            if mod_list:
                category_name = category.title()
                mod_text = ""
                for mod in mod_list[:5]:  # Show first 5 of each category
                    size_text = f" ({mod.get('size_gb', 'Unknown'):.1f}GB)" if mod.get('size_gb') else ""
                    mod_text += f"• {mod['name']}{size_text}\n"
                
                if len(mod_list) > 5:
                    mod_text += f"... and {len(mod_list) - 5} more\n"
                
                embed.add_field(
                    name=f"{category_name} ({len(mod_list)})",
                    value=mod_text,
                    inline=True
                )
        
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Mod categories sent!", ephemeral=True)
    
    @discord.ui.button(label="❌ Dismiss", style=discord.ButtonStyle.danger)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Dismiss the view"""
        await interaction.message.delete()
        await interaction.response.send_message("✅ Mod list dismissed.", ephemeral=True)

async def main():
    """Main function to run the bot"""
    bot = ArmaModBot()
    
    try:
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Error running bot: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main()) 