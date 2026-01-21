import discord
from discord.ext import commands
from discord import app_commands
import requests
import json
import os
import re
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio

# Configuration du bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Stockage des données
roblox_links = {}
warnings = {}
config_serveur = {}
automod_config = {}
user_infractions = defaultdict(lambda: defaultdict(int))
message_history = defaultdict(lambda: [])
spam_tracker = defaultdict(lambda: {'count': 0, 'last_time': datetime.now()})

# Configuration AutoMod par défaut
DEFAULT_AUTOMOD = {
    'enabled': False,
    # Anti-spam
    'anti_spam': {'enabled': False, 'max_messages': 5, 'timeframe': 5, 'action': 'warn'},
    'anti_mention': {'enabled': False, 'max_mentions': 5, 'action': 'warn'},
    'anti_duplicate': {'enabled': False, 'max_duplicates': 3, 'action': 'delete'},
    'anti_flood': {'enabled': False, 'max_chars_repeat': 10, 'action': 'warn'},
    'anti_emoji_spam': {'enabled': False, 'max_emojis': 10, 'action': 'delete'},
    'anti_caps': {'enabled': False, 'caps_percent': 70, 'action': 'warn'},
    
    # Sécurité
    'account_age': {'enabled': False, 'min_days': 7, 'action': 'kick'},
    'raid_mode': {'enabled': False, 'joins_threshold': 10, 'timeframe': 60},
    'auto_slowmode': {'enabled': False, 'trigger_messages': 20, 'slowmode_seconds': 5},
    
    # Filtres de contenu
    'filter_insults': {'enabled': False, 'action': 'delete', 'words': []},
    'filter_slurs': {'enabled': False, 'action': 'ban'},
    'filter_nsfw': {'enabled': False, 'action': 'delete'},
    'filter_violence': {'enabled': False, 'action': 'warn'},
    
    # Liens
    'anti_discord_links': {'enabled': False, 'action': 'delete', 'whitelist': []},
    'anti_suspicious_links': {'enabled': False, 'action': 'delete'},
    'anti_scam': {'enabled': False, 'action': 'ban'},
    'domain_whitelist': {'enabled': False, 'domains': []},
    
    # Sanctions automatiques
    'auto_sanctions': {'enabled': False, 'warn_threshold': 3, 'mute_threshold': 5, 'kick_threshold': 7, 'ban_threshold': 10},
    'sanction_decay': {'enabled': False, 'days': 30},
    
    # Nouveaux membres
    'welcome_dm': {'enabled': False, 'message': 'Bienvenue sur le serveur !'},
    'auto_role': {'enabled': False, 'role_id': None},
    'verification': {'enabled': False, 'method': 'button'},
    
    # Logs
    'log_deleted': {'enabled': False, 'channel_id': None},
    'log_edited': {'enabled': False, 'channel_id': None},
    'log_joins': {'enabled': False, 'channel_id': None},
    'log_automod': {'enabled': False, 'channel_id': None},
    
    # Salons immunisés
    'immune_channels': [],
    'immune_roles': [],
}

# Listes de mots interdits (exemples de base)
INSULTS = ['con', 'idiot', 'débile', 'crétin', 'imbécile', 'connard', 'salope', 'pute']
SLURS = ['pd', 'tapette', 'nègre', 'bougnoule', 'youpin']
NSFW_WORDS = ['porn', 'sex', 'nude', 'xxx', 'hentai']
VIOLENCE_WORDS = ['tuer', 'mort', 'suicide', 'arme', 'explosif']
SCAM_PATTERNS = [
    r'(free|gratuit).*(nitro|steam|robux)',
    r'(claim|réclame).*(gift|cadeau)',
    r'discord\.gift',
    r'steamcommunity\.(ru|cn)',
]

# ========== PANEL AUTOMOD ==========

class AutoModMainView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
    
    @discord.ui.button(label="🔒 Sécurité & Anti-raid", style=discord.ButtonStyle.danger, row=0)
    async def security_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SecurityConfigView(self.guild_id)
        embed = discord.Embed(title="🔒 Configuration Sécurité & Anti-raid", color=discord.Color.red())
        embed.description = "Configure la protection contre les raids et le spam"
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🚫 Modération de contenu", style=discord.ButtonStyle.primary, row=0)
    async def content_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ContentConfigView(self.guild_id)
        embed = discord.Embed(title="🚫 Modération de contenu", color=discord.Color.blue())
        embed.description = "Filtre les insultes, propos haineux, NSFW..."
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🔗 Liens & Publicité", style=discord.ButtonStyle.success, row=1)
    async def links_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LinksConfigView(self.guild_id)
        embed = discord.Embed(title="🔗 Liens & Publicité", color=discord.Color.green())
        embed.description = "Contrôle les liens Discord, scam, self-promo..."
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="⚖️ Sanctions automatiques", style=discord.ButtonStyle.secondary, row=1)
    async def sanctions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SanctionsConfigView(self.guild_id)
        embed = discord.Embed(title="⚖️ Sanctions automatiques", color=discord.Color.orange())
        embed.description = "Configure l'escalade des sanctions"
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="👤 Nouveaux membres", style=discord.ButtonStyle.primary, row=2)
    async def members_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MembersConfigView(self.guild_id)
        embed = discord.Embed(title="👤 Gestion des nouveaux membres", color=discord.Color.purple())
        embed.description = "Bienvenue, vérification, rôle auto..."
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="📊 Logs & Transparence", style=discord.ButtonStyle.secondary, row=2)
    async def logs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LogsConfigView(self.guild_id)
        embed = discord.Embed(title="📊 Logs & Transparence", color=discord.Color.blurple())
        embed.description = "Configure les salons de logs"
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="✅ Activer/Désactiver AutoMod", style=discord.ButtonStyle.danger, row=3)
    async def toggle_automod(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.guild_id not in automod_config:
            automod_config[self.guild_id] = DEFAULT_AUTOMOD.copy()
        
        automod_config[self.guild_id]['enabled'] = not automod_config[self.guild_id]['enabled']
        status = "✅ ACTIVÉ" if automod_config[self.guild_id]['enabled'] else "❌ DÉSACTIVÉ"
        
        await interaction.response.send_message(f"AutoMod est maintenant {status} !", ephemeral=True)
    
    @discord.ui.button(label="📋 Voir la configuration", style=discord.ButtonStyle.success, row=3)
    async def view_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config.get(self.guild_id, DEFAULT_AUTOMOD)
        
        embed = discord.Embed(title="📋 Configuration AutoMod actuelle", color=discord.Color.gold())
        
        status = "✅ Activé" if config['enabled'] else "❌ Désactivé"
        embed.add_field(name="Statut global", value=status, inline=False)
        
        # Compte les modules actifs
        active_modules = sum(1 for key, val in config.items() 
                            if isinstance(val, dict) and val.get('enabled', False))
        
        embed.add_field(name="Modules actifs", value=f"{active_modules} modules", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SecurityConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        if self.guild_id not in automod_config:
            automod_config[self.guild_id] = DEFAULT_AUTOMOD.copy()
    
    @discord.ui.button(label="Anti-Spam", style=discord.ButtonStyle.secondary)
    async def toggle_spam(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['anti_spam']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Anti-Spam: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Anti-Mentions", style=discord.ButtonStyle.secondary)
    async def toggle_mentions(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['anti_mention']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Anti-Mentions: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Anti-Flood", style=discord.ButtonStyle.secondary)
    async def toggle_flood(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['anti_flood']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Anti-Flood: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Mode Anti-Raid", style=discord.ButtonStyle.danger)
    async def toggle_raid(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['raid_mode']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Mode Anti-Raid: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Âge compte minimum", style=discord.ButtonStyle.secondary)
    async def toggle_age(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['account_age']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Vérif âge compte: {config['enabled']} (min {config['min_days']} jours)", ephemeral=True)

class ContentConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        if self.guild_id not in automod_config:
            automod_config[self.guild_id] = DEFAULT_AUTOMOD.copy()
    
    @discord.ui.button(label="Filtre Insultes", style=discord.ButtonStyle.secondary)
    async def toggle_insults(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['filter_insults']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Filtre insultes: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Filtre Propos Haineux", style=discord.ButtonStyle.danger)
    async def toggle_slurs(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['filter_slurs']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Filtre propos haineux: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Filtre NSFW", style=discord.ButtonStyle.secondary)
    async def toggle_nsfw(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['filter_nsfw']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Filtre NSFW: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Filtre Violence", style=discord.ButtonStyle.secondary)
    async def toggle_violence(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['filter_violence']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Filtre violence: {config['enabled']}", ephemeral=True)

class LinksConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        if self.guild_id not in automod_config:
            automod_config[self.guild_id] = DEFAULT_AUTOMOD.copy()
    
    @discord.ui.button(label="Anti-Discord Links", style=discord.ButtonStyle.secondary)
    async def toggle_discord(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['anti_discord_links']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Anti-Discord Links: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Anti-Scam", style=discord.ButtonStyle.danger)
    async def toggle_scam(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['anti_scam']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Anti-Scam: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Liens Suspects", style=discord.ButtonStyle.secondary)
    async def toggle_suspicious(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['anti_suspicious_links']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Anti-Liens suspects: {config['enabled']}", ephemeral=True)

class SanctionsConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        if self.guild_id not in automod_config:
            automod_config[self.guild_id] = DEFAULT_AUTOMOD.copy()
    
    @discord.ui.button(label="Activer Sanctions Auto", style=discord.ButtonStyle.success)
    async def toggle_sanctions(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['auto_sanctions']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Sanctions automatiques: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Voir les seuils", style=discord.ButtonStyle.primary)
    async def view_thresholds(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['auto_sanctions']
        
        embed = discord.Embed(title="⚖️ Seuils de sanctions", color=discord.Color.orange())
        embed.add_field(name="⚠️ Warn", value=f"{config['warn_threshold']} infractions", inline=True)
        embed.add_field(name="🔇 Mute", value=f"{config['mute_threshold']} infractions", inline=True)
        embed.add_field(name="👢 Kick", value=f"{config['kick_threshold']} infractions", inline=True)
        embed.add_field(name="🔨 Ban", value=f"{config['ban_threshold']} infractions", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MembersConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        if self.guild_id not in automod_config:
            automod_config[self.guild_id] = DEFAULT_AUTOMOD.copy()
    
    @discord.ui.button(label="Message DM Bienvenue", style=discord.ButtonStyle.secondary)
    async def toggle_dm(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['welcome_dm']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Message DM: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Rôle Automatique", style=discord.ButtonStyle.secondary)
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['auto_role']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Rôle auto: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Vérification", style=discord.ButtonStyle.success)
    async def toggle_verification(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['verification']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Vérification: {config['enabled']}", ephemeral=True)

class LogsConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        if self.guild_id not in automod_config:
            automod_config[self.guild_id] = DEFAULT_AUTOMOD.copy()
    
    @discord.ui.button(label="Logs Messages Supprimés", style=discord.ButtonStyle.secondary)
    async def toggle_deleted(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['log_deleted']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Logs suppression: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Logs Éditions", style=discord.ButtonStyle.secondary)
    async def toggle_edited(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['log_edited']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Logs éditions: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Logs Joins/Leaves", style=discord.ButtonStyle.secondary)
    async def toggle_joins(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['log_joins']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Logs arrivées: {config['enabled']}", ephemeral=True)
    
    @discord.ui.button(label="Logs AutoMod", style=discord.ButtonStyle.success)
    async def toggle_automod_logs(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = automod_config[self.guild_id]['log_automod']
        config['enabled'] = not config['enabled']
        status = "✅" if config['enabled'] else "❌"
        await interaction.response.send_message(f"{status} Logs AutoMod: {config['enabled']}", ephemeral=True)

@bot.tree.command(name="automod", description="[ADMIN] Panel de configuration AutoMod complet")
async def automod_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Seuls les administrateurs peuvent utiliser cette commande !", ephemeral=True)
        return
    
    if interaction.guild.id not in automod_config:
        automod_config[interaction.guild.id] = DEFAULT_AUTOMOD.copy()
    
    embed = discord.Embed(
        title="🛡️ Panel AutoMod - Configuration Complète",
        description="Bienvenue dans le panneau de configuration AutoMod !\n\n"
                   "Utilisez les boutons ci-dessous pour configurer chaque module.",
        color=discord.Color.gold()
    )
    
    status = "✅ **ACTIVÉ**" if automod_config[interaction.guild.id]['enabled'] else "❌ **DÉSACTIVÉ**"
    embed.add_field(name="Statut AutoMod", value=status, inline=False)
    
    embed.set_footer(text="Cliquez sur les boutons pour configurer chaque catégorie")
    
    view = AutoModMainView(interaction.guild.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ========== SYSTÈME AUTOMOD - DÉTECTION ==========

def is_immune(member, channel, guild_id):
    """Vérifie si un membre/salon est immunisé"""
    config = automod_config.get(guild_id, {})
    
    if member.guild_permissions.administrator:
        return True
    
    if channel.id in config.get('immune_channels', []):
        return True
    
    for role in member.roles:
        if role.id in config.get('immune_roles', []):
            return True
    
    return False

def check_spam(user_id, guild_id):
    """Détecte le spam"""
    config = automod_config.get(guild_id, {}).get('anti_spam', {})
    if not config.get('enabled'):
        return False
    
    tracker = spam_tracker[user_id]
    now = datetime.now()
    
    if (now - tracker['last_time']).seconds < config['timeframe']:
        tracker['count'] += 1
    else:
        tracker['count'] = 1
        tracker['last_time'] = now
    
    return tracker['count'] > config['max_messages']

def check_mentions(message, guild_id):
    """Détecte trop de mentions"""
    config = automod_config.get(guild_id, {}).get('anti_mention', {})
    if not config.get('enabled'):
        return False
    
    total_mentions = len(message.mentions) + len(message.role_mentions)
    if message.mention_everyone:
        total_mentions += 10  # Pénalité pour @everyone
    
    return total_mentions > config['max_mentions']

def check_duplicate(user_id, message, guild_id):
    """Détecte les messages dupliqués"""
    config = automod_config.get(guild_id, {}).get('anti_duplicate', {})
    if not config.get('enabled'):
        return False
    
    history = message_history[user_id]
    history.append(message.content.lower())
    
    if len(history) > 10:
        history.pop(0)
    
    duplicates = history.count(message.content.lower())
    return duplicates > config['max_duplicates']

def check_flood(message, guild_id):
    """Détecte le flood de caractères"""
    config = automod_config.get(guild_id, {}).get('anti_flood', {})
    if not config.get('enabled'):
        return False
    
    content = message.content
    max_repeat = config['max_chars_repeat']
    
    for i in range(len(content) - max_repeat):
        if len(set(content[i:i+max_repeat])) == 1:
            return True
    
    return False

def check_caps(message, guild_id):
    """Détecte l'excès de majuscules"""
    config = automod_config.get(guild_id, {}).get('anti_caps', {})
    if not config.get('enabled') or len(message.content) < 10:
        return False
    
    caps_count = sum(1 for c in message.content if c.isupper())
    total_letters = sum(1 for c in message.content if c.isalpha())
    
    if total_letters == 0:
        return False
    
    caps_percent = (caps_count / total_letters) * 100
    return caps_percent > config['caps_percent']

def check_emoji_spam(message, guild_id):
    """Détecte le spam d'emojis"""
    config = automod_config.get(guild_id, {}).get('anti_emoji_spam', {})
    if not config.get('enabled'):
        return False
    
    emoji_count = len(re.findall(r'<:\w+:\d+>|[\U0001F600-\U0001F64F]', message.content))
    return emoji_count > config['max_emojis']

def check_bad_words(message, guild_id):
    """Filtre les insultes et mots interdits"""
    content = message.content.lower()
    
    # Insultes
    config_insults = automod_config.get(guild_id, {}).get('filter_insults', {})
    if config_insults.get('enabled'):
        for word in INSULTS + config_insults.get('words', []):
            if word in content:
                return 'insult'
    
    # Propos haineux
    config_slurs = automod_config.get(guild_id, {}).get('filter_slurs', {})
    if config_slurs.get('enabled'):
        for word in SLURS:
            if word in content:
                return 'slur'
    
    # NSFW
    config_nsfw = automod_config.get(guild_id, {}).get('filter_nsfw', {})
    if config_nsfw.get('enabled'):
        for word in NSFW_WORDS:
            if word in content:
                return 'nsfw'
    
    # Violence
    config_violence = automod_config.get(guild_id, {}).get('filter_violence', {})
    if config_violence.get('enabled'):
        for word in VIOLENCE_WORDS:
            if word in content:
                return 'violence'
    
    return None

def check_links(message, guild_id):
    """Vérifie les liens suspects"""
    content = message.content.lower()
    
    # Discord links
    config_discord = automod_config.get(guild_id, {}).get('anti_discord_links', {})
    if config_discord.get('enabled'):
        if 'discord.gg/' in content or 'discord.com/invite/' in content:
            return 'discord_link'
    
    # Scam
    config_scam = automod_config.get(guild_id, {}).get('anti_scam', {})
    if config_scam.get('enabled'):
        for pattern in SCAM_PATTERNS:
            if re.search(pattern, content):
                return 'scam'
    
    # Liens suspects
    config_suspicious = automod_config.get(guild_id, {}).get('anti_suspicious_links', {})
    if config_suspicious.get('enabled'):
        suspicious = ['bit.ly', 'tinyurl', 'grabify', 'iplogger']
        for susp in suspicious:
            if susp in content:
                return 'suspicious_link'
    
    return None

async def log_automod_action(guild, user, reason, action, message=None):
    """Log les actions de l'AutoMod"""
    config = automod_config.get(guild.id, {}).get('log_automod', {})
    if not config.get('enabled') or not config.get('channel_id'):
        return
    
    channel = guild.get_channel(config['channel_id'])
    if not channel:
        return
    
    embed = discord.Embed(
        title="🤖 AutoMod - Action automatique",
        color=discord.Color.orange(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Membre", value=f"{user.mention} ({user.id})", inline=True)
    embed.add_field(name="Raison", value=reason, inline=True)
    embed.add_field(name="Action", value=action, inline=True)
    
    if message:
        embed.add_field(name="Message", value=message.content[:100], inline=False)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
    
    embed.set_thumbnail(url=user.display_avatar.url)
    
    await channel.send(embed=embed)

async def apply_sanction(member, guild_id, reason):
    """Applique une sanction selon les infractions"""
    config = automod_config.get(guild_id, {}).get('auto_sanctions', {})
    if not config.get('enabled'):
        return None
    
    user_infractions[member.id]['total'] += 1
    infractions = user_infractions[member.id]['total']
    
    action = None
    
    if infractions >= config['ban_threshold']:
        try:
            await member.ban(reason=f"AutoMod: {reason} ({infractions} infractions)")
            action = "🔨 BAN"
        except:
            pass
    
    elif infractions >= config['kick_threshold']:
        try:
            await member.kick(reason=f"AutoMod: {reason} ({infractions} infractions)")
            action = "👢 KICK"
        except:
            pass
    
    elif infractions >= config['mute_threshold']:
        try:
            await member.timeout(timedelta(hours=1), reason=f"AutoMod: {reason}")
            action = "🔇 TIMEOUT 1H"
        except:
            pass
    
    elif infractions >= config['warn_threshold']:
        if member.id not in warnings:
            warnings[member.id] = []
        
        warnings[member.id].append({
            'raison': f"AutoMod: {reason}",
            'moderateur': 'AutoMod',
            'date': datetime.now().strftime("%d/%m/%Y %H:%M")
        })
        action = "⚠️ WARN"
    
    return action

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    guild_id = message.guild.id
    
    # Vérifier si AutoMod est activé
    if guild_id not in automod_config or not automod_config[guild_id]['enabled']:
        await bot.process_commands(message)
        return
    
    # Vérifier immunité
    if is_immune(message.author, message.channel, guild_id):
        await bot.process_commands(message)
        return
    
    should_delete = False
    reason = None
    
    # SPAM
    if check_spam(message.author.id, guild_id):
        should_delete = True
        reason = "Spam de messages"
    
    # MENTIONS
    elif check_mentions(message, guild_id):
        should_delete = True
        reason = "Trop de mentions"
    
    # DUPLICATE
    elif check_duplicate(message.author.id, message, guild_id):
        should_delete = True
        reason = "Messages dupliqués"
    
    # FLOOD
    elif check_flood(message, guild_id):
        should_delete = True
        reason = "Flood de caractères"
    
    # CAPS
    elif check_caps(message, guild_id):
        should_delete = True
        reason = "Trop de majuscules"
    
    # EMOJI SPAM
    elif check_emoji_spam(message, guild_id):
        should_delete = True
        reason = "Spam d'emojis"
    
    # MOTS INTERDITS
    bad_word_type = check_bad_words(message, guild_id)
    if bad_word_type:
        should_delete = True
        reasons_map = {
            'insult': 'Insulte',
            'slur': 'Propos haineux',
            'nsfw': 'Contenu NSFW',
            'violence': 'Propos violent'
        }
        reason = reasons_map.get(bad_word_type, 'Langage inapproprié')
        
        # Ban immédiat pour propos haineux
        if bad_word_type == 'slur':
            try:
                await message.author.ban(reason="AutoMod: Propos haineux")
                await log_automod_action(message.guild, message.author, "Propos haineux", "BAN IMMÉDIAT", message)
                await message.delete()
                return
            except:
                pass
    
    # LIENS
    link_type = check_links(message, guild_id)
    if link_type:
        should_delete = True
        reasons_map = {
            'discord_link': 'Lien Discord non autorisé',
            'scam': 'Tentative de scam',
            'suspicious_link': 'Lien suspect'
        }
        reason = reasons_map.get(link_type, 'Lien interdit')
        
        # Ban pour scam
        if link_type == 'scam':
            try:
                await message.author.ban(reason="AutoMod: Tentative de scam")
                await log_automod_action(message.guild, message.author, "Tentative de scam", "BAN IMMÉDIAT", message)
                await message.delete()
                return
            except:
                pass
    
    # Si violation détectée
    if should_delete and reason:
        try:
            await message.delete()
            
            # Appliquer sanction
            action = await apply_sanction(message.author, guild_id, reason)
            
            # Log
            await log_automod_action(message.guild, message.author, reason, action or "Message supprimé", message)
            
            # Notifier l'utilisateur
            try:
                embed = discord.Embed(
                    title="⚠️ Message supprimé par AutoMod",
                    description=f"**Raison:** {reason}",
                    color=discord.Color.red()
                )
                if action:
                    embed.add_field(name="Action", value=action, inline=False)
                
                await message.author.send(embed=embed)
            except:
                pass
        
        except:
            pass
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    guild_id = member.guild.id
    
    # Vérifier âge du compte
    if guild_id in automod_config:
        config_age = automod_config[guild_id].get('account_age', {})
        if config_age.get('enabled'):
            account_age = (datetime.now() - member.created_at.replace(tzinfo=None)).days
            
            if account_age < config_age['min_days']:
                try:
                    await member.kick(reason=f"AutoMod: Compte trop récent ({account_age} jours)")
                    await log_automod_action(member.guild, member, f"Compte trop récent ({account_age} jours)", "KICK AUTO")
                    return
                except:
                    pass
    
    # Message DM de bienvenue
    if guild_id in automod_config:
        config_dm = automod_config[guild_id].get('welcome_dm', {})
        if config_dm.get('enabled'):
            try:
                embed = discord.Embed(
                    title=f"Bienvenue sur {member.guild.name} !",
                    description=config_dm.get('message', 'Bienvenue !'),
                    color=discord.Color.green()
                )
                await member.send(embed=embed)
            except:
                pass
    
    # Rôle automatique
    if guild_id in automod_config:
        config_role = automod_config[guild_id].get('auto_role', {})
        if config_role.get('enabled') and config_role.get('role_id'):
            role = member.guild.get_role(config_role['role_id'])
            if role:
                try:
                    await member.add_roles(role)
                except:
                    pass
    
    # Logs
    if guild_id in automod_config:
        config_logs = automod_config[guild_id].get('log_joins', {})
        if config_logs.get('enabled') and config_logs.get('channel_id'):
            channel = member.guild.get_channel(config_logs['channel_id'])
            if channel:
                embed = discord.Embed(
                    title="👋 Nouveau membre",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Membre", value=f"{member.mention} ({member.id})", inline=False)
                
                account_age = (datetime.now() - member.created_at.replace(tzinfo=None)).days
                embed.add_field(name="Âge du compte", value=f"{account_age} jours", inline=True)
                embed.add_field(name="Total membres", value=member.guild.member_count, inline=True)
                
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)
    
    # Bienvenue dans le salon configuré
    config = config_serveur.get(guild_id, {})
    channel_id = config.get('salon_bienvenue')
    
    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title=f"Bienvenue {member.name} !",
                description=f"Bienvenue sur **{member.guild.name}** !\nTu es le membre n°{member.guild.member_count}",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    
    guild_id = message.guild.id
    
    if guild_id in automod_config:
        config = automod_config[guild_id].get('log_deleted', {})
        if config.get('enabled') and config.get('channel_id'):
            channel = message.guild.get_channel(config['channel_id'])
            if channel:
                embed = discord.Embed(
                    title="🗑️ Message supprimé",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(name="Auteur", value=f"{message.author.mention}", inline=True)
                embed.add_field(name="Salon", value=message.channel.mention, inline=True)
                embed.add_field(name="Contenu", value=message.content[:1000] or "*[Aucun contenu texte]*", inline=False)
                
                embed.set_footer(text=f"ID: {message.id}")
                
                await channel.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or not before.guild or before.content == after.content:
        return
    
    guild_id = before.guild.id
    
    if guild_id in automod_config:
        config = automod_config[guild_id].get('log_edited', {})
        if config.get('enabled') and config.get('channel_id'):
            channel = before.guild.get_channel(config['channel_id'])
            if channel:
                embed = discord.Embed(
                    title="✏️ Message édité",
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(name="Auteur", value=f"{before.author.mention}", inline=True)
                embed.add_field(name="Salon", value=before.channel.mention, inline=True)
                embed.add_field(name="Avant", value=before.content[:500] or "*[Vide]*", inline=False)
                embed.add_field(name="Après", value=after.content[:500] or "*[Vide]*", inline=False)
                
                embed.set_footer(text=f"ID: {before.id}")
                
                await channel.send(embed=embed)

# ========== COMMANDES CONFIGURATION ==========

@bot.tree.command(name="setlogchannel", description="[ADMIN] Définir le salon de logs AutoMod")
@app_commands.describe(type_log="Type de log", salon="Le salon")
@app_commands.choices(type_log=[
    app_commands.Choice(name="Messages supprimés", value="deleted"),
    app_commands.Choice(name="Messages édités", value="edited"),
    app_commands.Choice(name="Arrivées/Départs", value="joins"),
    app_commands.Choice(name="Actions AutoMod", value="automod")
])
async def set_log_channel(interaction: discord.Interaction, type_log: str, salon: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_AUTOMOD.copy()
    
    log_types = {
        'deleted': 'log_deleted',
        'edited': 'log_edited',
        'joins': 'log_joins',
        'automod': 'log_automod'
    }
    
    config_key = log_types[type_log]
    automod_config[guild_id][config_key]['channel_id'] = salon.id
    automod_config[guild_id][config_key]['enabled'] = True
    
    await interaction.response.send_message(f"✅ Salon de logs **{type_log}** défini sur {salon.mention}", ephemeral=True)

@bot.tree.command(name="statsautomod", description="Voir les statistiques AutoMod")
async def stats_automod(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    if guild_id not in automod_config:
        await interaction.response.send_message("❌ AutoMod non configuré !", ephemeral=True)
        return
    
    # Compter les modules actifs
    config = automod_config[guild_id]
    active = sum(1 for key, val in config.items() if isinstance(val, dict) and val.get('enabled', False))
    
    embed = discord.Embed(
        title="📊 Statistiques AutoMod",
        color=discord.Color.blue()
    )
    
    status = "🟢 Actif" if config['enabled'] else "🔴 Inactif"
    embed.add_field(name="Statut global", value=status, inline=True)
    embed.add_field(name="Modules actifs", value=f"{active}", inline=True)
    
    # Top utilisateurs avec infractions
    top_users = sorted(user_infractions.items(), key=lambda x: x[1]['total'], reverse=True)[:5]
    
    if top_users:
        top_text = ""
        for user_id, data in top_users:
            member = interaction.guild.get_member(user_id)
            if member:
                top_text += f"{member.mention}: {data['total']} infractions\n"
        
        if top_text:
            embed.add_field(name="Top infractions", value=top_text, inline=False)
    
    await interaction.response.send_message(embed=embed)

# ========== COMMANDES MODÉRATION (inchangées) ==========

async def log_action(guild, action_type, moderateur, cible, raison):
    config = config_serveur.get(guild.id, {})
    logs_channel_id = config.get('salon_logs')
    
    if not logs_channel_id:
        return
    
    logs_channel = guild.get_channel(logs_channel_id)
    if not logs_channel:
        return
    
    colors = {
        'warn': discord.Color.orange(),
        'kick': discord.Color.red(),
        'ban': discord.Color.dark_red(),
        'timeout': discord.Color.yellow(),
        'unmute': discord.Color.green(),
        'unwarn': discord.Color.blue()
    }
    
    embed = discord.Embed(
        title=f"🔨 Action: {action_type.upper()}",
        color=colors.get(action_type, discord.Color.gray()),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Membre", value=f"{cible.mention} ({cible.id})", inline=True)
    embed.add_field(name="Modérateur", value=f"{moderateur.mention}", inline=True)
    embed.add_field(name="Raison", value=raison, inline=False)
    embed.set_thumbnail(url=cible.display_avatar.url)
    
    await logs_channel.send(embed=embed)

@bot.tree.command(name="warn", description="Avertir un membre")
@app_commands.describe(membre="Le membre à avertir", raison="La raison")
async def warn(interaction: discord.Interaction, membre: discord.Member, raison: str):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if membre.id not in warnings:
        warnings[membre.id] = []
    
    warnings[membre.id].append({
        'raison': raison,
        'moderateur': interaction.user.name,
        'date': datetime.now().strftime("%d/%m/%Y %H:%M")
    })
    
    warn_count = len(warnings[membre.id])
    
    embed = discord.Embed(title="⚠️ Avertissement", color=discord.Color.orange())
    embed.add_field(name="Membre", value=membre.mention, inline=True)
    embed.add_field(name="Raison", value=raison, inline=False)
    embed.add_field(name="Total warns", value=f"{warn_count}", inline=True)
    
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, 'warn', interaction.user, membre, raison)

@bot.tree.command(name="warns", description="Voir les warns d'un membre")
@app_commands.describe(membre="Le membre")
async def see_warns(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    
    if target.id not in warnings or len(warnings[target.id]) == 0:
        await interaction.response.send_message(f"✅ Aucun warn", ephemeral=True)
        return
    
    embed = discord.Embed(title=f"⚠️ Warns de {target.name}", color=discord.Color.orange())
    
    for i, warn in enumerate(warnings[target.id], 1):
        embed.add_field(
            name=f"Warn #{i} - {warn['date']}",
            value=f"**Raison:** {warn['raison']}\n**Par:** {warn['moderateur']}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un membre")
@app_commands.describe(membre="Le membre", raison="La raison")
async def kick(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    try:
        await membre.kick(reason=raison)
        await interaction.response.send_message(f"✅ {membre.mention} expulsé")
        await log_action(interaction.guild, 'kick', interaction.user, membre, raison)
    except:
        await interaction.response.send_message("❌ Erreur", ephemeral=True)

@bot.tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(membre="Le membre", raison="La raison")
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    try:
        await membre.ban(reason=raison)
        await interaction.response.send_message(f"🔨 {membre.mention} banni")
        await log_action(interaction.guild, 'ban', interaction.user, membre, raison)
    except:
        await interaction.response.send_message("❌ Erreur", ephemeral=True)

@bot.tree.command(name="timeout", description="Timeout un membre")
@app_commands.describe(membre="Le membre", duree="Durée en minutes", raison="La raison")
async def timeout(interaction: discord.Interaction, membre: discord.Member, duree: int, raison: str = "Aucune raison"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    try:
        await membre.timeout(timedelta(minutes=duree), reason=raison)
        await interaction.response.send_message(f"⏰ {membre.mention} timeout {duree}min")
        await log_action(interaction.guild, 'timeout', interaction.user, membre, raison)
    except:
        await interaction.response.send_message("❌ Erreur", ephemeral=True)

@bot.tree.command(name="clear", description="Supprimer des messages")
@app_commands.describe(nombre="Nombre de messages")
async def clear(interaction: discord.Interaction, nombre: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(f"✅ {len(deleted)} messages supprimés", ephemeral=True)

# ========== ROBLOX (inchangé) ==========

@bot.tree.command(name="lier_roblox", description="Lier ton compte Roblox")
@app_commands.describe(nom_utilisateur="Ton nom Roblox")
async def lier_roblox(interaction: discord.Interaction, nom_utilisateur: str):
    await interaction.response.defer()
    
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/search?keyword={nom_utilisateur}&limit=1")
        data = response.json()
        
        if not data.get('data'):
            await interaction.followup.send(f"❌ Utilisateur introuvable")
            return
        
        roblox_user = data['data'][0]
        roblox_id = roblox_user['id']
        roblox_name = roblox_user['name']
        
        roblox_links[interaction.user.id] = {
            'roblox_id': roblox_id,
            'roblox_name': roblox_name
        }
        
        embed = discord.Embed(title="✅ Compte lié !", description=f"Lié à **{roblox_name}**", color=discord.Color.green())
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=150&height=150&format=png")
        
        await interaction.followup.send(embed=embed)
    except:
        await interaction.followup.send("❌ Erreur")

@bot.tree.command(name="userinfo", description="Infos sur un membre")
@app_commands.describe(membre="Le membre")
async def userinfo(interaction: discord.Interaction, membre: discord.Member = None):
    user = membre or interaction.user
    
    embed = discord.Embed(title=f"Infos sur {user.name}", color=user.color)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Créé le", value=user.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Rejoint le", value=user.joined_at.strftime("%d/%m/%Y"), inline=True)
    
    if user.id in warnings and len(warnings[user.id]) > 0:
        embed.add_field(name="⚠️ Warns", value=f"{len(warnings[user.id])}", inline=True)
    
    if user.id in user_infractions:
        embed.add_field(name="Infractions AutoMod", value=f"{user_infractions[user.id]['total']}", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Infos sur le serveur")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    
    embed = discord.Embed(title=f"Infos - {guild.name}", color=discord.Color.purple())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="Propriétaire", value=guild.owner.mention, inline=True)
    embed.add_field(name="Membres", value=guild.member_count, inline=True)
    embed.add_field(name="Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    
    await interaction.response.send_message(embed=embed)

# ========== ÉVÉNEMENTS ==========

@bot.event
async def on_ready():
    print(f'{bot.user} connecté !')
    try:
        synced = await bot.tree.sync()
        print(f'Synchronisé {len(synced)} commandes')
    except Exception as e:
        print(f'Erreur: {e}')

# Serveur web pour Render
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot Discord actif !"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# Lance le bot
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("❌ Token Discord non trouvé !")
else:
    keep_alive()
    bot.run(TOKEN)
