import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import io
import tempfile
import os
from typing import Optional
import time

from config import DISCORD_TOKEN, BOT_PREFIX, MAX_MODS_PER_PAGE, MESSAGE_DELETE_DELAY, AUTHORIZED_USERS
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
        
        # Track last mod list analysis per channel (for comparison)
        self.last_modlist_analysis = {}
        
        # Start cleanup task for expired mod lists
        self.cleanup_task = None
    
    async def setup_hook(self):
        """Setup hook for bot initialization"""
        await self.add_cog(ModCommands(self))
        
        # Add persistent views for button functionality after restarts
        self.add_view(ModListView("persistent", 0))
        
        # Sync slash commands with Discord
        print("Syncing slash commands...")
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
        
        # Start cleanup task for expired mod lists
        self.cleanup_task = asyncio.create_task(self.cleanup_expired_mod_lists())
    
    async def on_ready(self):
        """Called when bot is ready"""
        print(f'{self.user} has connected to Discord!')
        print(f'Bot is in {len(self.guilds)} guilds')
        
        # Set bot status
        await self.change_presence(activity=discord.Game(name="Arma 3 Mod Manager"))
        
        # Railway-specific: Log environment info
        print(f"Running on Railway: {os.getenv('RAILWAY_ENVIRONMENT', 'Unknown')}")
        print(f"Container ID: {os.getenv('RAILWAY_CONTAINER_ID', 'Unknown')}")
    
    async def cleanup_expired_mod_lists(self):
        """Cleanup task to remove expired mod lists from memory and old database records"""
        while not self.is_closed():
            try:
                current_time = time.time()
                expired_keys = []
                
                for list_id, data in self.active_mod_lists.items():
                    # Remove mod lists older than 20 minutes (1200 seconds)
                    if current_time - data['timestamp'] > 1200:
                        expired_keys.append(list_id)
                
                for key in expired_keys:
                    del self.active_mod_lists[key]
                
                if expired_keys:
                    print(f"Cleaned up {len(expired_keys)} expired mod lists")
                
                # Clean up old bot messages from database (older than 24 hours)
                self.database.cleanup_old_bot_messages(86400)  # 24 hours
                
                # Run cleanup every 5 minutes
                await asyncio.sleep(300)
                
            except Exception as e:
                print(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def close(self):
        """Cleanup when bot shuts down"""
        # Cancel cleanup task
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
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
                    # Add a small delay to ensure Discord interaction context is ready
                    await asyncio.sleep(0.1)
                    await self.handle_html_upload(message, attachment)
                    return  # Prevents any further processing
        
        # Only process commands if no file upload was handled
        await self.bot.process_commands(message)
    
    async def handle_html_upload(self, message: discord.Message, attachment: discord.Attachment):
        """Handle HTML file upload"""
        print(f"Processing HTML upload from {message.author.name} ({message.author.id})")
        
        # Check if user is authorized to upload mod lists
        user_id = str(message.author.id)
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            error_embed = discord.Embed(
                title="❌ Access Denied",
                description="You are not authorized to upload mod lists to this bot.",
                color=0xff0000
            )
            error_embed.add_field(
                name="ℹ️ How to get access",
                value="Contact the bot administrator to be added to the authorized users list.",
                inline=False
            )
            await message.channel.send(embed=error_embed)
            return
        
        loading_embed = discord.Embed(
            title="🔄 Processing Mod List",
            description="Downloading and analyzing your mod list...",
            color=0xffff00
        )
        loading_msg = await message.channel.send(embed=loading_embed)
        try:
            print(f"Reading HTML file: {attachment.filename}")
            html_content = await attachment.read()
            html_text = html_content.decode('utf-8')
            print(f"HTML file read successfully, size: {len(html_text)} characters")
            
            print("Starting mod list analysis...")
            # Add timeout to prevent hanging
            analysis = await asyncio.wait_for(
                self.bot.analyzer.analyze_mod_list(
                    html_text, 
                    user_id, 
                    str(message.guild.id) if message.guild else "DM"
                ),
                timeout=60.0  # 60 second timeout
            )
            print("Mod list analysis completed successfully")
            analysis['modlist_attachment_url'] = attachment.url

            # Delete previous mod list messages in this channel
            channel_id = str(message.channel.id)
            old_messages = self.bot.database.get_bot_messages_for_channel(channel_id, "modlist")
            old_message_deleted = False
            
            for old_msg_id, old_user_id in old_messages:
                try:
                    # Only delete messages from the same user or if it's the same channel
                    if old_user_id == str(message.author.id):
                        old_msg = await message.channel.fetch_message(int(old_msg_id))
                        await old_msg.delete()
                        old_message_deleted = True
                        # Remove from database
                        self.bot.database.delete_bot_message(old_msg_id)
                except Exception as e:
                    print(f"Could not delete old message {old_msg_id}: {e}")
                    # Remove from database if message doesn't exist
                    self.bot.database.delete_bot_message(old_msg_id)

            # Send the new analysis
            result_msg = await self.send_mod_analysis(message.channel, analysis, message.author)
            
            # Save the new message to database
            self.bot.database.save_bot_message(
                channel_id=str(message.channel.id),
                message_id=str(result_msg.id),
                user_id=str(message.author.id),
                server_id=str(message.guild.id) if message.guild else "DM",
                message_type="modlist"
            )
            
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
        except asyncio.TimeoutError:
            print("Mod list analysis timed out after 60 seconds")
            error_embed = discord.Embed(
                title="⏰ Processing Timeout",
                description="The mod list analysis took too long and timed out. This might be due to:\n"
                           "• Large number of mods\n"
                           "• Steam Workshop API being slow\n"
                           "• Network connectivity issues\n\n"
                           "Please try again in a few minutes.",
                color=0xff6600
            )
            await loading_msg.edit(embed=error_embed)
        except Exception as e:
            print(f"Error processing mod list: {e}")
            error_embed = discord.Embed(
                title="❌ Error Processing Mod List",
                description=f"An error occurred while processing your mod list:\n```{str(e)}```",
                color=0xff0000
            )
            await loading_msg.edit(embed=error_embed)

    async def send_mod_analysis(self, channel, analysis: dict, user: discord.User | discord.Member):
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
        
        # Debug output
        print(f"DEBUG - Detected CDLC: {detected_cdlc}")
        print(f"DEBUG - Mods require CDLC: {mods_require_cdlc}")
        
        # Handle CDLC detection - unified approach
        if detected_cdlc or mods_require_cdlc:
            from config import CDLC_COMPAT_MODS
            
            # Collect all unique CDLC requirements
            all_cdlc_requirements = set()
            if detected_cdlc:
                all_cdlc_requirements.update(detected_cdlc)
            if mods_require_cdlc:
                all_cdlc_requirements.update(mods_require_cdlc)
            
            compat_text = "**Required CDLC and Compatibility Mods:**\n\n"
            
            # Process each CDLC requirement
            for cdlc_name in sorted(all_cdlc_requirements):
                # Find the CDLC info from config
                cdlc_info = None
                for cdlc_key, info in CDLC_COMPAT_MODS.items():
                    if info['name'] == cdlc_name:
                        cdlc_info = info
                        break
                
                if cdlc_info:
                    # Check if this CDLC is detected (has compat mod) or just required
                    is_detected = cdlc_name in detected_cdlc
                    
                    if is_detected:
                        # CDLC is detected - show compat mod link
                        compat_text += f"✅ **{cdlc_name}** (Detected)\n"
                        compat_text += f"• [Compatibility Mod]({cdlc_info['steam_url']})\n\n"
                    else:
                        # CDLC is required but not detected - show CDLC link
                        compat_text += f"⚠️ **{cdlc_name}** (Required)\n"
                        compat_text += f"• [CDLC Store Page]({cdlc_info['cdlc_url']})\n"
                        compat_text += f"• [Compatibility Mod]({cdlc_info['steam_url']})\n\n"
            
            # Add reminder about activating CDLC
            if any(cdlc_name not in detected_cdlc for cdlc_name in all_cdlc_requirements):
                compat_text += "***If you own the CDLC, remember to ***activate it*** before joining the server!***\n\n"
            
            # Truncate if too long for Discord
            if len(compat_text) > 1024:
                compat_text = compat_text[:1021] + "..."
            
            embed.add_field(
                name="🎮 CDLC Requirements",
                value=compat_text,
                inline=False
            )
        else:
            embed.add_field(
                name="🎮 CDLC Requirements",
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
            'download_url': analysis.get('modlist_attachment_url'),
            'user_id': user.id,
            'guild_id': channel.guild.id if channel.guild else None
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
                  "`/debug` - Debug bot functionality\n"
                  "`/regen` - Regenerate buttons for recent mod list\n"
                  "`/showmods` - Show complete mod list (no timeout)\n"
                  "`/download` - Get download link (no timeout)\n"
                  "`/cleanup` - Clean up old bot messages (Admin only)\n\n"
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
                  "• **LMB Alpha 0.5.1** button - View GitHub repository\n"
                  "• **Change tracking** - See what changed from last upload\n"
                  "• **CDLC warnings** - Get links to compatibility mods\n\n"
                  "**Persistent Buttons:** Buttons work permanently (no timeout).\n"
                  "**Alternative Commands:** Use `/showmods` and `/download` as backup.",
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
    async def debug_slash(self, interaction: discord.Interaction, debug_type: str, mod_id: str | None = None):
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
    
    @app_commands.command(name="regen", description="Get fresh buttons for your recent mod list")
    async def regen_buttons(self, interaction: discord.Interaction):
        """Get fresh buttons for a recent mod list"""
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else None
        
        # Find the most recent mod list for this user
        most_recent = None
        most_recent_time = 0
        
        for list_id, data in self.bot.active_mod_lists.items():
            if (data.get('user_id') == user_id and 
                data.get('guild_id') == guild_id and
                data['timestamp'] > most_recent_time):
                most_recent = (list_id, data)
                most_recent_time = data['timestamp']
        
        if not most_recent:
            await interaction.followup.send("❌ No recent mod list found. Please upload a new mod list first.", ephemeral=True)
            return
        
        list_id, data = most_recent
        
        # Check if the mod list is too old (more than 24 hours)
        if time.time() - data['timestamp'] > 86400:  # 24 hours
            await interaction.followup.send("❌ Your mod list is too old (more than 24 hours). Please upload a new one.", ephemeral=True)
            return
        
        # Create new view with fresh buttons
        view = ModListView(list_id, len(data['mods']))
        
        embed = discord.Embed(
            title="🔄 Fresh Buttons Generated",
            description="Here are fresh buttons for your recent mod list:",
            color=0x00ff00
        )
        embed.add_field(
            name="📋 Available Actions",
            value="• **Show All Mods** - Get complete list in private message\n"
                  "• **Download** - Download original HTML file\n"
                  "• **LMB Alpha 0.5.1** - View GitHub repository",
            inline=False
        )
        embed.add_field(
            name="⏰ Button Lifetime",
            value="These buttons will work permanently (no timeout).",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name="cleanup", description="Clean up old bot messages (Admin only)")
    async def cleanup_messages(self, interaction: discord.Interaction):
        """Clean up old bot messages from the database"""
        await interaction.response.defer(ephemeral=True)
        
        # Only allow admins in guilds, or the bot owner in DMs
        is_admin = False
        from discord import Member
        if interaction.guild and isinstance(interaction.user, Member):
            is_admin = interaction.user.guild_permissions.administrator
        else:
            is_admin = str(interaction.user.id) in ["YOUR_USER_ID_HERE"]  # Replace with your Discord ID
        if not is_admin:
            await interaction.followup.send("❌ You don't have permission to use this command.", ephemeral=True)
            return
        
        try:
            # Clean up old bot messages (older than 1 hour for testing)
            self.bot.database.cleanup_old_bot_messages(3600)  # 1 hour
            
            embed = discord.Embed(
                title="🧹 Cleanup Complete",
                description="Old bot messages have been cleaned up from the database.",
                color=0x00ff00
            )
            embed.add_field(
                name="ℹ️ What was cleaned",
                value="• Bot messages older than 1 hour\n"
                      "• Expired mod list records\n"
                      "• Orphaned database entries",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error during cleanup: {str(e)}", ephemeral=True)

    @app_commands.command(name="showmods", description="Show your complete mod list from recent upload")
    async def show_mods_command(self, interaction: discord.Interaction):
        """Show complete mod list via command (no button timeout)"""
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else None
        
        # Find the most recent mod list for this user
        most_recent = None
        most_recent_time = 0
        
        for list_id, data in self.bot.active_mod_lists.items():
            if (data.get('user_id') == user_id and 
                data.get('guild_id') == guild_id and
                data['timestamp'] > most_recent_time):
                most_recent = (list_id, data)
                most_recent_time = data['timestamp']
        
        if not most_recent:
            await interaction.followup.send("❌ No recent mod list found. Please upload a new mod list first.", ephemeral=True)
            return
        
        list_id, data = most_recent
        
        # Check if the mod list is too old (more than 24 hours)
        if time.time() - data['timestamp'] > 86400:  # 24 hours
            await interaction.followup.send("❌ Your mod list is too old (more than 24 hours). Please upload a new one.", ephemeral=True)
            return
        
        mods = data['mods']
        
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

    @app_commands.command(name="download", description="Get download link for your recent mod list")
    async def download_command(self, interaction: discord.Interaction):
        """Get download link via command (no button timeout)"""
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else None
        
        # Find the most recent mod list for this user
        most_recent = None
        most_recent_time = 0
        
        for list_id, data in self.bot.active_mod_lists.items():
            if (data.get('user_id') == user_id and 
                data.get('guild_id') == guild_id and
                data['timestamp'] > most_recent_time):
                most_recent = (list_id, data)
                most_recent_time = data['timestamp']
        
        if not most_recent:
            await interaction.followup.send("❌ No recent mod list found. Please upload a new mod list first.", ephemeral=True)
            return
        
        list_id, data = most_recent
        
        # Check if the mod list is too old (more than 24 hours)
        if time.time() - data['timestamp'] > 86400:  # 24 hours
            await interaction.followup.send("❌ Your mod list is too old (more than 24 hours). Please upload a new one.", ephemeral=True)
            return
        
        download_url = data.get('download_url')
        if download_url:
            await interaction.followup.send(f"📥 [Download your mod list HTML file]({download_url})", ephemeral=True)
        else:
            await interaction.followup.send("❌ Download link not available.", ephemeral=True)

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
    async def dlc_debug_legacy(self, ctx: commands.Context, mod_id: str | None = None):
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
        super().__init__(timeout=None)  # No timeout - persistent view
        self.list_id = list_id
        self.total_mods = total_mods
        self.current_page = 0
        self.mods_per_page = 10
    
    # Add custom_id for persistent views
    @discord.ui.button(label="📋 Show All Mods", style=discord.ButtonStyle.primary, custom_id="show_all_mods")
    async def show_all_mods(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show all mods in a private message to the user"""
        try:
            # Check if interaction is already responded to
            if interaction.response.is_done():
                return
                
            # Respond immediately to prevent interaction timeout
            await interaction.response.defer(ephemeral=True)
            
            # Get the bot instance and cast it properly
            bot = interaction.client
            if not isinstance(bot, ArmaModBot):
                await interaction.followup.send("❌ Bot configuration error - wrong bot type.", ephemeral=True)
                return
            
            # Try to get mod list from active lists first
            mods = None
            if self.list_id in bot.active_mod_lists:
                mods = bot.active_mod_lists[self.list_id]['mods']
            else:
                # Try to find a recent mod list for this user
                user_id = interaction.user.id
                guild_id = interaction.guild.id if interaction.guild else None
                
                most_recent = None
                most_recent_time = 0
                
                for list_id, data in bot.active_mod_lists.items():
                    if (data.get('user_id') == user_id and 
                        data.get('guild_id') == guild_id and
                        data['timestamp'] > most_recent_time):
                        most_recent = (list_id, data)
                        most_recent_time = data['timestamp']
                
                if most_recent and (time.time() - most_recent_time) <= 86400:  # 24 hours
                    mods = most_recent[1]['mods']
                else:
                    await interaction.followup.send("❌ No recent mod list found. Please upload a new mod list first.", ephemeral=True)
                    return
            
            if not mods:
                await interaction.followup.send("❌ Mod list not found. Please upload a new mod list first.", ephemeral=True)
                return
            
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
            
        except Exception as e:
            print(f"Error in show_all_mods button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="⬇️ DOWNLOAD", style=discord.ButtonStyle.secondary, emoji="📥", custom_id="download_modlist")
    async def download_modlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Download the original modlist HTML file"""
        try:
            # Check if interaction is already responded to
            if interaction.response.is_done():
                return
                
            # Get the bot instance and cast it properly
            bot = interaction.client
            if not isinstance(bot, ArmaModBot):
                await interaction.response.send_message("❌ Bot configuration error - wrong bot type.", ephemeral=True)
                return
            
            # Try to get mod list from active lists first
            download_url = None
            if self.list_id in bot.active_mod_lists:
                download_url = bot.active_mod_lists[self.list_id].get('download_url')
            else:
                # Try to find a recent mod list for this user
                user_id = interaction.user.id
                guild_id = interaction.guild.id if interaction.guild else None
                
                most_recent = None
                most_recent_time = 0
                
                for list_id, data in bot.active_mod_lists.items():
                    if (data.get('user_id') == user_id and 
                        data.get('guild_id') == guild_id and
                        data['timestamp'] > most_recent_time):
                        most_recent = (list_id, data)
                        most_recent_time = data['timestamp']
                
                if most_recent and (time.time() - most_recent_time) <= 86400:  # 24 hours
                    download_url = most_recent[1].get('download_url')
            
            if download_url:
                await interaction.response.send_message(f"📥 [Download your mod list HTML file]({download_url})", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Download link not available. Please upload a new mod list first.", ephemeral=True)
                
        except Exception as e:
            print(f"Error in download_modlist button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)
            except:
                pass
    
    @discord.ui.button(label="LMB Alpha 0.5.1", style=discord.ButtonStyle.secondary, custom_id="github_link")
    async def github_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Link to GitHub repository"""
        try:
            # Check if interaction is already responded to
            if interaction.response.is_done():
                return
                
            embed = discord.Embed(
                title="🔗 LoadmasterBot GitHub",
                description="View the source code and contribute to the project!",
                color=0x0099ff
            )
            embed.add_field(
                name="📁 Repository",
                value="[GitHub Repository](https://github.com/jfahler/loadmasterbot)",
                inline=False
            )
            embed.add_field(
                name="📋 Version",
                value="**LMB Alpha 0.5.1**",
                inline=False
            )
            embed.add_field(
                name="🤝 Contributing",
                value="Feel free to submit issues, feature requests, or pull requests!",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in github_link button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)
            except:
                pass

async def main():
    """Main function to run the bot"""
    bot = ArmaModBot()
    
    try:
        if not DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN environment variable is not set")
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Error running bot: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main()) 