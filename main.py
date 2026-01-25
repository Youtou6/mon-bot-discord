import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import io
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
import random

# ========== CONFIGURATION BOT ==========
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# ========== STOCKAGE MODMAIL ==========
modmail_tickets = {}
modmail_config = {}
modmail_blacklist = set()
modmail_cooldowns = {}
staff_notes = defaultdict(list)
ticket_counter = defaultdict(int)

# ========== STOCKAGE GIVEAWAY ==========
giveaways = {}
giveaway_participants = defaultdict(set)
giveaway_weights = defaultdict(dict)
giveaway_history = []
blocked_giveaway_users = set()

# ========== STOCKAGE AUTOMOD ==========
automod_config = {}
user_warnings = defaultdict(list)
user_messages = defaultdict(lambda: deque(maxlen=10))
user_infractions = defaultdict(int)
last_infraction = {}

# ========== CONFIG MODMAIL ==========
DEFAULT_MODMAIL_CONFIG = {
    'enabled': True,
    'category_id': None,
    'log_channel_id': None,
    'transcript_channel_id': None,
    'anonymous_staff': False,
    'cooldown_seconds': 300,
    'max_tickets_per_user': 1,
    'ping_role_id': None,
    'categories': {
        '📢': 'Signalement',
        '❓': 'Question',
        '⚠️': 'Réclamation',
        '🚫': 'Appel de sanction',
        '🤝': 'Partenariat',
        '🛠': 'Support technique',
        '📋': 'Autre'
    },
    'greeting_message': 'Merci de nous contacter ! Un membre du staff vous répondra bientôt.',
    'closing_message': 'Merci d\'avoir contacté notre équipe. Ce ticket est maintenant fermé.',
    'blocked_words': [],
    'satisfaction_survey': True,
}

# ========== CONFIG AUTOMOD ==========
DEFAULT_AUTOMOD_CONFIG = {
    'enabled': False,
    'log_channel': None,
    'immune_roles': [],
    'immune_channels': [],
    'spam_enabled': True,
    'spam_messages': 5,
    'spam_seconds': 5,
    'spam_action': 'mute',
    'flood_enabled': True,
    'flood_chars': 15,
    'flood_action': 'delete',
    'caps_enabled': True,
    'caps_percent': 70,
    'caps_min_length': 10,
    'caps_action': 'delete',
    'emoji_enabled': True,
    'emoji_max': 10,
    'emoji_action': 'delete',
    'badwords_enabled': True,
    'badwords_list': [],
    'badwords_action': 'delete',
    'links_enabled': True,
    'links_whitelist': [],
    'links_action': 'delete',
    'discord_invites': True,
    'discord_invites_action': 'delete',
    'mentions_enabled': True,
    'mentions_max': 5,
    'mentions_action': 'warn',
    'newaccount_enabled': False,
    'newaccount_days': 7,
    'newaccount_action': 'kick',
    'sanctions_enabled': True,
    'warn_threshold': 3,
    'mute_duration': 600,
    'kick_threshold': 5,
    'ban_threshold': 10,
}

DEFAULT_BADWORDS = ['merde', 'connard', 'salope', 'pute', 'fdp', 'ntm', 'pd', 'enculé']
SCAM_PATTERNS = [r'(free|gratuit).*(nitro|steam)', r'discord\.gift', r'(claim|réclame).*(gift|cadeau)']

# ========== VUES MODMAIL ==========

class TicketCategorySelectView(discord.ui.View):
    def __init__(self, user, guild):
        super().__init__(timeout=120)
        self.user = user
        self.guild = guild
        self.category = None
        
        config = modmail_config.get(guild.id, DEFAULT_MODMAIL_CONFIG)
        categories = config.get('categories', DEFAULT_MODMAIL_CONFIG['categories'])
        
        for emoji, name in list(categories.items())[:5]:
            button = discord.ui.Button(label=name, emoji=emoji, style=discord.ButtonStyle.primary)
            button.callback = self.make_callback(emoji, name)
            self.add_item(button)
    
    def make_callback(self, emoji, name):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                await interaction.response.send_message("❌ Ce n'est pas pour toi !", ephemeral=True)
                return
            self.category = f"{emoji} {name}"
            self.stop()
            await interaction.response.send_message(f"✅ Catégorie sélectionnée: **{name}**", ephemeral=True)
        return callback

class TicketControlView(discord.ui.View):
    def __init__(self, ticket_channel, user_id, guild_id):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="✍️ Note interne", style=discord.ButtonStyle.secondary, custom_id="add_note")
    async def add_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NoteModal(self.ticket_channel.id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🏷️ Claim", style=discord.ButtonStyle.primary, custom_id="claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id in modmail_tickets:
            modmail_tickets[self.user_id]['claimed_by'] = interaction.user.id
            embed = discord.Embed(title="✅ Ticket réclamé", description=f"Ticket pris en charge par {interaction.user.mention}", color=discord.Color.blue())
            await self.ticket_channel.send(embed=embed)
            await interaction.response.send_message("✅ Ticket réclamé !", ephemeral=True)
    
    @discord.ui.button(label="⚡ Urgent", style=discord.ButtonStyle.danger, custom_id="mark_urgent")
    async def mark_urgent(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id in modmail_tickets:
            modmail_tickets[self.user_id]['priority'] = 'haute'
            try:
                new_name = f"⚠️-{self.ticket_channel.name.replace('⚠️-', '')}"
                await self.ticket_channel.edit(name=new_name)
            except:
                pass
            config = modmail_config.get(self.guild_id, {})
            ping_role_id = config.get('ping_role_id')
            ping_text = ""
            if ping_role_id:
                role = interaction.guild.get_role(ping_role_id)
                if role:
                    ping_text = f"{role.mention} "
            embed = discord.Embed(title="⚠️ TICKET URGENT", description=f"{ping_text}Ce ticket nécessite une attention immédiate !", color=discord.Color.red(), timestamp=datetime.now())
            await self.ticket_channel.send(embed=embed)
            await interaction.response.send_message("✅ Ticket marqué urgent !", ephemeral=True)
    
    @discord.ui.button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, custom_id="save_transcript")
    async def save_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        transcript = await generate_transcript(self.ticket_channel, self.user_id)
        config = modmail_config.get(self.guild_id, {})
        transcript_channel_id = config.get('transcript_channel_id')
        if transcript_channel_id:
            channel = interaction.guild.get_channel(transcript_channel_id)
            if channel:
                file = discord.File(fp=io.BytesIO(transcript.encode('utf-8')), filename=f"ticket-{self.user_id}.txt")
                await channel.send(file=file)
        await interaction.followup.send("✅ Transcript sauvegardé !", ephemeral=True)
    
    @discord.ui.button(label="🔒 Fermer", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CloseConfirmView(self.ticket_channel, self.user_id, self.guild_id)
        await interaction.response.send_message("⚠️ Fermer ce ticket ?", view=view, ephemeral=True)

class CloseConfirmView(discord.ui.View):
    def __init__(self, ticket_channel, user_id, guild_id):
        super().__init__(timeout=30)
        self.ticket_channel = ticket_channel
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="✅ Oui, fermer", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        transcript = await generate_transcript(self.ticket_channel, self.user_id)
        config = modmail_config.get(self.guild_id, {})
        transcript_channel_id = config.get('transcript_channel_id')
        if transcript_channel_id:
            channel = interaction.guild.get_channel(transcript_channel_id)
            if channel:
                file = discord.File(fp=io.BytesIO(transcript.encode('utf-8')), filename=f"ticket-{self.user_id}.txt")
                embed = discord.Embed(title="🔒 Ticket fermé", color=discord.Color.red(), timestamp=datetime.now())
                await channel.send(embed=embed, file=file)
        user = bot.get_user(self.user_id)
        if user:
            try:
                embed = discord.Embed(title="🔒 Ticket fermé", description=config.get('closing_message', ''), color=discord.Color.red())
                if config.get('satisfaction_survey', True):
                    view = SatisfactionView(self.user_id, self.guild_id)
                    await user.send(embed=embed, view=view)
                else:
                    await user.send(embed=embed)
            except:
                pass
        if self.user_id in modmail_tickets:
            del modmail_tickets[self.user_id]
        await self.ticket_channel.delete()
        await interaction.followup.send("✅ Ticket fermé", ephemeral=True)
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Annulé", ephemeral=True)

class SatisfactionView(discord.ui.View):
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="⭐", style=discord.ButtonStyle.secondary)
    async def one_star(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, 1)
    
    @discord.ui.button(label="⭐⭐", style=discord.ButtonStyle.secondary)
    async def two_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, 2)
    
    @discord.ui.button(label="⭐⭐⭐", style=discord.ButtonStyle.secondary)
    async def three_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, 3)
    
    @discord.ui.button(label="⭐⭐⭐⭐", style=discord.ButtonStyle.primary)
    async def four_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, 4)
    
    @discord.ui.button(label="⭐⭐⭐⭐⭐", style=discord.ButtonStyle.success)
    async def five_stars(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_rating(interaction, 5)
    
    async def handle_rating(self, interaction, rating):
        modal = SatisfactionCommentModal(rating, self.user_id, self.guild_id)
        await interaction.response.send_modal(modal)

class SatisfactionCommentModal(discord.ui.Modal, title="Commentaire (optionnel)"):
    def __init__(self, rating, user_id, guild_id):
        super().__init__()
        self.rating = rating
        self.user_id = user_id
        self.guild_id = guild_id
    
    comment = discord.ui.TextInput(label="Votre avis", style=discord.TextStyle.paragraph, placeholder="Optionnel...", required=False, max_length=500)
    
    async def on_submit(self, interaction: discord.Interaction):
        config = modmail_config.get(self.guild_id, {})
        log_channel_id = config.get('log_channel_id')
        if log_channel_id:
            channel = bot.get_guild(self.guild_id).get_channel(log_channel_id)
            if channel:
                embed = discord.Embed(title="⭐ Satisfaction", description=f"**Note:** {'⭐' * self.rating}", color=discord.Color.gold())
                if self.comment.value:
                    embed.add_field(name="💬 Commentaire", value=f"```{self.comment.value}```", inline=False)
                await channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Merci ! {'⭐' * self.rating}", ephemeral=True)

class NoteModal(discord.ui.Modal, title="Note interne"):
    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id
    
    note_input = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph, required=True, max_length=1000)
    
    async def on_submit(self, interaction: discord.Interaction):
        staff_notes[self.channel_id].append({'author': interaction.user.name, 'note': self.note_input.value, 'timestamp': datetime.now()})
        embed = discord.Embed(title="📝 Note interne", description=self.note_input.value, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)

async def generate_transcript(channel, user_id):
    lines = [f"TRANSCRIPT - {datetime.now().strftime('%d/%m/%Y %H:%M')}", "="*60, ""]
    async for message in channel.history(limit=None, oldest_first=True):
        if message.content:
            lines.append(f"[{message.created_at.strftime('%H:%M')}] {message.author.name}: {message.content}")
    return "\n".join(lines)

def check_cooldown_modmail(user_id):
    if user_id in modmail_cooldowns:
        time_left = (modmail_cooldowns[user_id] - datetime.now()).total_seconds()
        if time_left > 0:
            return int(time_left)
    return 0

# ========== VUES GIVEAWAY ==========

class GiveawayCreateModal(discord.ui.Modal, title="🎁 Créer un Giveaway"):
    prize_input = discord.ui.TextInput(label="🏆 Prix", placeholder="Ex: Nitro 1 mois", required=True, max_length=100)
    duration_input = discord.ui.TextInput(label="⏱️ Durée (ex: 2h, 1d 2h)", placeholder="2h", required=True, max_length=20)
    winners_input = discord.ui.TextInput(label="👥 Gagnants", placeholder="1", required=True, max_length=2)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Utilisez `/giveaway_quick` pour créer rapidement !", ephemeral=True)

class GiveawayParticipateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🎉 Participer", style=discord.ButtonStyle.success, custom_id="giveaway_participate")
    async def participate(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = interaction.message.id
        if message_id not in giveaways:
            await interaction.response.send_message("❌ Giveaway introuvable", ephemeral=True)
            return
        giveaway = giveaways[message_id]
        if not giveaway['active']:
            await interaction.response.send_message("❌ Terminé", ephemeral=True)
            return
        if interaction.user.id in giveaway_participants[message_id]:
            giveaway_participants[message_id].remove(interaction.user.id)
            await update_participant_count(interaction.message, message_id)
            await interaction.response.send_message("❌ Participation annulée", ephemeral=True)
            return
        giveaway_participants[message_id].add(interaction.user.id)
        await update_participant_count(interaction.message, message_id)
        await interaction.response.send_message("✅ Vous participez !", ephemeral=True)

def format_duration(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}j")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}min")
    return " ".join(parts) if parts else "0s"

async def update_participant_count(message, message_id):
    try:
        embed = message.embeds[0]
        count = len(giveaway_participants[message_id])
        for i, field in enumerate(embed.fields):
            if "Participants" in field.name:
                embed.set_field_at(i, name="👥 Participants", value=str(count), inline=True)
                break
        await message.edit(embed=embed)
    except:
        pass

async def giveaway_countdown(message_id, duration):
    await asyncio.sleep(duration)
    if message_id in giveaways:
        await end_giveaway(message_id)

async def end_giveaway(message_id):
    if message_id not in giveaways:
        return
    giveaway = giveaways[message_id]
    giveaway['active'] = False
    guild = bot.get_guild(giveaway['guild_id'])
    if not guild:
        return
    channel = guild.get_channel(giveaway['channel_id'])
    if not channel:
        return
    try:
        message = await channel.fetch_message(message_id)
    except:
        return
    participants = list(giveaway_participants[message_id])
    if len(participants) == 0:
        embed = discord.Embed(title="🎁 Giveaway annulé", description="Aucun participant", color=0xED4245)
        await message.edit(embed=embed, view=None)
        return
    winners = random.sample(participants, min(giveaway['winners'], len(participants)))
    embed = discord.Embed(title="🎉 Giveaway terminé !", description=f"**{giveaway['prize']}**", color=0x57F287)
    winners_text = "\n".join([f"🏆 <@{w}>" for w in winners])
    embed.add_field(name="Gagnants", value=winners_text, inline=False)
    await message.edit(embed=embed, view=None)
    await channel.send(f"🎊 Félicitations {', '.join([f'<@{w}>' for w in winners])} !")
    for winner_id in winners:
        user = guild.get_member(winner_id)
        if user:
            try:
                await user.send(f"🎉 Vous avez gagné **{giveaway['prize']}** sur **{guild.name}** !")
            except:
                pass

# ========== FONCTIONS AUTOMOD ==========

def is_immune(member, channel, guild_id):
    config = automod_config.get(guild_id, DEFAULT_AUTOMOD_CONFIG)
    if member.guild_permissions.administrator:
        return True
    for role in member.roles:
        if role.id in config.get('immune_roles', []):
            return True
    if channel.id in config.get('immune_channels', []):
        return True
    return False

def check_spam(user_id, guild_id):
    config = automod_config.get(guild_id, DEFAULT_AUTOMOD_CONFIG)
    if not config.get('spam_enabled', True):
        return False
    now = datetime.now()
    user_messages[user_id].append(now)
    window = timedelta(seconds=config.get('spam_seconds', 5))
    recent = sum(1 for ts in user_messages[user_id] if now - ts < window)
    return recent > config.get('spam_messages', 5)

def check_badwords(content, guild_id):
    config = automod_config.get(guild_id, DEFAULT_AUTOMOD_CONFIG)
    if not config.get('badwords_enabled', True):
        return None
    badwords = config.get('badwords_list', DEFAULT_BADWORDS)
    normalized = re.sub(r'[^a-zA-Z0-9]', '', content.lower())
    for word in badwords:
        if word in content.lower() or re.sub(r'[^a-z0-9]', '', word) in normalized:
            return word
    return None

async def apply_automod_action(message, action, reason, guild_id):
    try:
        await message.delete()
    except:
        pass
    user_infractions[message.author.id] += 1
    config = automod_config.get(guild_id, DEFAULT_AUTOMOD_CONFIG)
    if user_infractions[message.author.id] >= config.get('warn_threshold', 3):
        try:
            await message.author.timeout(timedelta(seconds=config.get('mute_duration', 600)), reason=f"AutoMod: {reason}")
        except:
            pass
    await log_automod_action(message.guild, message.author, message.channel, reason, action, guild_id)

async def log_automod_action(guild, user, channel, reason, action, guild_id):
    config = automod_config.get(guild_id, DEFAULT_AUTOMOD_CONFIG)
    log_channel_id = config.get('log_channel')
    if not log_channel_id:
        return
    log_channel = guild.get_channel(log_channel_id)
    if not log_channel:
        return
    embed = discord.Embed(title=f"🛡️ AutoMod • {action.upper()}", color=0xED4245, timestamp=datetime.now())
    embed.add_field(name="User", value=f"{user.mention}", inline=True)
    embed.add_field(name="Salon", value=channel.mention, inline=True)
    embed.add_field(name="Raison", value=f"`{reason}`", inline=False)
    await log_channel.send(embed=embed)

async def process_automod(message):
    if message.author.bot or not message.guild:
        return
    guild_id = message.guild.id
    config = automod_config.get(guild_id, DEFAULT_AUTOMOD_CONFIG)
    if not config.get('enabled', False):
        return
    if is_immune(message.author, message.channel, guild_id):
        return
    content = message.content
    # Spam
    if check_spam(message.author.id, guild_id):
        await apply_automod_action(message, 'mute', 'Spam', guild_id)
        return
    # Mots interdits
    badword = check_badwords(content, guild_id)
    if badword:
        await apply_automod_action(message, 'delete', 'Langage inapproprié', guild_id)
        return
    # Invitations Discord
    if config.get('discord_invites', True) and re.search(r'discord\.gg/', content.lower()):
        await apply_automod_action(message, 'delete', 'Invitation Discord', guild_id)
        return

# ========== COMMANDES MODMAIL ==========

@bot.tree.command(name="modmail_setup", description="⚙️ [ADMIN] Configurer le ModMail")
async def modmail_setup(interaction: discord.Interaction, categorie: discord.CategoryChannel, logs: discord.TextChannel, transcripts: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if guild_id not in modmail_config:
        modmail_config[guild_id] = DEFAULT_MODMAIL_CONFIG.copy()
    modmail_config[guild_id]['category_id'] = categorie.id
    modmail_config[guild_id]['log_channel_id'] = logs.id
    modmail_config[guild_id]['transcript_channel_id'] = transcripts.id
    embed = discord.Embed(title="✅ ModMail configuré !", color=0x57F287)
    embed.add_field(name="Catégorie", value=categorie.mention, inline=False)
    embed.add_field(name="Logs", value=logs.mention, inline=True)
    embed.add_field(name="Transcripts", value=transcripts.mention, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="close", description="[STAFF] Fermer le ticket actuel")
async def close_ticket_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    ticket_user_id = None
    for user_id, data in modmail_tickets.items():
        if data['channel_id'] == interaction.channel.id:
            ticket_user_id = user_id
            break
    if not ticket_user_id:
        await interaction.response.send_message("❌ Pas un ticket", ephemeral=True)
        return
    view = CloseConfirmView(interaction.channel, ticket_user_id, interaction.guild.id)
    await interaction.response.send_message("⚠️ Fermer ?", view=view, ephemeral=True)

# ========== COMMANDES GIVEAWAY ==========

@bot.tree.command(name="giveaway_quick", description="🚀 Créer un giveaway")
async def giveaway_quick(interaction: discord.Interaction, salon: discord.TextChannel, prix: str, duree: str, gagnants: int = 1):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    duration_str = duree.lower()
    duration_seconds = 0
    try:
        days = re.search(r'(\d+)d', duration_str)
        hours = re.search(r'(\d+)h', duration_str)
        minutes = re.search(r'(\d+)m', duration_str)
        if days:
            duration_seconds += int(days.group(1)) * 86400
        if hours:
            duration_seconds += int(hours.group(1)) * 3600
        if minutes:
            duration_seconds += int(minutes.group(1)) * 60
        if duration_seconds == 0:
            await interaction.response.send_message("❌ Durée invalide", ephemeral=True)
            return
    except:
        await interaction.response.send_message("❌ Erreur durée", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    end_time = datetime.now() + timedelta(seconds=duration_seconds)
    embed = discord.Embed(title=f"🎁 {prix}", description="Cliquez sur **Participer** !", color=0xF1C40F, timestamp=end_time)
    embed.add_field(name="🏆 Gagnants", value=str(gagnants), inline=True)
    embed.add_field(name="⏱️ Fin dans", value=format_duration(duration_seconds), inline=True)
    embed.add_field(name="👥 Participants", value="0", inline=True)
    view = GiveawayParticipateView()
    message = await salon.send(content="🎉 **NOUVEAU GIVEAWAY !**", embed=embed, view=view)
    giveaways[message.id] = {'prize': prix, 'winners': gagnants, 'end_time': end_time, 'creator_id': interaction.user.id,
    @bot.tree.command(name="giveaway_reroll", description="🎲 Re-tirer un gagnant")
async def giveaway_reroll(interaction: discord.Interaction, message_id: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    try:
        msg_id = int(message_id)
    except:
        await interaction.response.send_message("❌ ID invalide", ephemeral=True)
        return
    if msg_id not in giveaways:
        await interaction.response.send_message("❌ Introuvable", ephemeral=True)
        return
    participants = list(giveaway_participants[msg_id])
    if len(participants) == 0:
        await interaction.response.send_message("❌ Aucun participant", ephemeral=True)
        return
    new_winner = random.choice(participants)
    await interaction.response.send_message(f"🎉 Nouveau gagnant : <@{new_winner}> !", ephemeral=False)

@bot.tree.command(name="giveaway_list", description="📋 Liste des giveaways actifs")
async def giveaway_list(interaction: discord.Interaction):
    active = [g for g in giveaways.values() if g['active'] and g['guild_id'] == interaction.guild.id]
    if not active:
        await interaction.response.send_message("✅ Aucun giveaway actif", ephemeral=True)
        return
    embed = discord.Embed(title="📋 Giveaways actifs", color=0xF1C40F)
    for g in active[:10]:
        time_left = (g['end_time'] - datetime.now()).total_seconds()
        embed.add_field(name=f"🎁 {g['prize']}", value=f"Fin: {format_duration(int(time_left))}\nGagnants: {g['winners']}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== COMMANDES AUTOMOD ==========

@bot.tree.command(name="automod_setup", description="⚙️ [ADMIN] Configurer AutoMod")
async def automod_setup(interaction: discord.Interaction, log_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_AUTOMOD_CONFIG.copy()
    automod_config[guild_id]['log_channel'] = log_channel.id
    automod_config[guild_id]['enabled'] = True
    automod_config[guild_id]['badwords_list'] = DEFAULT_BADWORDS.copy()
    embed = discord.Embed(title="✅ AutoMod configuré !", color=0x57F287)
    embed.add_field(name="📊 Logs", value=log_channel.mention, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="automod_toggle", description="🔄 Activer/Désactiver AutoMod")
async def automod_toggle(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_AUTOMOD_CONFIG.copy()
    automod_config[guild_id]['enabled'] = not automod_config[guild_id]['enabled']
    status = "✅ ACTIVÉ" if automod_config[guild_id]['enabled'] else "❌ DÉSACTIVÉ"
    await interaction.response.send_message(f"AutoMod: {status}", ephemeral=True)

@bot.tree.command(name="automod_badword", description="🚫 Ajouter un mot interdit")
async def automod_badword(interaction: discord.Interaction, mot: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_AUTOMOD_CONFIG.copy()
    if 'badwords_list' not in automod_config[guild_id]:
        automod_config[guild_id]['badwords_list'] = DEFAULT_BADWORDS.copy()
    automod_config[guild_id]['badwords_list'].append(mot.lower())
    await interaction.response.send_message(f"✅ `{mot}` ajouté", ephemeral=True)

@bot.tree.command(name="automod_whitelist", description="➕ Autoriser un domaine")
async def automod_whitelist(interaction: discord.Interaction, domaine: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    guild_id = interaction.guild.id
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_AUTOMOD_CONFIG.copy()
    if 'links_whitelist' not in automod_config[guild_id]:
        automod_config[guild_id]['links_whitelist'] = []
    automod_config[guild_id]['links_whitelist'].append(domaine.lower())
    await interaction.response.send_message(f"✅ `{domaine}` autorisé", ephemeral=True)

@bot.tree.command(name="automod_stats", description="📊 Stats AutoMod")
async def automod_stats(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    guild_id = interaction.guild.id
    config = automod_config.get(guild_id, DEFAULT_AUTOMOD_CONFIG)
    embed = discord.Embed(title="📊 Stats AutoMod", color=0x5865F2)
    status = "🟢 Actif" if config.get('enabled') else "🔴 Inactif"
    embed.add_field(name="Statut", value=status, inline=True)
    top_users = sorted(user_infractions.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_users:
        top_text = "\n".join([f"<@{uid}>: {count}" for uid, count in top_users])
        embed.add_field(name="Top infractions", value=top_text, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== ÉVÉNEMENT PRINCIPAL ==========

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # AUTOMOD (priorité)
    if message.guild:
        try:
            await process_automod(message)
        except Exception as e:
            print(f"Erreur AutoMod: {e}")
    
    # MODMAIL DM
    if isinstance(message.channel, discord.DMChannel):
        user = message.author
        
        # Ticket existant
        if user.id in modmail_tickets:
            ticket_data = modmail_tickets[user.id]
            guild = bot.get_guild(ticket_data['guild_id'])
            if guild:
                channel = guild.get_channel(ticket_data['channel_id'])
                if channel:
                    embed = discord.Embed(description=message.content, color=0x5865F2, timestamp=datetime.now())
                    embed.set_author(name=user.name, icon_url=user.display_avatar.url)
                    if message.attachments:
                        embed.set_image(url=message.attachments[0].url)
                    await channel.send(embed=embed)
                    await message.add_reaction('✅')
                    return
        
        # Nouveau ticket
        mutual_guilds = [g for g in bot.guilds if g.get_member(user.id)]
        if not mutual_guilds:
            await message.channel.send("❌ Aucun serveur commun")
            return
        
        target_guild = None
        for guild in mutual_guilds:
            if guild.id in modmail_config and modmail_config[guild.id].get('category_id'):
                target_guild = guild
                break
        
        if not target_guild:
            await message.channel.send("❌ ModMail non configuré")
            return
        
        config = modmail_config[target_guild.id]
        cooldown = check_cooldown_modmail(user.id)
        if cooldown > 0:
            await message.channel.send(f"⏳ Attendez {cooldown}s")
            return
        
        # Sélection catégorie
        embed = discord.Embed(title="🎫 Création ticket", description=f"Sélectionnez une catégorie sur **{target_guild.name}**", color=0x5865F2)
        view = TicketCategorySelectView(user, target_guild)
        await message.channel.send(embed=embed, view=view)
        await view.wait()
        
        if not view.category:
            await message.channel.send("❌ Temps écoulé")
            return
        
        # Animation création
        progress_embed = discord.Embed(title="⏳ Création en cours...", description="", color=0x5865F2)
        steps = [
            ("Vérification...", "✅ Vérifié"),
            ("Création salon...", "✅ Salon créé"),
            ("Configuration...", "✅ Configuré"),
            ("Finalisation...", "✅ Prêt !")
        ]
        progress_msg = await message.channel.send(embed=progress_embed)
        completed = []
        for i, (current, done) in enumerate(steps):
            completed.append(done)
            progress_text = "\n".join(completed)
            if i < len(steps) - 1:
                progress_text += f"\n🔄 {steps[i+1][0]}"
            progress_embed.description = progress_text
            await progress_msg.edit(embed=progress_embed)
            await asyncio.sleep(0.8)
        
        # Créer ticket
        try:
            category = target_guild.get_channel(config['category_id'])
            ticket_counter[target_guild.id] += 1
            ticket_num = ticket_counter[target_guild.id]
            channel_name = f"modmail-{user.name}-{ticket_num}".lower().replace(" ", "-")[:50]
            ticket_channel = await category.create_text_channel(name=channel_name, topic=f"ModMail {user.name} ({user.id})")
            await ticket_channel.set_permissions(target_guild.default_role, view_channel=False)
            await ticket_channel.set_permissions(user, view_channel=True, send_messages=False, read_messages=True)
            for role in target_guild.roles:
                if role.permissions.manage_messages or role.permissions.administrator:
                    await ticket_channel.set_permissions(role, view_channel=True, send_messages=True)
            
            modmail_tickets[user.id] = {'channel_id': ticket_channel.id, 'guild_id': target_guild.id, 'category': view.category, 'created_at': datetime.now()}
            modmail_cooldowns[user.id] = datetime.now() + timedelta(seconds=config.get('cooldown_seconds', 300))
            
            member = target_guild.get_member(user.id)
            embed_ticket = discord.Embed(title=f"🎫 Ticket #{ticket_num}", description=f"Nouveau ticket de {user.mention}", color=0x5865F2, timestamp=datetime.now())
            embed_ticket.add_field(name="💬 Message initial", value=f"```{message.content[:200]}```", inline=False)
            embed_ticket.add_field(name="📂 Catégorie", value=view.category, inline=True)
            embed_ticket.add_field(name="🆔 Ticket", value=f"#{ticket_num}", inline=True)
            
            if member:
                account_age = (datetime.now() - user.created_at.replace(tzinfo=None)).days
                embed_ticket.add_field(name="👤 Infos", value=f"**ID:** `{user.id}`\n**Compte:** {account_age}j", inline=False)
            
            embed_ticket.set_thumbnail(url=user.display_avatar.url)
            view_control = TicketControlView(ticket_channel, user.id, target_guild.id)
            await ticket_channel.send(embed=embed_ticket, view=view_control)
            
            ping_role_id = config.get('ping_role_id')
            if ping_role_id:
                role = target_guild.get_role(ping_role_id)
                if role:
                    await ticket_channel.send(f"{role.mention} **Nouveau ticket !**")
            
            greeting = config.get('greeting_message', DEFAULT_MODMAIL_CONFIG['greeting_message'])
            embed_welcome = discord.Embed(title="✅ Ticket créé !", description=greeting, color=0x57F287)
            embed_welcome.add_field(name="🏢 Serveur", value=target_guild.name, inline=True)
            embed_welcome.add_field(name="📂 Catégorie", value=view.category, inline=True)
            embed_welcome.add_field(name="🎫 Numéro", value=f"#{ticket_num}", inline=True)
            
            try:
                await progress_msg.delete()
            except:
                pass
            
            await message.channel.send(embed=embed_welcome)
        except Exception as e:
            await message.channel.send(f"❌ Erreur: {str(e)}")
        
        return
    
    # Messages dans tickets
    if message.guild:
        ticket_user_id = None
        for user_id, data in modmail_tickets.items():
            if data['channel_id'] == message.channel.id:
                ticket_user_id = user_id
                break
        
        if ticket_user_id:
            user = bot.get_user(ticket_user_id)
            if user:
                config = modmail_config.get(message.guild.id, {})
                anonymous = config.get('anonymous_staff', False)
                embed = discord.Embed(description=message.content, color=0x57F287, timestamp=datetime.now())
                if anonymous:
                    embed.set_author(name="Équipe Staff", icon_url=message.guild.icon.url if message.guild.icon else None)
                else:
                    embed.set_author(name=f"{message.author.name} (Staff)", icon_url=message.author.display_avatar.url)
                embed.set_footer(text=f"{message.guild.name} • Réponse", icon_url=message.guild.icon.url if message.guild.icon else None)
                if message.attachments:
                    embed.set_image(url=message.attachments[0].url)
                try:
                    await user.send(embed=embed)
                    await message.add_reaction('✅')
                except:
                    await message.channel.send("⚠️ DM fermés")
            return
    
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'{bot.user} connecté !')
    activity = discord.Streaming(name="HelpDesk", url="https://twitch.tv/helpdesk")
    await bot.change_presence(activity=activity, status=discord.Status.online)
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} commandes synchronisées')
    except Exception as e:
        print(f'❌ Erreur sync: {e}')

# Serveur Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot actif !"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# Lancement
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("❌ Token non trouvé !")
else:
    print("✅ Token trouvé, démarrage...")
    keep_alive()
    bot.run(TOKEN)
