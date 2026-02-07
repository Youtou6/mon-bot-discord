"""
🌙 LUNERA SECURITY ULTRA 🛡️
Système de sécurité et modération automatique ultra-complet
Protection maximale contre raids, spam, toxicité et menaces
Version: 3.0 ULTIMATE
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
import hashlib
import aiohttp
from typing import Optional, List, Dict
import json

# ========== CONFIGURATION GLOBALE ==========
lunera_config = {}
user_warnings = defaultdict(list)
user_infractions = defaultdict(lambda: {'warns': 0, 'mutes': 0, 'kicks': 0, 'bans': 0})
message_history = defaultdict(lambda: deque(maxlen=20))
spam_tracker = defaultdict(lambda: deque(maxlen=15))
raid_tracker = defaultdict(list)
suspicious_users = defaultdict(set)
user_trust_scores = defaultdict(lambda: 100)
toxicity_scores = defaultdict(lambda: 0)

# Nouveaux trackers
duplicate_messages = defaultdict(lambda: deque(maxlen=10))
attachment_history = defaultdict(lambda: deque(maxlen=10))
voice_raid_tracker = defaultdict(list)
reaction_spam_tracker = defaultdict(lambda: deque(maxlen=20))
mention_tracker = defaultdict(lambda: deque(maxlen=10))
edit_tracker = defaultdict(list)
ghost_ping_tracker = defaultdict(list)
user_behavior_tracker = defaultdict(lambda: {
    'sudden_spam': False,
    'message_burst': deque(maxlen=30),
    'link_spam': deque(maxlen=10),
    'image_spam': deque(maxlen=10),
    'caps_abuse': 0,
    'last_slowmode': None
})

# Protection anti-nuke
server_backups = defaultdict(dict)
channel_delete_tracker = defaultdict(lambda: deque(maxlen=5))
role_delete_tracker = defaultdict(lambda: deque(maxlen=5))
webhook_spam_tracker = defaultdict(lambda: deque(maxlen=10))

# ========== CONFIGURATION ULTRA ==========
DEFAULT_CONFIG = {
    'enabled': True,
    'log_channel': None,
    'alert_channel': None,
    'quarantine_role': None,
    'verified_role': None,
    'staff_ping_role': None,
    
    # Niveau de protection
    'protection_level': 'maximum',  # low, medium, high, maximum, ultra
    
    # ===== ANTI-SPAM ULTRA =====
    'spam_protection': True,
    'spam_messages': 5,
    'spam_interval': 3,
    'spam_action': 'mute',
    'spam_mute_duration': 600,
    'spam_duplicate_check': True,
    'spam_similarity_threshold': 80,
    'spam_burst_detection': True,  # Détecte les rafales
    'spam_burst_threshold': 10,  # messages en 10s = burst
    
    # Anti-spam images/médias
    'image_spam_protection': True,
    'max_images_per_message': 3,
    'max_images_per_minute': 5,
    'max_file_size_mb': 8,
    'image_spam_action': 'mute',
    
    # Anti-spam emojis/réactions
    'emoji_spam_protection': True,
    'max_emojis_per_message': 10,
    'reaction_spam_protection': True,
    'max_reactions_per_minute': 15,
    'reaction_spam_action': 'warn',
    
    # Anti-répétition
    'repetition_protection': True,
    'max_repeated_chars': 8,
    'max_repeated_words': 4,
    'repetition_action': 'delete',
    
    # ===== ANTI-RAID ULTRA =====
    'raid_protection': True,
    'raid_joins': 6,
    'raid_interval': 8,
    'raid_account_age_minutes': 30,  # Comptes < 30min suspects
    'raid_account_age_hours': 24,  # Comptes < 24h très suspects
    'raid_auto_lockdown': True,
    'raid_lockdown_threshold': 8,
    'raid_kick_new_accounts': True,
    'raid_voice_protection': True,
    'raid_max_voice_joins': 4,
    
    # Mode lockdown
    'lockdown_active': False,
    'lockdown_auto_unlock_minutes': 30,
    
    # ===== FILTRE CONTENU ULTRA =====
    'word_filter': True,
    'banned_words': [
        # Insultes françaises (votre liste actuelle)
        'malpt', 'baiser', 'bander', 'bigornette', 'bite', 'bitte', 'bloblos',
        'bordel', 'bourré', 'bourrée', 'brackmard', 'branlage',
        'branler', 'branlette', 'branleur', 'branleuse',
        'caca', 'chatte', 'chiasse', 'chier', 'chiottes',
        'clito', 'clitoris',
        'con', 'connard', 'connasse', 'conne',
        'couilles', 'cramouille', 'cul',
        'déconne', 'déconner',
        'emmerdant', 'emmerder', 'emmerdeur', 'emmerdeuse',
        'enculeur', 'enculeurs', 'enculé', 'enculée',
        'enfoiré', 'enfoirée',
        'folle', 'foutre',
        'gerbe', 'gerber',
        'gouine', 'grogniasse', 'gueule',
        'jouir',
        'merde', 'merdeuse', 'merdeux',
        'meuf',
        'negro', 'nègre',
        'palucher',
        'pipi', 'pisser',
        'pouffiasse',
        'putain', 'pute',
        'pédale', 'pédé',
        'péter',
        'ramoner',
        'salaud', 'salope',
        'suce',
        'tanche', 'tapette', 'teuch', 'tringler', 'trique', 'troncher', 'turlute',
        'zigounette', 'zizi',
        'étron',
        # Mots anglais courants
        'fuck', 'shit', 'bitch', 'ass', 'damn', 'nigger', 'nigga',
        'retard', 'faggot', 'cunt', 'pussy', 'dick', 'cock',
        # Toxicité
        'kys', 'kill yourself', 'suicide', 'die',
    ],
    'toxicity_detection': True,  # Détection par IA (score)
    'toxicity_threshold': 70,  # 0-100
    'word_filter_action': 'warn',
    'word_filter_bypass_detection': True,  # Leet speak, accents, etc.
    
    # ===== PROTECTION LIENS/PUB =====
    'link_filter': True,
    'allow_links': False,
    'block_discord_invites': True,
    'block_url_shorteners': True,
    'block_ip_links': True,
    'block_suspicious_tlds': True,
    'link_action': 'delete',
    'whitelist_domains': ['youtube.com', 'youtu.be', 'twitter.com', 'x.com', 'twitch.tv', 'spotify.com'],
    
    # Anti-phishing/scam avancé
    'phishing_protection': True,
    'phishing_action': 'ban',
    'scam_link_detection': True,
    'token_grabber_detection': True,
    'known_scam_domains': [
        'discord-nitro', 'discordgift', 'steamcommunity-gift',
        'free-nitro', 'discord-app', 'steamnitro', 'discord-nitro-free',
        'dlscord', 'discоrd', 'steam-wallet', 'nitro-claim'
    ],
    'suspicious_tld': ['.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.top', '.loan'],
    
    # ===== ANTI-MENTIONS =====
    'mention_protection': True,
    'max_mentions': 5,
    'max_role_mentions': 2,
    'mention_action': 'warn',
    'everyone_mention_allowed': False,
    'ghost_ping_protection': True,  # Détecte ping puis delete
    'mass_mention_threshold': 10,  # = raid mention
    'mass_mention_action': 'mute',
    
    # ===== ANTI-CAPS/FLOOD =====
    'caps_filter': True,
    'max_caps_percentage': 60,
    'min_caps_length': 10,
    'caps_action': 'delete',
    
    'flood_protection': True,
    'max_repeated_chars': 8,
    'flood_action': 'delete',
    
    # Messages vides/invisibles
    'empty_message_protection': True,
    'invisible_char_detection': True,
    
    # ===== PROTECTION FICHIERS DANGEREUX =====
    'dangerous_file_protection': True,
    'blocked_extensions': [
        '.exe', '.bat', '.cmd', '.scr', '.jar', '.vbs', '.js',
        '.msi', '.com', '.pif', '.application', '.gadget',
        '.msp', '.hta', '.cpl', '.inf', '.ps1', '.sh'
    ],
    'dangerous_file_action': 'ban',  # Fichiers dangereux = ban direct
    
    # ===== PROTECTION COMPTE HACKÉ =====
    'hacked_account_detection': True,
    'sudden_spam_threshold': 8,  # messages en 5s = suspect
    'sudden_spam_action': 'mute',
    'behavior_change_detection': True,
    'auto_slowmode_user': True,  # Slowmode individuel
    'slowmode_duration': 10,  # secondes entre messages
    
    # ===== SYSTÈME SANCTIONS =====
    'progressive_sanctions': True,
    'warn_threshold': 3,
    'mute_duration': 1800,
    'warn_reset_days': 7,
    'escalation_enabled': True,  # warn → mute → kick → ban
    
    # Score de toxicité
    'toxicity_scoring': True,
    'max_toxicity_score': 100,
    'toxicity_auto_mute': 80,
    'toxicity_auto_ban': 150,
    
    # ===== ANTI-NUKE =====
    'anti_nuke_protection': True,
    'max_channel_deletes': 3,  # 3 salons supprimés = suspect
    'max_role_deletes': 3,
    'max_kicks_per_minute': 5,
    'max_bans_per_minute': 3,
    'nuke_detection_action': 'lockdown',
    'backup_roles_on_join': True,
    
    # ===== ANTI-WEBHOOK SPAM =====
    'webhook_protection': True,
    'max_webhook_messages': 10,
    'webhook_spam_interval': 5,
    'webhook_spam_action': 'delete',
    
    # ===== PROTECTION AVANCÉE =====
    'anti_selfbot': True,
    'anti_hoisting': True,
    'hoist_characters': ['!', '?', '.', '|', '*', '#', '~'],
    
    'captcha_verification': False,  # Optionnel (nécessite implémentation)
    'auto_quarantine_threshold': 25,
    'trust_score_enabled': True,
    
    # ===== EXCEPTIONS =====
    'immune_roles': [],
    'immune_users': [],
    'ignored_channels': [],
    'whitelist_users': [],  # Jamais sanctionnés
    
    # ===== NOTIFICATIONS =====
    'dm_warnings': True,
    'dm_sanctions': True,
    'detailed_logs': True,
    'log_edits': True,
    'log_deletes': True,
    'log_joins_leaves': True,
}

# ========== PATTERNS DÉTECTION ==========

# URLs et invites
DISCORD_INVITE = re.compile(
    r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/|discord\.me/|dsc\.gg/)[a-zA-Z0-9\-]+',
    re.IGNORECASE
)

URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
    re.IGNORECASE
)

IP_PATTERN = re.compile(
    r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b|\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'
)

# URL shorteners
URL_SHORTENERS = [
    'bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ow.ly', 'buff.ly',
    'adf.ly', 'bit.do', 'short.io', 'rebrand.ly', 'cutt.ly', 'is.gd',
    'shorturl.at', 'tiny.cc', 's.id', 'cli.gs'
]

# Token Discord
TOKEN_PATTERN = re.compile(
    r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}|mfa\.[A-Za-z0-9_-]{84}',
    re.IGNORECASE
)

# Caractères invisibles
INVISIBLE_CHARS = [
    '\u200b', '\u200c', '\u200d', '\u2060', '\ufeff',
    '\u180e', '\u2061', '\u2062', '\u2063'
]

# Zalgo detection
def is_zalgo(text):
    """Détecte le texte zalgo (corruption Unicode)"""
    zalgo_chars = sum(1 for c in text if '\u0300' <= c <= '\u036f')
    return zalgo_chars > len(text) * 0.3

# Normalisation avancée (bypass leet speak, accents, etc.)
def normalize_text(text):
    """Normalise le texte pour détecter contournements"""
    # Supprimer espaces, underscores, tirets, points
    text = re.sub(r'[\s_\-\.]+', '', text)
    
    # Remplacer caractères similaires (leet speak)
    replacements = {
        '0': 'o', 'O': 'o',
        '1': 'i', 'l': 'i', 'I': 'i', '|': 'i',
        '3': 'e', 'E': 'e', '€': 'e',
        '4': 'a', 'A': 'a', '@': 'a',
        '5': 's', 'S': 's', '$': 's',
        '7': 't', 'T': 't',
        '8': 'b', 'B': 'b',
        '9': 'g', 'G': 'g',
        'ç': 'c', 'Ç': 'c',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'à': 'a', 'â': 'a', 'ä': 'a',
        'î': 'i', 'ï': 'i',
        'ô': 'o', 'ö': 'o',
        'û': 'u', 'ù': 'u', 'ü': 'u',
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Supprimer répétitions (aaa -> a)
    text = re.compile(r'(.)\1+').sub(r'\1', text)
    
    return text.lower()

# Similarité de messages
def message_similarity(msg1, msg2):
    """Calcule la similarité entre deux messages (0-100%)"""
    if msg1 == msg2:
        return 100
    
    len1, len2 = len(msg1), len(msg2)
    if abs(len1 - len2) > max(len1, len2) * 0.5:
        return 0
    
    common = sum(1 for a, b in zip(msg1, msg2) if a == b)
    return int((common / max(len1, len2)) * 100)

# Hash de message
def message_hash(content):
    """Crée un hash du message"""
    normalized = normalize_text(content)
    return hashlib.md5(normalized.encode()).hexdigest()

# ========== UTILITAIRES ==========

def get_config(guild_id):
    """Récupère la config d'un serveur"""
    if guild_id not in lunera_config:
        lunera_config[guild_id] = DEFAULT_CONFIG.copy()
    return lunera_config[guild_id]

def is_immune(member, config):
    """Vérifie si un membre est immunisé"""
    if member.guild_permissions.administrator:
        return True
    
    if member.id in config.get('immune_users', []) or member.id in config.get('whitelist_users', []):
        return True
    
    for role in member.roles:
        if role.id in config.get('immune_roles', []):
            return True
    
    verified_role_id = config.get('verified_role')
    if verified_role_id:
        if any(r.id == verified_role_id for r in member.roles):
            return True
    
    return False

def update_trust_score(user_id, guild_id, delta):
    """Met à jour le score de confiance"""
    key = f"{guild_id}_{user_id}"
    user_trust_scores[key] = max(0, min(100, user_trust_scores[key] + delta))
    return user_trust_scores[key]

def get_trust_score(user_id, guild_id):
    """Récupère le score de confiance"""
    key = f"{guild_id}_{user_id}"
    return user_trust_scores.get(key, 100)

def update_toxicity_score(user_id, delta):
    """Met à jour le score de toxicité"""
    toxicity_scores[user_id] = max(0, toxicity_scores[user_id] + delta)
    return toxicity_scores[user_id]

def get_toxicity_score(user_id):
    """Récupère le score de toxicité"""
    return toxicity_scores.get(user_id, 0)

async def log_security_event(guild, event_type, user, reason, severity='medium', extra_data=None):
    """Log un événement de sécurité"""
    config = get_config(guild.id)
    log_channel_id = config.get('log_channel')
    
    if not log_channel_id:
        return
    
    log_channel = guild.get_channel(log_channel_id)
    if not log_channel:
        return
    
    colors = {
        'low': 0x57F287,
        'medium': 0xFEE75C,
        'high': 0xED4245,
        'critical': 0x5865F2
    }
    
    emojis = {
        'spam': '🚫', 'raid': '🛡️', 'phishing': '🎣', 'scam': '⚠️',
        'word': '🔤', 'link': '🔗', 'mention': '👥', 'token': '🔑',
        'suspicious': '🔍', 'quarantine': '🔒', 'ban': '🔨',
        'mute': '🔇', 'warn': '⚠️', 'image': '🖼️', 'file': '📁',
        'nuke': '💥', 'lockdown': '🔐', 'caps': '📢', 'flood': '🌊',
        'toxic': '☠️', 'hack': '🚨', 'ghost': '👻', 'emoji': '😀',
        'reaction': '👍', 'webhook': '🪝', 'edit': '✏️', 'delete': '🗑️'
    }
    
    embed = discord.Embed(
        title=f"{emojis.get(event_type, '🛡️')} Lunera Security Ultra - {event_type.upper()}",
        color=colors.get(severity, 0x5865F2),
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="👤 Utilisateur",
        value=f"{user.mention}\n`{user.name}` (`{user.id}`)",
        inline=True
    )
    
    embed.add_field(
        name="📝 Raison",
        value=reason[:1024],
        inline=True
    )
    
    embed.add_field(
        name="🎯 Sévérité",
        value=severity.upper(),
        inline=True
    )
    
    # Scores
    trust_score = get_trust_score(user.id, guild.id)
    trust_emoji = "🟢" if trust_score >= 70 else "🟡" if trust_score >= 40 else "🔴"
    
    toxicity = get_toxicity_score(user.id)
    toxicity_emoji = "🟢" if toxicity < 30 else "🟡" if toxicity < 60 else "🔴"
    
    embed.add_field(
        name="📊 Scores",
        value=f"{trust_emoji} Confiance: {trust_score}/100\n{toxicity_emoji} Toxicité: {toxicity}/100",
        inline=True
    )
    
    # Infractions
    infractions = user_infractions[user.id]
    embed.add_field(
        name="📋 Historique",
        value=f"Warns: {infractions['warns']} | Mutes: {infractions['mutes']}\nKicks: {infractions['kicks']} | Bans: {infractions['bans']}",
        inline=True
    )
    
    if extra_data and config.get('detailed_logs', True):
        for key, value in list(extra_data.items())[:5]:  # Max 5 champs
            embed.add_field(name=key, value=str(value)[:1024], inline=True)
    
    embed.set_footer(text="🌙 Lunera Security Ultra v3.0", icon_url=guild.icon.url if guild.icon else None)
    embed.set_thumbnail(url=user.display_avatar.url)
    
    try:
        await log_channel.send(embed=embed)
    except:
        pass

async def apply_sanction(message, reason, action='warn', duration=None, severity='medium'):
    """Applique une sanction"""
    config = get_config(message.guild.id)
    user = message.author
    
    # Supprimer le message si possible
    if action != 'delete':
        try:
            await message.delete()
        except:
            pass
    
    # DELETE seulement
    if action == 'delete':
        try:
            await message.delete()
            
            if config.get('dm_warnings', True):
                try:
                    embed = discord.Embed(
                        title="🗑️ Message supprimé - Lunera Security Ultra",
                        description=f"**Serveur:** {message.guild.name}\n**Salon:** {message.channel.mention}",
                        color=0xFEE75C,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.add_field(name="💬 Votre message", value=f"```{message.content[:500]}```", inline=False)
                    embed.set_footer(text="🌙 Lunera Security Ultra")
                    await user.send(embed=embed)
                except:
                    pass
            
            await log_security_event(message.guild, 'delete', user, reason, severity)
        except:
            pass
        return
    
    # WARN
    if action == 'warn':
        user_warnings[user.id].append({
            'guild_id': message.guild.id,
            'reason': reason,
            'timestamp': datetime.now()
        })
        
        user_infractions[user.id]['warns'] += 1
        update_trust_score(user.id, message.guild.id, -5)
        update_toxicity_score(user.id, 5)
        
        reset_days = config.get('warn_reset_days', 7)
        cutoff = datetime.now() - timedelta(days=reset_days)
        user_warnings[user.id] = [w for w in user_warnings[user.id] if w['timestamp'] > cutoff]
        
        warn_count = len([w for w in user_warnings[user.id] if w['guild_id'] == message.guild.id])
        threshold = config.get('warn_threshold', 3)
        
        if config.get('dm_warnings', True):
            try:
                embed = discord.Embed(
                    title="⚠️ Avertissement - Lunera Security Ultra",
                    description=f"Vous avez reçu un avertissement sur **{message.guild.name}**",
                    color=0xFEE75C,
                    timestamp=datetime.now()
                )
                embed.add_field(name="📝 Raison", value=reason, inline=False)
                embed.add_field(name="💬 Message", value=f"```{message.content[:500]}```", inline=False)
                embed.add_field(name="📊 Warns", value=f"**{warn_count}/{threshold}**", inline=True)
                
                trust = get_trust_score(user.id, message.guild.id)
                toxicity = get_toxicity_score(user.id)
                embed.add_field(name="📈 Scores", value=f"Confiance: {trust}/100\nToxicité: {toxicity}/100", inline=True)
                
                if warn_count >= threshold - 1:
                    embed.add_field(
                        name="⚠️ ATTENTION",
                        value=f"Prochain warn = sanction automatique !",
                        inline=False
                    )
                
                embed.set_footer(text="🌙 Lunera Security Ultra")
                await user.send(embed=embed)
            except:
                pass
        
        try:
            await message.channel.send(
                embed=discord.Embed(
                    description=f"⚠️ **{user.mention}** a reçu un avertissement\n**Raison:** {reason}\n**Warns:** {warn_count}/{threshold}",
                    color=0xFEE75C
                ),
                delete_after=8
            )
        except:
            pass
        
        await log_security_event(
            message.guild, 'warn', user, reason, severity,
            {'Warns': f"{warn_count}/{threshold}", 'Message': message.content[:100]}
        )
        
        # Escalade automatique
        if warn_count >= threshold and config.get('progressive_sanctions', True):
            action = 'mute'
            duration = config.get('mute_duration', 1800)
    
    # MUTE
    if action == 'mute':
        try:
            mute_duration = duration or config.get('mute_duration', 1800)
            timeout_until = datetime.now() + timedelta(seconds=mute_duration)
            
            await user.timeout(timeout_until, reason=f"Lunera Security Ultra: {reason}")
            
            user_infractions[user.id]['mutes'] += 1
            update_trust_score(user.id, message.guild.id, -15)
            update_toxicity_score(user.id, 10)
            
            mins = mute_duration // 60
            
            if config.get('dm_sanctions', True):
                try:
                    embed = discord.Embed(
                        title="🔇 Timeout - Lunera Security Ultra",
                        description=f"Vous avez été mis en timeout sur **{message.guild.name}**",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.add_field(name="⏱️ Durée", value=f"**{mins} minutes**", inline=True)
                    embed.add_field(name="🕐 Fin", value=f"<t:{int(timeout_until.timestamp())}:R>", inline=True)
                    
                    trust = get_trust_score(user.id, message.guild.id)
                    toxicity = get_toxicity_score(user.id)
                    embed.add_field(name="📈 Scores", value=f"Confiance: {trust}/100\nToxicité: {toxicity}/100", inline=True)
                    
                    embed.set_footer(text="🌙 Lunera Security Ultra")
                    await user.send(embed=embed)
                except:
                    pass
            
            try:
                await message.channel.send(
                    embed=discord.Embed(
                        description=f"🔇 **{user.mention}** a été mis en timeout pour **{mins} minutes**\n**Raison:** {reason}",
                        color=0xED4245
                    ),
                    delete_after=10
                )
            except:
                pass
            
            await log_security_event(
                message.guild, 'mute', user, reason, 'high',
                {'Durée': f"{mins} min", 'Message': message.content[:100]}
            )
        except Exception as e:
            print(f"Erreur mute: {e}")
    
    # KICK
    if action == 'kick':
        try:
            if config.get('dm_sanctions', True):
                try:
                    embed = discord.Embed(
                        title="👢 Expulsion - Lunera Security Ultra",
                        description=f"Vous avez été expulsé de **{message.guild.name}**",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.set_footer(text="🌙 Lunera Security Ultra")
                    await user.send(embed=embed)
                except:
                    pass
            
            await user.kick(reason=f"Lunera Security Ultra: {reason}")
            
            user_infractions[user.id]['kicks'] += 1
            update_trust_score(user.id, message.guild.id, -30)
            update_toxicity_score(user.id, 20)
            
            await log_security_event(
                message.guild, 'kick', user, reason, 'high',
                {'Message': message.content[:100]}
            )
        except Exception as e:
            print(f"Erreur kick: {e}")
    
    # BAN
    if action == 'ban':
        try:
            if config.get('dm_sanctions', True):
                try:
                    embed = discord.Embed(
                        title="🔨 Bannissement - Lunera Security Ultra",
                        description=f"Vous avez été **définitivement banni** de **{message.guild.name}**",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.set_footer(text="🌙 Lunera Security Ultra")
                    await user.send(embed=embed)
                except:
                    pass
            
            await user.ban(reason=f"Lunera Security Ultra: {reason}", delete_message_days=1)
            
            user_infractions[user.id]['bans'] += 1
            update_trust_score(user.id, message.guild.id, -100)
            update_toxicity_score(user.id, 50)
            
            await log_security_event(
                message.guild, 'ban', user, reason, 'critical',
                {'Message': message.content[:100]}
            )
        except Exception as e:
            print(f"Erreur ban: {e}")
    
    # QUARANTINE
    if action == 'quarantine':
        quarantine_role_id = config.get('quarantine_role')
        if quarantine_role_id:
            role = message.guild.get_role(quarantine_role_id)
            if role:
                try:
                    await user.add_roles(role, reason=f"Lunera Security Ultra: {reason}")
                    
                    if config.get('dm_sanctions', True):
                        try:
                            embed = discord.Embed(
                                title="🔒 Quarantaine - Lunera Security Ultra",
                                description=f"Vous avez été mis en quarantaine sur **{message.guild.name}**",
                                color=0xED4245,
                                timestamp=datetime.now()
                            )
                            embed.add_field(name="📝 Raison", value=reason, inline=False)
                            embed.set_footer(text="🌙 Lunera Security Ultra")
                            await user.send(embed=embed)
                        except:
                            pass
                    
                    await log_security_event(
                        message.guild, 'quarantine', user, reason, 'high'
                    )
                except:
                    pass

# ========== FILTRES ULTRA ==========

async def check_spam_ultra(message, config):
    """Anti-spam ultra avancé"""
    if not config.get('spam_protection', True):
        return False
    
    user_id = message.author.id
    now = datetime.now()
    
    message_history[user_id].append(now)
    
    # Spam fréquence
    interval = config.get('spam_interval', 3)
    threshold = config.get('spam_messages', 5)
    recent = [ts for ts in message_history[user_id] if (now - ts).total_seconds() < interval]
    
    if len(recent) >= threshold:
        action = config.get('spam_action', 'mute')
        duration = config.get('spam_mute_duration', 600)
        
        await apply_sanction(
            message,
            f"Spam détecté ({len(recent)} messages en {interval}s)",
            action,
            duration,
            'high'
        )
        message_history[user_id].clear()
        return True
    
    # Spam burst (rafales)
    if config.get('spam_burst_detection', True):
        burst_threshold = config.get('spam_burst_threshold', 10)
        burst_window = 10
        
        burst_msgs = [ts for ts in message_history[user_id] if (now - ts).total_seconds() < burst_window]
        
        if len(burst_msgs) >= burst_threshold:
            await apply_sanction(
                message,
                f"Burst spam détecté ({len(burst_msgs)} messages en {burst_window}s)",
                'mute',
                600,
                'critical'
            )
            message_history[user_id].clear()
            return True
    
    # Messages dupliqués
    if config.get('spam_duplicate_check', True):
        msg_hash = message_hash(message.content)
        duplicate_messages[user_id].append((msg_hash, now))
        
        recent_duplicates = [
            h for h, ts in duplicate_messages[user_id]
            if (now - ts).total_seconds() < 60 and h == msg_hash
        ]
        
        if len(recent_duplicates) >= 3:
            await apply_sanction(
                message,
                "Spam de messages identiques",
                'mute',
                300,
                'high'
            )
            duplicate_messages[user_id].clear()
            return True
        
        # Similarité (messages presque identiques)
        similarity_threshold = config.get('spam_similarity_threshold', 80)
        for old_content, ts in list(spam_tracker[user_id])[-5:]:
            if (now - ts).total_seconds() < 30:
                similarity = message_similarity(message.content, old_content)
                if similarity >= similarity_threshold:
                    await apply_sanction(
                        message,
                        f"Messages très similaires ({similarity}% similarité)",
                        'warn',
                        severity='medium'
                    )
                    return True
        
        spam_tracker[user_id].append((message.content, now))
    
    return False

async def check_image_spam(message, config):
    """Anti-spam images/fichiers"""
    if not config.get('image_spam_protection', True):
        return False
    
    if not message.attachments:
        return False
    
    user_id = message.author.id
    now = datetime.now()
    
    # Trop d'images dans le message
    if len(message.attachments) > config.get('max_images_per_message', 3):
        await apply_sanction(
            message,
            f"Trop d'images dans un message ({len(message.attachments)})",
            config.get('image_spam_action', 'mute'),
            300,
            'medium'
        )
        return True
    
    # Spam d'images dans le temps
    attachment_history[user_id].append(now)
    recent_images = [ts for ts in attachment_history[user_id] if (now - ts).total_seconds() < 60]
    
    max_per_minute = config.get('max_images_per_minute', 5)
    if len(recent_images) > max_per_minute:
        await apply_sanction(
            message,
            f"Spam d'images ({len(recent_images)} en 1 minute)",
            'mute',
            600,
            'high'
        )
        attachment_history[user_id].clear()
        return True
    
    # Fichiers dangereux
    if config.get('dangerous_file_protection', True):
        blocked_ext = config.get('blocked_extensions', [])
        for attachment in message.attachments:
            filename = attachment.filename.lower()
            for ext in blocked_ext:
                if filename.endswith(ext):
                    await apply_sanction(
                        message,
                        f"🚨 Fichier dangereux détecté: {ext}",
                        config.get('dangerous_file_action', 'ban'),
                        severity='critical'
                    )
                    return True
    
    # Taille fichier
    max_size_mb = config.get('max_file_size_mb', 8)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    for attachment in message.attachments:
        if attachment.size > max_size_bytes:
            await apply_sanction(
                message,
                f"Fichier trop volumineux ({attachment.size / 1024 / 1024:.1f} MB)",
                'delete',
                severity='low'
            )
            return True
    
    return False

async def check_emoji_spam(message, config):
    """Anti-spam emojis"""
    if not config.get('emoji_spam_protection', True):
        return False
    
    content = message.content
    
    custom_emojis = len(re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', content))
    unicode_emojis = len(re.findall(r'[\U00010000-\U0010ffff]', content))
    total_emojis = custom_emojis + unicode_emojis
    
    max_emojis = config.get('max_emojis_per_message', 10)
    
    if total_emojis > max_emojis:
        await apply_sanction(
            message,
            f"Spam d'emojis ({total_emojis})",
            'delete',
            severity='low'
        )
        return True
    
    return False

async def check_repetition_ultra(message, config):
    """Anti-répétition avancé"""
    if not config.get('repetition_protection', True):
        return False
    
    content = message.content
    
    # Caractères répétés (aaaaaaa)
    max_repeated = config.get('max_repeated_chars', 8)
    if re.search(r'(.)\1{' + str(max_repeated) + ',}', content):
        await apply_sanction(
            message,
            f"Flood de caractères répétés",
            config.get('repetition_action', 'delete'),
            severity='low'
        )
        return True
    
    # Mots répétés
    if config.get('max_repeated_words', 4):
        words = content.lower().split()
        for word in set(words):
            if len(word) > 2 and words.count(word) > config['max_repeated_words']:
                await apply_sanction(
                    message,
                    f"Répétition excessive du mot '{word}'",
                    'delete',
                    severity='low'
                )
                return True
    
    return False

async def check_phishing_ultra(message, config):
    """Anti-phishing/scam ultra"""
    if not config.get('phishing_protection', True):
        return False
    
    content = message.content.lower()
    
    # Domaines scam connus
    scam_domains = config.get('known_scam_domains', [])
    for domain in scam_domains:
        if domain in content:
            await apply_sanction(
                message,
                f"🎣 Tentative de phishing: {domain}",
                config.get('phishing_action', 'ban'),
                severity='critical'
            )
            return True
    
    # TLD suspects + mots-clés scam
    suspicious_tld = config.get('suspicious_tld', [])
    scam_keywords = ['free', 'nitro', 'gift', 'steam', 'giveaway', 'prize', 'win', 'claim', 'generator']
    
    urls = URL_PATTERN.findall(content)
    for url in urls:
        for tld in suspicious_tld:
            if tld in url:
                if any(keyword in content for keyword in scam_keywords):
                    await apply_sanction(
                        message,
                        f"🎣 Lien suspect ({tld}) avec mots-clés scam",
                        'ban',
                        severity='critical'
                    )
                    return True
    
    # Token Discord
    if config.get('token_grabber_detection', True):
        if TOKEN_PATTERN.search(content):
            await apply_sanction(
                message,
                "🔑 Token Discord détecté - Protection activée",
                'ban',
                severity='critical'
            )
            return True
    
    return False

async def check_words_ultra(message, config):
    """Filtre mots avancé avec bypass detection"""
    if not config.get('word_filter', True):
        return False
    
    content = message.content
    content_normalized = normalize_text(content)
    
    banned_words = config.get('banned_words', [])
    
    for word in banned_words:
        word_normalized = normalize_text(word)
        
        # Recherche exacte ET normalisée (bypass leet speak)
        if word.lower() in content.lower() or word_normalized in content_normalized:
            
            # Calculer toxicité
            toxicity = update_toxicity_score(message.author.id, 10)
            
            # Auto-sanction selon score toxicité
            if config.get('toxicity_scoring', True):
                if toxicity >= config.get('toxicity_auto_ban', 150):
                    await apply_sanction(
                        message,
                        f"Score de toxicité critique ({toxicity}/100) - Mot: {word}",
                        'ban',
                        severity='critical'
                    )
                    return True
                elif toxicity >= config.get('toxicity_auto_mute', 80):
                    await apply_sanction(
                        message,
                        f"Score de toxicité élevé ({toxicity}/100) - Mot: {word}",
                        'mute',
                        1800,
                        'high'
                    )
                    return True
            
            await apply_sanction(
                message,
                f"Mot interdit: **{word}**",
                config.get('word_filter_action', 'warn'),
                severity='medium'
            )
            return True
    
    return False

async def check_links_ultra(message, config):
    """Vérification liens ultra avancée"""
    if not config.get('link_filter', True):
        return False
    
    content = message.content
    
    # Discord invites
    if config.get('block_discord_invites', True):
        if DISCORD_INVITE.search(content):
            await apply_sanction(
                message,
                "Lien d'invitation Discord non autorisé",
                config.get('link_action', 'delete'),
                severity='medium'
            )
            return True
    
    # IPs
    if config.get('block_ip_links', True):
        if IP_PATTERN.search(content):
            await apply_sanction(
                message,
                "Lien IP bloqué (potentiellement dangereux)",
                'warn',
                severity='high'
            )
            return True
    
    # URL shorteners
    if config.get('block_url_shorteners', True):
        for shortener in URL_SHORTENERS:
            if shortener in content.lower():
                await apply_sanction(
                    message,
                    f"Lien raccourci non autorisé: {shortener}",
                    'delete',
                    severity='medium'
                )
                return True
    
    # Liens généraux
    if not config.get('allow_links', False):
        urls = URL_PATTERN.findall(content)
        if urls:
            whitelist = config.get('whitelist_domains', [])
            for url in urls:
                allowed = any(domain in url.lower() for domain in whitelist)
                
                if not allowed:
                    await apply_sanction(
                        message,
                        "Lien non autorisé",
                        config.get('link_action', 'delete'),
                        severity='low'
                    )
                    return True
    
    return False

async def check_mentions_ultra(message, config):
    """Anti-mention spam ultra"""
    if not config.get('mention_protection', True):
        return False
    
    user_mentions = len(message.mentions)
    role_mentions = len(message.role_mentions)
    
    # @everyone/@here
    if not config.get('everyone_mention_allowed', False):
        if message.mention_everyone:
            await apply_sanction(
                message,
                "Mention @everyone/@here non autorisée",
                config.get('mention_action', 'warn'),
                severity='high'
            )
            return True
    
    # Mass mention = raid
    mass_threshold = config.get('mass_mention_threshold', 10)
    total_mentions = user_mentions + role_mentions
    
    if total_mentions >= mass_threshold:
        await apply_sanction(
            message,
            f"🚨 Mass mention détecté ({total_mentions})",
            config.get('mass_mention_action', 'mute'),
            1800,
            'critical'
        )
        return True
    
    # Mentions utilisateurs
    max_mentions = config.get('max_mentions', 5)
    if user_mentions > max_mentions:
        await apply_sanction(
            message,
            f"Spam de mentions ({user_mentions})",
            config.get('mention_action', 'warn'),
            severity='medium'
        )
        return True
    
    # Mentions rôles
    max_role_mentions = config.get('max_role_mentions', 2)
    if role_mentions > max_role_mentions:
        await apply_sanction(
            message,
            f"Spam de mentions de rôles ({role_mentions})",
            'warn',
            severity='high'
        )
        return True
    
    return False

async def check_caps_flood_ultra(message, config):
    """Anti-caps et flood avancé"""
    content = message.content
    
    # Zalgo
    if is_zalgo(content):
        await apply_sanction(
            message,
            "Texte zalgo/corrompu détecté",
            'delete',
            severity='medium'
        )
        return True
    
    # Caractères invisibles
    if config.get('invisible_char_detection', True):
        for char in INVISIBLE_CHARS:
            if char in content:
                await apply_sanction(
                    message,
                    "Message avec caractères invisibles",
                    'delete',
                    severity='medium'
                )
                return True
    
    # Message vide
    if config.get('empty_message_protection', True):
        if len(content.strip()) == 0 and not message.attachments:
            await apply_sanction(
                message,
                "Message vide détecté",
                'delete',
                severity='low'
            )
            return True
    
    # Flood caractères
    if config.get('flood_protection', True):
        max_repeated = config.get('max_repeated_chars', 8)
        if re.search(r'(.)\1{' + str(max_repeated) + ',}', content):
            await apply_sanction(
                message,
                "Flood de caractères",
                config.get('flood_action', 'delete'),
                severity='low'
            )
            return True
    
    # Caps abuse
    if config.get('caps_filter', True):
        min_length = config.get('min_caps_length', 10)
        if len(content) >= min_length:
            caps_count = sum(1 for c in content if c.isupper())
            alpha_count = sum(1 for c in content if c.isalpha())
            
            if alpha_count > 0:
                caps_percentage = (caps_count / alpha_count) * 100
                max_caps = config.get('max_caps_percentage', 60)
                
                if caps_percentage > max_caps:
                    await apply_sanction(
                        message,
                        f"Abus de majuscules ({int(caps_percentage)}%)",
                        config.get('caps_action', 'delete'),
                        severity='low'
                    )
                    return True
    
    return False

async def check_hacked_account(message, config):
    """Détection compte hacké/comportement suspect"""
    if not config.get('hacked_account_detection', True):
        return False
    
    user_id = message.author.id
    now = datetime.now()
    
    behavior = user_behavior_tracker[user_id]
    behavior['message_burst'].append(now)
    
    # Spam soudain = compte hacké possible
    threshold = config.get('sudden_spam_threshold', 8)
    recent_burst = [ts for ts in behavior['message_burst'] if (now - ts).total_seconds() < 5]
    
    if len(recent_burst) >= threshold:
        behavior['sudden_spam'] = True
        
        await apply_sanction(
            message,
            f"🚨 Comportement suspect: spam soudain ({len(recent_burst)} msgs/5s)",
            config.get('sudden_spam_action', 'mute'),
            1800,
            'critical'
        )
        
        # Alert staff
        alert_channel_id = config.get('alert_channel')
        if alert_channel_id:
            alert_channel = message.guild.get_channel(alert_channel_id)
            if alert_channel:
                await alert_channel.send(
                    embed=discord.Embed(
                        title="🚨 COMPTE POSSIBLEMENT HACKÉ",
                        description=f"{message.author.mention} montre un comportement de spam soudain.\n**Action:** Mute automatique\n**Vérification recommandée**",
                        color=0xED4245
                    )
                )
        
        return True
    
    # Spam de liens
    if URL_PATTERN.findall(message.content):
        behavior['link_spam'].append(now)
        recent_links = [ts for ts in behavior['link_spam'] if (now - ts).total_seconds() < 60]
        
        if len(recent_links) >= 5:
            await apply_sanction(
                message,
                "Spam de liens suspect",
                'mute',
                600,
                'high'
            )
            return True
    
    # Spam d'images
    if message.attachments:
        behavior['image_spam'].append(now)
        recent_images = [ts for ts in behavior['image_spam'] if (now - ts).total_seconds() < 30]
        
        if len(recent_images) >= 4:
            await apply_sanction(
                message,
                "Spam d'images suspect",
                'mute',
                600,
                'high'
            )
            return True
    
    # Auto-slowmode utilisateur
    if config.get('auto_slowmode_user', True):
        slowmode_duration = config.get('slowmode_duration', 10)
        last_slowmode = behavior.get('last_slowmode')
        
        if last_slowmode and (now - last_slowmode).total_seconds() < slowmode_duration:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} Ralentissez ! ({slowmode_duration}s entre messages)",
                    delete_after=5
                )
            except:
                pass
            return True
        
        # Activer slowmode si burst
        if len(recent_burst) >= 5:
            behavior['last_slowmode'] = now
    
    return False

# ========== ANTI-RAID & LOCKDOWN ==========

async def on_lunera_member_join(member):
    """Anti-raid ultra sur join"""
    guild = member.guild
    config = get_config(guild.id)
    
    if not config.get('raid_protection', True):
        return
    
    now = datetime.now()
    raid_tracker[guild.id].append((member.id, now))
    
    interval = config.get('raid_interval', 8)
    raid_tracker[guild.id] = [
        (uid, ts) for uid, ts in raid_tracker[guild.id]
        if (now - ts).total_seconds() < interval
    ]
    
    recent_joins = len(raid_tracker[guild.id])
    threshold = config.get('raid_joins', 6)
    
    # Âge du compte
    account_age_minutes = (now - member.created_at.replace(tzinfo=None)).total_seconds() / 60
    account_age_hours = account_age_minutes / 60
    
    min_age_minutes = config.get('raid_account_age_minutes', 30)
    min_age_hours = config.get('raid_account_age_hours', 24)
    
    is_very_new = account_age_minutes < min_age_minutes
    is_new = account_age_hours < min_age_hours
    
    # Compte suspect
    is_suspicious = False
    suspicion_reasons = []
    
    if is_very_new:
        is_suspicious = True
        suspicion_reasons.append(f"Compte créé il y a {int(account_age_minutes)}min")
        update_trust_score(member.id, guild.id, -30)
    elif is_new:
        is_suspicious = True
        suspicion_reasons.append(f"Compte créé il y a {int(account_age_hours)}h")
        update_trust_score(member.id, guild.id, -15)
    
    if member.avatar is None:
        is_suspicious = True
        suspicion_reasons.append("Pas d'avatar")
        update_trust_score(member.id, guild.id, -10)
    
    # Anti-hoisting
    if config.get('anti_hoisting', True):
        hoist_chars = config.get('hoist_characters', [])
        if any(member.name.startswith(char) for char in hoist_chars):
            is_suspicious = True
            suspicion_reasons.append("Nom suspect (hoisting)")
            update_trust_score(member.id, guild.id, -10)
            
            # Rename
            try:
                new_name = "Modéré " + member.name.lstrip(''.join(hoist_chars))
                await member.edit(nick=new_name)
            except:
                pass
    
    # RAID DÉTECTÉ
    if recent_joins >= threshold:
        # Lockdown automatique
        if config.get('raid_auto_lockdown', True):
            lockdown_threshold = config.get('raid_lockdown_threshold', 8)
            
            if recent_joins >= lockdown_threshold:
                await activate_lockdown(guild, "RAID DÉTECTÉ - Lockdown automatique")
        
        # Kick comptes suspects pendant raid
        if is_suspicious and config.get('raid_kick_new_accounts', True):
            try:
                await member.kick(reason=f"Lunera: Raid - {', '.join(suspicion_reasons)}")
                
                await log_security_event(
                    guild, 'raid', member,
                    f"Kick pendant raid: {', '.join(suspicion_reasons)}",
                    'critical',
                    {'Joins récents': recent_joins}
                )
            except:
                pass
            return
        
        # Alerte raid
        alert_channel_id = config.get('alert_channel') or config.get('log_channel')
        if alert_channel_id:
            alert_channel = guild.get_channel(alert_channel_id)
            if alert_channel:
                staff_role_id = config.get('staff_ping_role')
                ping = f"<@&{staff_role_id}>" if staff_role_id else "@Staff"
                
                embed = discord.Embed(
                    title="🚨 RAID DÉTECTÉ - LUNERA SECURITY ULTRA",
                    description=f"**{recent_joins} utilisateurs** ont rejoint en {interval}s !",
                    color=0xED4245,
                    timestamp=datetime.now()
                )
                
                if config.get('lockdown_active', False):
                    embed.add_field(name="⚡ Statut", value="✅ **LOCKDOWN ACTIVÉ**", inline=False)
                else:
                    embed.add_field(name="⚡ Action", value="⚠️ Seuil de raid atteint", inline=False)
                
                embed.add_field(name="🛡️ Protection", value="Comptes suspects kick automatique", inline=False)
                embed.add_field(name="🔧 Commandes", value="`/lunera_lockdown` pour verrouiller\n`/lunera_unlockdown` pour débloquer", inline=False)
                embed.set_footer(text="🌙 Lunera Security Ultra")
                
                try:
                    await alert_channel.send(f"{ping}", embed=embed)
                except:
                    pass
    
    # Quarantaine auto des comptes très suspects
    elif is_very_new:
        trust_score = get_trust_score(member.id, guild.id)
        quarantine_threshold = config.get('auto_quarantine_threshold', 25)
        
        if trust_score < quarantine_threshold:
            quarantine_role_id = config.get('quarantine_role')
            if quarantine_role_id:
                role = guild.get_role(quarantine_role_id)
                if role:
                    try:
                        await member.add_roles(role, reason=f"Lunera: Compte très suspect - {', '.join(suspicion_reasons)}")
                        
                        await log_security_event(
                            guild, 'quarantine', member,
                            f"Auto-quarantaine: {', '.join(suspicion_reasons)}",
                            'high'
                        )
                    except:
                        pass

async def activate_lockdown(guild, reason="Lockdown manuel"):
    """Active le mode lockdown"""
    config = get_config(guild.id)
    
    if config.get('lockdown_active', False):
        return  # Déjà lockdown
    
    config['lockdown_active'] = True
    
    locked = 0
    for channel in guild.text_channels:
        try:
            await channel.set_permissions(
                guild.default_role,
                send_messages=False,
                reason=reason
            )
            locked += 1
        except:
            pass
    
    # Auto-unlock après X minutes
    auto_unlock_mins = config.get('lockdown_auto_unlock_minutes', 30)
    if auto_unlock_mins > 0:
        await asyncio.sleep(auto_unlock_mins * 60)
        
        # Vérifier si toujours lockdown
        if config.get('lockdown_active', False):
            await deactivate_lockdown(guild, "Auto-unlock après timeout")

async def deactivate_lockdown(guild, reason="Lockdown levé"):
    """Désactive le mode lockdown"""
    config = get_config(guild.id)
    
    if not config.get('lockdown_active', False):
        return
    
    config['lockdown_active'] = False
    
    unlocked = 0
    for channel in guild.text_channels:
        try:
            await channel.set_permissions(
                guild.default_role,
                send_messages=None,
                reason=reason
            )
            unlocked += 1
        except:
            pass

async def on_lunera_voice_join(member, channel):
    """Anti-raid vocal"""
    guild = member.guild
    config = get_config(guild.id)
    
    if not config.get('raid_voice_protection', True):
        return
    
    now = datetime.now()
    voice_raid_tracker[guild.id].append((member.id, now))
    
    voice_raid_tracker[guild.id] = [
        (uid, ts) for uid, ts in voice_raid_tracker[guild.id]
        if (now - ts).total_seconds() < 10
    ]
    
    recent_voice_joins = len(voice_raid_tracker[guild.id])
    max_voice_joins = config.get('raid_max_voice_joins', 4)
    
    if recent_voice_joins >= max_voice_joins:
        try:
            await member.move_to(None, reason="Lunera: Raid vocal détecté")
            
            await log_security_event(
                guild, 'raid', member,
                f"Raid vocal ({recent_voice_joins} joins)",
                'high'
            )
        except:
            pass

# ========== ANTI-NUKE ==========

async def on_lunera_channel_delete(channel):
    """Détection suppression massive de salons"""
    guild = channel.guild
    config = get_config(guild.id)
    
    if not config.get('anti_nuke_protection', True):
        return
    
    now = datetime.now()
    channel_delete_tracker[guild.id].append(now)
    
    recent_deletes = [
        ts for ts in channel_delete_tracker[guild.id]
        if (now - ts).total_seconds() < 60
    ]
    
    max_deletes = config.get('max_channel_deletes', 3)
    
    if len(recent_deletes) >= max_deletes:
        # NUKE DÉTECTÉ
        if config.get('nuke_detection_action', 'lockdown') == 'lockdown':
            await activate_lockdown(guild, "🚨 NUKE DÉTECTÉ - Suppression massive de salons")
        
        # Alert
        alert_channel_id = config.get('alert_channel')
        if alert_channel_id:
            alert_channel = guild.get_channel(alert_channel_id)
            if alert_channel:
                await alert_channel.send(
                    embed=discord.Embed(
                        title="🚨 TENTATIVE DE NUKE DÉTECTÉE",
                        description=f"**{len(recent_deletes)} salons** supprimés en 1 minute !\n\n**Action:** Lockdown automatique activé",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                )

async def on_lunera_role_delete(role):
    """Détection suppression massive de rôles"""
    guild = role.guild
    config = get_config(guild.id)
    
    if not config.get('anti_nuke_protection', True):
        return
    
    now = datetime.now()
    role_delete_tracker[guild.id].append(now)
    
    recent_deletes = [
        ts for ts in role_delete_tracker[guild.id]
        if (now - ts).total_seconds() < 60
    ]
    
    max_deletes = config.get('max_role_deletes', 3)
    
    if len(recent_deletes) >= max_deletes:
        if config.get('nuke_detection_action', 'lockdown') == 'lockdown':
            await activate_lockdown(guild, "🚨 NUKE DÉTECTÉ - Suppression massive de rôles")

# ========== GHOST PING & EDITS ==========

async def on_lunera_message_delete(message):
    """Détection ghost ping et logs"""
    if message.author.bot:
        return
    
    config = get_config(message.guild.id)
    
    # Ghost ping
    if config.get('ghost_ping_protection', True):
        if message.mentions or message.mention_everyone:
            ghost_ping_tracker[message.guild.id].append({
                'author': message.author,
                'mentions': [m.id for m in message.mentions],
                'everyone': message.mention_everyone,
                'timestamp': datetime.now(),
                'channel': message.channel
            })
            
            # Notifier
            try:
                mentioned_users = ", ".join([m.mention for m in message.mentions[:5]])
                if len(message.mentions) > 5:
                    mentioned_users += f" et {len(message.mentions) - 5} autres"
                
                await message.channel.send(
                    embed=discord.Embed(
                        title="👻 Ghost Ping Détecté",
                        description=f"{message.author.mention} a mentionné {mentioned_users} puis supprimé le message",
                        color=0xFEE75C
                    ),
                    delete_after=10
                )
            except:
                pass
    
    # Log delete
    if config.get('log_deletes', True):
        await log_security_event(
            message.guild, 'delete', message.author,
            f"Message supprimé dans {message.channel.mention}",
            'low',
            {'Contenu': message.content[:200]}
        )

async def on_lunera_message_edit(before, after):
    """Log des edits"""
    if before.author.bot or before.content == after.content:
        return
    
    config = get_config(before.guild.id)
    
    if config.get('log_edits', True):
        edit_tracker[before.guild.id].append({
            'author': before.author.id,
            'before': before.content,
            'after': after.content,
            'timestamp': datetime.now()
        })
        
        await log_security_event(
            before.guild, 'edit', before.author,
            f"Message édité dans {before.channel.mention}",
            'low',
            {
                'Avant': before.content[:200],
                'Après': after.content[:200]
            }
        )

# ========== REACTION SPAM ==========

async def on_lunera_reaction_add(reaction, user):
    """Anti-spam réactions"""
    if user.bot:
        return
    
    guild = reaction.message.guild
    if not guild:
        return
    
    config = get_config(guild.id)
    
    if not config.get('reaction_spam_protection', True):
        return
    
    now = datetime.now()
    reaction_spam_tracker[user.id].append(now)
    
    recent_reactions = [
        ts for ts in reaction_spam_tracker[user.id]
        if (now - ts).total_seconds() < 60
    ]
    
    max_reactions = config.get('max_reactions_per_minute', 15)
    
    if len(recent_reactions) > max_reactions:
        # Spam de réactions
        try:
            # Impossible de timeout juste pour ça, mais on peut warn
            await log_security_event(
                guild, 'reaction', user,
                f"Spam de réactions ({len(recent_reactions)}/min)",
                'medium'
            )
            
            # Supprimer les réactions
            try:
                await reaction.remove(user)
            except:
                pass
            
        except:
            pass

# ========== WEBHOOK SPAM ==========

async def on_lunera_webhook_message(message):
    """Anti-spam webhook"""
    if not message.webhook_id:
        return
    
    guild = message.guild
    config = get_config(guild.id)
    
    if not config.get('webhook_protection', True):
        return
    
    now = datetime.now()
    webhook_spam_tracker[message.webhook_id].append(now)
    
    interval = config.get('webhook_spam_interval', 5)
    recent = [
        ts for ts in webhook_spam_tracker[message.webhook_id]
        if (now - ts).total_seconds() < interval
    ]
    
    max_messages = config.get('max_webhook_messages', 10)
    
    if len(recent) > max_messages:
        # Spam webhook
        try:
            webhook = await message.guild.webhooks()
            for wh in webhook:
                if wh.id == message.webhook_id:
                    await wh.delete(reason="Lunera: Webhook spam détecté")
                    break
            
            await log_security_event(
                guild, 'webhook', message.author,
                f"Webhook spam ({len(recent)} msgs/{interval}s)",
                'high'
            )
        except:
            pass

# ========== HANDLER PRINCIPAL ==========

async def on_lunera_message(message):
    """Handler principal Lunera Security Ultra"""
    if message.author.bot:
        # Vérifier webhook spam
        if message.webhook_id:
            await on_lunera_webhook_message(message)
        return
    
    if not message.guild:
        return
    
    config = get_config(message.guild.id)
    
    if not config.get('enabled', True):
        return
    
    # Vérifier immunité
    if is_immune(message.author, config):
        return
    
    # Salon ignoré
    if message.channel.id in config.get('ignored_channels', []):
        return
    
    # Lockdown actif
    if config.get('lockdown_active', False):
        try:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} Le serveur est en mode lockdown. Veuillez patienter.",
                delete_after=5
            )
        except:
            pass
        return
    
    # Vérifier score de confiance
    if config.get('trust_score_enabled', True):
        trust_score = get_trust_score(message.author.id, message.guild.id)
        threshold = config.get('auto_quarantine_threshold', 25)
        
        if trust_score < threshold:
            quarantine_role_id = config.get('quarantine_role')
            if quarantine_role_id:
                role = message.guild.get_role(quarantine_role_id)
                if role and role not in message.author.roles:
                    try:
                        await message.author.add_roles(role, reason=f"Lunera: Score critique ({trust_score})")
                        await log_security_event(
                            message.guild, 'quarantine', message.author,
                            f"Auto-quarantaine (score: {trust_score}/100)",
                            'high'
                        )
                    except:
                        pass
    
    # === FILTRES PRIORITAIRES ===
    filters = [
        check_phishing_ultra,          # 1. Phishing/scam
        check_image_spam,              # 2. Fichiers dangereux
        check_hacked_account,          # 3. Compte hacké
        check_spam_ultra,              # 4. Spam messages
        check_words_ultra,             # 5. Mots interdits
        check_links_ultra,             # 6. Liens
        check_mentions_ultra,          # 7. Mentions
        check_emoji_spam,              # 8. Emojis
        check_repetition_ultra,        # 9. Répétition
        check_caps_flood_ultra,        # 10. Caps/flood
    ]
    
    for filter_func in filters:
        try:
            if await filter_func(message, config):
                return  # Stop au premier match
        except Exception as e:
            print(f"Erreur Lunera {filter_func.__name__}: {e}")
    
    # Message légitime = améliorer scores
    if config.get('trust_score_enabled', True):
        update_trust_score(message.author.id, message.guild.id, 0.3)
    
    # Réduire toxicité lentement
    if config.get('toxicity_scoring', True):
        toxicity = get_toxicity_score(message.author.id)
        if toxicity > 0:
            update_toxicity_score(message.author.id, -0.5)

# ========== COMMANDES SLASH ULTRA ==========

async def setup_lunera_commands_ultra(bot):
    """Configure les commandes Lunera Security Ultra"""
    
    # Toutes vos commandes actuelles + nouvelles
    
    @bot.tree.command(name="lunera_panel", description="🌙 Panneau principal Lunera Security Ultra")
    async def lunera_panel(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        
        embed = discord.Embed(
            title="🌙 LUNERA SECURITY ULTRA v3.0",
            description="**Protection maximale contre raids, spam et menaces**\n\n"
                       "🛡️ Système de sécurité de nouvelle génération\n"
                       "⚡ Protection en temps réel\n"
                       "🤖 Intelligence artificielle anti-menaces",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # Statut modules
        modules = {
            'spam_protection': '🚫 Anti-Spam Ultra',
            'raid_protection': '🛡️ Anti-Raid',
            'phishing_protection': '🎣 Anti-Phishing',
            'word_filter': '🔤 Filtre Toxicité',
            'link_filter': '🔗 Protection Liens',
            'mention_protection': '👥 Anti-Mention Spam',
            'image_spam_protection': '🖼️ Anti-Spam Images',
            'dangerous_file_protection': '📁 Protection Fichiers',
            'hacked_account_detection': '🚨 Détection Hack',
            'anti_nuke_protection': '💥 Anti-Nuke',
        }
        
        status_list = []
        for key, name in modules.items():
            status = "✅" if config.get(key, True) else "❌"
            status_list.append(f"{status} {name}")
        
        embed.add_field(
            name="📋 Modules Actifs",
            value="\n".join(status_list[:5]),
            inline=True
        )
        
        embed.add_field(
            name="⚙️ Modules Avancés",
            value="\n".join(status_list[5:]),
            inline=True
        )
        
        # Niveau protection
        level = config.get('protection_level', 'maximum')
        level_emoji = {'low': '🟢', 'medium': '🟡', 'high': '🟠', 'maximum': '🔴', 'ultra': '⚫'}
        
        embed.add_field(
            name="🎯 Niveau de Protection",
            value=f"{level_emoji.get(level, '🔴')} **{level.upper()}**",
            inline=False
        )
        
        # Lockdown status
        if config.get('lockdown_active', False):
            embed.add_field(
                name="🔐 Statut Lockdown",
                value="**🔴 ACTIF**",
                inline=True
            )
        
        # Stats
        total_warns = sum(
            len([w for w in warns if w['guild_id'] == interaction.guild.id])
            for warns in user_warnings.values()
        )
        
        embed.add_field(name="📊 Warns Actifs", value=str(total_warns), inline=True)
        embed.add_field(name="🔒 Quarantaine", value=str(len(suspicious_users.get(interaction.guild.id, set()))), inline=True)
        
        embed.set_footer(text="🌙 Lunera Security Ultra v3.0 - Protection maximale")
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_lockdown", description="🔒 Activer le mode lockdown")
    async def lunera_lockdown_cmd(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        await activate_lockdown(interaction.guild, f"Lockdown manuel par {interaction.user.name}")
        
        embed = discord.Embed(
            title="🔒 SERVEUR VERROUILLÉ",
            description="Le mode lockdown a été activé avec succès",
            color=0xED4245,
            timestamp=datetime.now()
        )
        embed.add_field(name="🛡️ Protection", value="Tous les salons sont verrouillés", inline=False)
        embed.add_field(name="🔓 Déverrouillage", value="Utilisez `/lunera_unlockdown`", inline=False)
        embed.set_footer(text="🌙 Lunera Security Ultra")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_unlockdown", description="🔓 Désactiver le mode lockdown")
    async def lunera_unlockdown_cmd(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        await deactivate_lockdown(interaction.guild, f"Unlock manuel par {interaction.user.name}")
        
        embed = discord.Embed(
            title="🔓 SERVEUR DÉVERROUILLÉ",
            description="Le mode lockdown a été désactivé",
            color=0x57F287,
            timestamp=datetime.now()
        )
        embed.set_footer(text="🌙 Lunera Security Ultra")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    # Ajouter toutes vos autres commandes ici
    # (lunera_config, lunera_toggle, lunera_trust, lunera_stats, etc.)

print("🌙 ✅ Lunera Security Ultra v3.0 chargé avec succès")
