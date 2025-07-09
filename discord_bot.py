import discord
from discord import app_commands
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
        
        # Track last mod list message per channel
        self.last_modlist_message = {}
        self.last_modlist_analysis = {}
    
    async def setup_hook(self):
        """Setup hook for bot initialization"""
        await self.add_cog(ModCommands(self))
        
        # Sync slash commands with Discord
        print("Syncing slash commands...")
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
    
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
    
    @app_commands.command(name="modlist", description="Show help for mod list analysis")
    async def modlist_slash(self, interaction: discord.Interaction):
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
                  "3. The bot will automatically analyze your mod list",
            inline=False
        )
        
        embed.add_field(
            name="🔍 What I'll check",
            value="• List all mods with names and sizes\n"
                  "• Check for CDLC requirements\n"
                  "• Compare with your last upload\n"
                  "• Estimate total download size",
            inline=False
        )
        
        embed.add_field(
            name="📋 Commands",
            value="`/modlist` - Show this help\n"
                  "`/bothelp` - Show all commands",
            inline=False
        )
        
        embed.set_footer(text="Made for Arma 3 communities")
        
        await interaction.response.send_message(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle file uploads and commands, but prevent duplicate command processing."""
        if message.author.bot:
            return
        
        # Check for HTML file uploads first
        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.lower().endswith('.html'):
                    await self.handle_html_upload(message, attachment)
                    return  # Prevents any further processing
        
        # Only process commands if no file upload was handled
        await self.bot.process_commands(message)
    
    async def handle_html_upload(self, message: discord.Message, attachment: discord.Attachment):
        """Handle HTML file upload"""
        loading_embed = discord.Embed(
            title="🔄 Processing Mod List",
            description="Downloading and analyzing your mod list...",
            color=0xffff00
        )
        loading_msg = await message.channel.send(embed=loading_embed)
        try:
            html_content = await attachment.read()
            html_text = html_content.decode('utf-8')
            analysis = await self.bot.analyzer.analyze_mod_list(
                html_text, 
                str(message.author.id), 
                str(message.guild.id)
            )
            analysis['modlist_attachment_url'] = attachment.url

            # Delete previous mod list message in this channel
            channel_id = message.channel.id
            old_msg = self.bot.last_modlist_message.get(channel_id)
            old_message_deleted = False
            if old_msg:
                try:
                    await old_msg.delete()
                    old_message_deleted = True
                except Exception:
                    pass

            # Send the new analysis
            result_msg = await self.send_mod_analysis(message.channel, analysis, message.author)
            self.bot.last_modlist_message[channel_id] = result_msg
            self.bot.last_modlist_analysis[channel_id] = analysis
            await loading_msg.delete()
            
            # Send private notification if old message was deleted
            if old_message_deleted:
                try:
                    notification_embed = discord.Embed(
                        title="🗑️ Old Mod List Removed",
                        description="I've automatically removed the previous mod list message from this channel to keep things organized.",
                        color=0x0099ff
                    )
                    notification_embed.add_field(
                        name="ℹ️ Why this happened",
                        value="When you upload a new mod list, I automatically delete the old one to prevent confusion and keep the channel clean.",
                        inline=False
                    )
                    notification_embed.set_footer(text="This message is only visible to you")
                    
                    await message.author.send(embed=notification_embed)
                except discord.Forbidden:
                    # User has DMs disabled, ignore
                    pass
                except Exception as e:
                    # Log error but don't fail the main operation
                    print(f"Failed to send deletion notification: {e}")
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error Processing Mod List",
                description=f"An error occurred while processing your mod list:\n```{str(e)}```",
                color=0xff0000
            )
            await loading_msg.edit(embed=error_embed)

    async def send_mod_analysis(self, channel, analysis: dict, user: discord.Member):
        """Send comprehensive mod analysis"""
        # Create main embed with new title format
        embed = discord.Embed(
            title=f"Current Modlist for {channel.guild.name}",
            description="",  # Remove user mention
            color=0x00ff00
        )
        
        # Add Discord icon to the right side (300x300px)
        if channel.guild.icon:
            embed.set_thumbnail(url=channel.guild.icon.url)
        
        # Add mod count and size using inline fields
        embed.add_field(
            name="📊 Total Mods",
            value=f"**{analysis['total_mods']}**",
            inline=True
        )
        embed.add_field(
            name="📦 Estimated Size",
            value=f"**{analysis['size_estimate']['total_size_gb']:.1f}GB**",
            inline=True
        )

        # Add line break
        embed.add_field(name="", value="", inline=False)

        # Add CDLC compatibility check
        compat_info = analysis['compatibility_check']
        detected_cdlc = compat_info.get('detected_cdlc', [])
        mods_require_cdlc = compat_info.get('mods_require_cdlc', [])
        
        # Handle CDLC detection
        if detected_cdlc or mods_require_cdlc:
            compat_text = ""
            
            # Check for detected CDLC
            if detected_cdlc:
                from config import CDLC_COMPAT_MODS
                for cdlc_key, cdlc_info in CDLC_COMPAT_MODS.items():
                    if cdlc_info['name'] in detected_cdlc:
                        compat_text += f"**{cdlc_info['name']}**\n"
                        compat_text += f"• [Compat Mod: {cdlc_info['compat_name']}]({cdlc_info['steam_url']})\n\n"
            
            # Check for mods that may require CDLC
            potential_cdlc = []
            for cdlc_name in mods_require_cdlc:
                if cdlc_name not in detected_cdlc:
                    potential_cdlc.append(cdlc_name)
            
            if potential_cdlc:
                compat_text += "⚠️ **This modlist may require these CDLC:**\n\n"
                
                # Add links for each potential CDLC
                for cdlc_name in potential_cdlc:
                    for cdlc_key, cdlc_info in CDLC_COMPAT_MODS.items():
                        if cdlc_info['name'] == cdlc_name:
                            compat_text += f"• [{cdlc_name}]({cdlc_info['cdlc_url']})\n"
                            break
                compat_text += "\n***If you own the CDLC, remember to ***activate it*** before joining the server!***\n\n"
            
            # Truncate if too long for Discord
            if len(compat_text) > 1024:
                compat_text = compat_text[:1021] + "..."
            
            embed.add_field(
                name="CDLC Required",
                value=compat_text,
                inline=False
            )
        else:
            embed.add_field(
                name="CDLC Required",
                value="No CDLC detected in your mod list.",
                inline=False
            )

        # Add line break
        embed.add_field(name="", value="", inline=False)

        # Add workshop requirements check
        workshop_req = analysis.get('workshop_requirements', {})
        if workshop_req:
            if workshop_req.get('all_requirements_met', True):
                embed.add_field(
                    name="✅ Workshop Requirements",
                    value="🟢 All required workshop dependencies are included",
                    inline=False
                )
            else:
                missing_text = ""
                for missing in workshop_req.get('missing_requirements', [])[:5]:  # Show first 5
                    missing_text += f"• **{missing['mod_name']}** requires {missing['required_item']}\n"
                if len(missing_text) > 1024:
                    missing_text = missing_text[:1021] + "..."
                embed.add_field(
                    name="❌ Workshop Requirements",
                    value=f"🔴 Missing required items:\n{missing_text}",
                    inline=False
                )
                embed.color = 0xff0000  # Red for errors

        # Add line break
        embed.add_field(name="", value="", inline=False)

        # Add changes from previous upload
        if analysis['comparison'] and analysis['comparison']['has_changes']:
            changes_text = ""
            if analysis['comparison']['total_added'] > 0:
                changes_text += f"➕ **Added:** {analysis['comparison']['total_added']} mods\n"
            if analysis['comparison']['total_removed'] > 0:
                changes_text += f"➖ **Removed:** {analysis['comparison']['total_removed']} mods\n"
            
            # Calculate size of added and removed mods
            added_size = 0.0
            removed_size = 0.0
            
            if analysis['comparison']['total_added'] > 0:
                added_mods = analysis['comparison']['added_mods']
                for mod_id in added_mods:
                    mod_info = analysis['mod_info'].get(mod_id, {})
                    size = mod_info.get('size_gb', 0)
                    if size:
                        added_size += size
            
            if analysis['comparison']['total_removed'] > 0:
                removed_mods = analysis['comparison']['removed_mods']
                for mod_id in removed_mods:
                    # Try to get mod size from cache since it's not in current mod_info
                    cached_mod = self.bot.analyzer.database.get_cached_mod_info(mod_id)
                    if cached_mod and cached_mod.get('mod_size'):
                        removed_size += cached_mod['mod_size']
            
            # Update the change text to include sizes
            if analysis['comparison']['total_added'] > 0:
                changes_text = changes_text.replace(
                    f"➕ **Added:** {analysis['comparison']['total_added']} mods\n",
                    f"➕ **Added:** {analysis['comparison']['total_added']} mods | {added_size:.1f}GB\n"
                )
            
            if analysis['comparison']['total_removed'] > 0:
                changes_text = changes_text.replace(
                    f"➖ **Removed:** {analysis['comparison']['total_removed']} mods\n",
                    f"➖ **Removed:** {analysis['comparison']['total_removed']} mods | {removed_size:.1f}GB\n"
                )
            
            # Add actual mod names if there are changes (only if 5 or fewer)
            if analysis['comparison']['total_added'] > 0 and analysis['comparison']['total_added'] <= 5:
                changes_text += "\n**Added Mods:**\n"
                added_mods = analysis['comparison']['added_mods']
                for i, mod_id in enumerate(added_mods):
                    mod_info = analysis['mod_info'].get(mod_id, {})
                    mod_name = mod_info.get('name', f"Mod {mod_id}")
                    size_text = f" ({mod_info.get('size_gb', 0):.1f}GB)" if mod_info.get('size_gb') else ""
                    changes_text += f"• {mod_name}{size_text}\n"
            
            if analysis['comparison']['total_removed'] > 0 and analysis['comparison']['total_removed'] <= 5:
                changes_text += "\n**Removed Mods:**\n"
                removed_mods = analysis['comparison']['removed_mods']
                for i, mod_id in enumerate(removed_mods):
                    # Try to get mod name from cache since it's not in current mod_info
                    cached_mod = self.bot.analyzer.database.get_cached_mod_info(mod_id)
                    mod_name = cached_mod.get('mod_name', f"Mod {mod_id}") if cached_mod else f"Mod {mod_id}"
                    size_text = f" ({cached_mod.get('mod_size', 0):.1f}GB)" if cached_mod and cached_mod.get('mod_size') else ""
                    changes_text += f"• {mod_name}{size_text}\n"
            
            if len(changes_text) > 1024:
                changes_text = changes_text[:1021] + "..."
            embed.add_field(
                name="📈 Changes from Last Upload",
                value=changes_text,
                inline=False
            )

        # Add line break
        embed.add_field(name="", value="", inline=False)

        # Format mod list for display - show only 10 mods
        mod_display = self.bot.analyzer.format_mod_list_for_display_3columns(
            analysis['mod_info'], 
            10  # Show only first 10 mods
        )

        # Add message about remaining mods
        remaining_count = mod_display['remaining_count']
        if remaining_count > 0:
            mod_list_text = mod_display['display_text'] + f"\n\nClick \"Show All Mods\" to get a list of these mods sent to your Discord inbox."
        else:
            mod_list_text = mod_display['display_text']

        embed.add_field(
            name=f"📦 Mod List ({mod_display['displayed_count']}/{mod_display['total_mods']})",
            value=mod_list_text,
            inline=False
        )

        # Store mod list for button interactions
        list_id = f"{user.id}_{int(time.time())}"
        self.bot.active_mod_lists[list_id] = {
            'mods': mod_display['all_mods'],
            'timestamp': time.time(),
            'download_url': analysis.get('modlist_attachment_url')
        }

        # Create view with buttons
        view = ModListView(list_id, mod_display['total_mods'])

        # Send the embed
        msg = await channel.send(embed=embed, view=view)

        # Auto-delete after delay if in a lobby channel
        if 'lobby' in channel.name.lower():
            await asyncio.sleep(MESSAGE_DELETE_DELAY)
            try:
                await msg.delete()
            except:
                pass

        return msg
    
    @app_commands.command(name="bothelp", description="Show detailed bot help and features")
    async def bothelp_slash(self, interaction: discord.Interaction):
        """Show detailed bot help"""
        embed = discord.Embed(
            title="🤖 LoadmasterBot Help",
            description="Complete guide to using the Arma 3 Mod Manager Discord Bot",
            color=0x0099ff
        )
        
        embed.add_field(
            name="📁 File Upload",
            value="**How to upload mod lists:**\n"
                  "1. Open Arma 3 Launcher\n"
                  "2. Go to Mods tab\n"
                  "3. Select your mod list\n"
                  "4. Click 'Export' and save as HTML\n"
                  "5. Upload the HTML file to Discord\n\n"
                  "The bot will automatically analyze your mod list!",
            inline=False
        )
        
        embed.add_field(
            name="🔍 Analysis Features",
            value="**What the bot checks:**\n"
                  "• Mod names and Steam Workshop links\n"
                  "• Individual mod sizes and total download size\n"
                  "• CDLC requirements and compatibility mods\n"
                  "• Workshop dependencies and missing items\n"
                  "• Changes from your previous upload\n"
                  "• Mod list comparison and tracking",
            inline=False
        )
        
        embed.add_field(
            name="📋 Available Commands",
            value="**Slash Commands:**\n"
                  "`/modlist` - Show basic help\n"
                  "`/bothelp` - Show detailed help (this command)\n"
                  "`/debug` - Debug bot functionality\n\n"
                  "**Legacy Commands:**\n"
                  "`!modlist` - Show basic help\n"
                  "`!bothelp` - Show detailed help\n"
                  "`!modsize_debug` - Debug mod sizes\n"
                  "`!dlc_debug <mod_id>` - Debug DLC for specific mod\n"
                  "`!changes_debug` - Debug change tracking",
            inline=False
        )
        
        embed.add_field(
            name="🎮 Interactive Features",
            value="**After uploading a mod list:**\n"
                  "• **Show All Mods** button - Get complete list in private message\n"
                  "• **Download** button - Download original HTML file\n"
                  "• **Change tracking** - See what changed from last upload\n"
                  "• **CDLC warnings** - Get links to compatibility mods",
            inline=False
        )
        
        embed.add_field(
            name="🔧 Troubleshooting",
            value="**Common issues:**\n"
                  "• Make sure the file is an HTML export from Arma 3 Launcher\n"
                  "• Check that the bot has permission to send messages\n"
                  "• For private messages, ensure the bot can DM you\n"
                  "• If mod names don't show, Steam Workshop might be down",
            inline=False
        )
        
        embed.set_footer(text="LoadmasterBot v2.0 - Made for Arma 3 communities")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="debug", description="Debug bot functionality")
    @app_commands.describe(
        debug_type="Type of debug: modsize, dlc, or changes",
        mod_id="Mod ID for DLC debug (required for dlc type)"
    )
    async def debug_slash(self, interaction: discord.Interaction, debug_type: str, mod_id: str = None):
        """Unified debug command for all debug functionality"""
        await interaction.response.defer(ephemeral=True)
        
        if debug_type.lower() == "modsize":
            await self._debug_modsize(interaction)
        elif debug_type.lower() == "dlc":
            if not mod_id:
                await interaction.followup.send("❌ Mod ID is required for DLC debug. Use `/debug dlc <mod_id>`", ephemeral=True)
                return
            await self._debug_dlc(interaction, mod_id)
        elif debug_type.lower() == "changes":
            await self._debug_changes(interaction)
        else:
            await interaction.followup.send("❌ Invalid debug type. Use: `modsize`, `dlc`, or `changes`", ephemeral=True)
    
    async def _debug_modsize(self, interaction: discord.Interaction):
        """Debug mod sizes for the last uploaded list"""
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id) if interaction.guild else "DM"
        
        if hasattr(self.bot.analyzer, 'get_last_analysis'):
            last_analysis = self.bot.analyzer.get_last_analysis(user_id, guild_id)
        else:
            last_analysis = None
            
        if not last_analysis:
            await interaction.followup.send("No mod list analysis found for you yet.", ephemeral=True)
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
        
        content = summary + "\n\n" + "\n".join(lines[:30])
        if len(lines) > 30:
            content += "\n...and more."
            
        await interaction.followup.send(content, ephemeral=True)
    
    async def _debug_dlc(self, interaction: discord.Interaction, mod_id: str):
        """Debug DLC requirements for a specific mod"""
        try:
            mod_info = await self.bot.steam_api.get_mod_info(mod_id)
            if mod_info:
                dlc_info = mod_info.get('dlc_requirements', {})
                embed = discord.Embed(
                    title=f"🔍 DLC Analysis for {mod_info['name']}",
                    description=f"Mod ID: {mod_id}",
                    color=0x0099ff
                )
                
                if dlc_info.get('required'):
                    embed.add_field(
                        name="🔴 Required DLC",
                        value="\n".join([f"• {dlc}" for dlc in dlc_info['required']]),
                        inline=False
                    )
                
                if dlc_info.get('optional'):
                    embed.add_field(
                        name="🟡 Optional DLC",
                        value="\n".join([f"• {dlc}" for dlc in dlc_info['optional']]),
                        inline=False
                    )
                
                if dlc_info.get('compatible'):
                    embed.add_field(
                        name="🟢 Compatible DLC",
                        value="\n".join([f"• {dlc}" for dlc in dlc_info['compatible']]),
                        inline=False
                    )
                
                if not any(dlc_info.values()):
                    embed.add_field(
                        name="ℹ️ DLC Requirements",
                        value="No DLC requirements detected",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Could not fetch mod information for {mod_id}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    
    async def _debug_changes(self, interaction: discord.Interaction):
        """Debug the changes detection for the last upload"""
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id) if interaction.guild else "DM"
        
        if hasattr(self.bot.analyzer, 'get_last_analysis'):
            last_analysis = self.bot.analyzer.get_last_analysis(user_id, guild_id)
        else:
            last_analysis = None
        
        if not last_analysis:
            await interaction.followup.send("No mod list analysis found for you yet.", ephemeral=True)
            return
        
        last_upload = self.bot.analyzer.database.get_last_upload(user_id, guild_id)
        if not last_upload:
            await interaction.followup.send("No previous upload found for comparison.", ephemeral=True)
            return
        
        current_mods = [mod['id'] for mod in last_analysis['mod_info']]
        previous_mods = last_upload['mod_list']
        
        comparison = self.bot.analyzer.compare_mod_lists(current_mods, previous_mods)
        
        embed = discord.Embed(
            title="🔍 Changes Debug",
            description="Analysis of the last comparison",
            color=0x0099ff
        )
        
        embed.add_field(
            name="📊 Comparison Data",
            value=f"**Added:** {comparison['total_added']} mods\n"
                  f"**Removed:** {comparison['total_removed']} mods\n"
                  f"**Unchanged:** {comparison['total_unchanged']} mods\n"
                  f"**Has Changes:** {comparison['has_changes']}",
            inline=False
        )
        
        if comparison['added_mods']:
            embed.add_field(
                name="➕ Added Mod IDs",
                value="\n".join([f"• {mod_id}" for mod_id in comparison['added_mods'][:10]]),
                inline=True
            )
        
        if comparison['removed_mods']:
            embed.add_field(
                name="➖ Removed Mod IDs",
                value="\n".join([f"• {mod_id}" for mod_id in comparison['removed_mods'][:10]]),
                inline=True
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # Legacy commands for backward compatibility
    @commands.command(name='modlist', aliases=['ml', 'mods'])
    async def modlist_legacy(self, ctx: commands.Context):
        """Legacy command - use /modlist instead"""
        await ctx.send("⚠️ This command is deprecated. Please use `/modlist` instead.")
    
    @commands.command(name='bothelp', aliases=['bh'])
    async def bothelp_legacy(self, ctx: commands.Context):
        """Legacy command - use /bothelp instead"""
        await ctx.send("⚠️ This command is deprecated. Please use `/bothelp` instead.")
    
    @commands.command(name='modsize_debug')
    async def modsize_debug_legacy(self, ctx: commands.Context):
        """Legacy command - use /debug modsize instead"""
        await ctx.send("⚠️ This command is deprecated. Please use `/debug modsize` instead.")
    
    @commands.command(name='dlc_debug')
    async def dlc_debug_legacy(self, ctx: commands.Context, mod_id: str = None):
        """Legacy command - use /debug dlc <mod_id> instead"""
        if mod_id:
            await ctx.send(f"⚠️ This command is deprecated. Please use `/debug dlc {mod_id}` instead.")
        else:
            await ctx.send("⚠️ This command is deprecated. Please use `/debug dlc <mod_id>` instead.")
    
    @commands.command(name='changes_debug')
    async def changes_debug_legacy(self, ctx: commands.Context):
        """Legacy command - use /debug changes instead"""
        await ctx.send("⚠️ This command is deprecated. Please use `/debug changes` instead.")

class ModListView(discord.ui.View):
    def __init__(self, list_id: str, total_mods: int):
        super().__init__(timeout=300)  # 5 minute timeout
        self.list_id = list_id
        self.total_mods = total_mods
        self.current_page = 0
        self.mods_per_page = 10
    
    @discord.ui.button(label="📋 Show All Mods", style=discord.ButtonStyle.primary)
    async def show_all_mods(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all mods in a private message to the user"""
        # Respond immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)
        
        bot = interaction.client
        if self.list_id not in bot.active_mod_lists:
            await interaction.followup.send("❌ Mod list has expired. Please upload again.", ephemeral=True)
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
                try:
                    await interaction.user.send(embed=embed)
                except discord.Forbidden:
                    await interaction.followup.send("❌ I cannot send you a private message. Please check your privacy settings.", ephemeral=True)
                    return
        else:
            embed = discord.Embed(
                title="📋 Complete Mod List",
                description=all_mods_text,
                color=0x00ff00
            )
            try:
                await interaction.user.send(embed=embed)
            except discord.Forbidden:
                await interaction.followup.send("❌ I cannot send you a private message. Please check your privacy settings.", ephemeral=True)
                return
        
        await interaction.followup.send("✅ Complete mod list sent to your private messages!", ephemeral=True)
    
    @discord.ui.button(label="⬇️ DOWNLOAD", style=discord.ButtonStyle.secondary, emoji="📥")
    async def download_modlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Download the original modlist HTML file"""
        bot = interaction.client
        if self.list_id not in bot.active_mod_lists:
            await interaction.response.send_message("❌ Mod list has expired. Please upload again.", ephemeral=True)
            return
        
        download_url = bot.active_mod_lists[self.list_id].get('download_url')
        if download_url:
            await interaction.response.send_message(f"📥 [Download your mod list HTML file]({download_url})", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Download link not available.", ephemeral=True)

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