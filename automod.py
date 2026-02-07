"""
🌙 LUNERA SECURITY 🛡️
Système de sécurité et modération automatique ultra-complet
Protégez votre serveur avec intelligence et élégance
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio
import hashlib

# ========== STOCKAGE DES DONNÉES ==========
lunera_config = {}
user_warnings = defaultdict(list)
user_infractions = defaultdict(lambda: {'warns': 0, 'mutes': 0, 'kicks': 0})
message_history = defaultdict(lambda: deque(maxlen=15))
spam_tracker = defaultdict(lambda: deque(maxlen=10))
raid_tracker = defaultdict(list)
suspicious_users = defaultdict(set)
phishing_cache = set()
user_trust_scores = defaultdict(lambda: 100)  # Score de confiance 0-100

# Détection avancée
duplicate_messages = defaultdict(lambda: deque(maxlen=5))
attachment_history = defaultdict(list)
voice_raid_tracker = defaultdict(list)

# ========== CONFIGURATION PAR DÉFAUT ==========
DEFAULT_CONFIG = {
    # Système général
    'enabled': True,
    'log_channel': None,
    'alert_channel': None,
    'quarantine_role': None,
    
    # Niveaux de protection
    'protection_level': 'medium',  # low, medium, high, maximum
    
    # ===== MODULES DE SÉCURITÉ =====
    
    # 1. Anti-Spam Avancé
    'spam_protection': True,
    'spam_messages': 5,
    'spam_interval': 4,
    'spam_action': 'mute',
    'spam_mute_duration': 600,
    'spam_duplicate_check': True,  # Détecte les messages identiques
    'spam_similarity_threshold': 85,  # % de similarité
    
    # 2. Anti-Raid Intelligent
    'raid_protection': True,
    'raid_joins': 8,
    'raid_interval': 10,
    'raid_account_age': 7,
    'raid_auto_lockdown': True,
    'raid_voice_protection': True,  # Anti-raid vocal
    'raid_max_voice_joins': 5,
    
    # 3. Filtre de Contenu
    'word_filter': True,
    'banned_words':[
    'malpt',
    'baiser', 'bander', 'bigornette', 'bite', 'bitte', 'bloblos',
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
    'folle',
    'foutre',
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
    'étron'
]

    ],
    'word_filter_action': 'delete',
    'word_filter_sensitivity': 'high',  # low, medium, high
    
    # 4. Anti-Phishing/Scam
    'phishing_protection': True,
    'phishing_action': 'ban',
    'known_scam_domains': [
        'discord-nitro', 'discordgift', 'steamcommunity-gift',
        'free-nitro', 'discord-app', 'steamnitro'
    ],
    'suspicious_tld': ['.tk', '.ml', '.ga', '.cf', '.gq', '.xyz'],
    
    # 5. Gestion des Liens
    'link_filter': True,
    'allow_links': False,
    'whitelist_domains': ['youtube.com', 'youtu.be', 'twitter.com', 'twitch.tv'],
    'block_discord_invites': True,
    'block_url_shorteners': True,
    'block_ip_links': True,
    'link_action': 'delete',
    
    # 6. Anti-Mentions
    'mention_protection': True,
    'max_mentions': 4,
    'max_role_mentions': 2,
    'mention_action': 'warn',
    'everyone_mention_allowed': False,
    
    # 7. Anti-Caps/Emoji/Flood
    'caps_filter': True,
    'max_caps_percentage': 65,
    'min_caps_length': 8,
    'emoji_filter': True,
    'max_emojis': 8,
    'flood_protection': True,
    'max_repeated_chars': 10,
    
    # 8. Protection des Images/Fichiers
    'image_protection': True,
    'max_images_per_message': 5,
    'suspicious_file_extensions': ['.exe', '.bat', '.cmd', '.scr', '.jar'],
    'image_spam_threshold': 3,  # images en 10s
    
    # 9. Anti-Hoisting (noms commençant par symboles)
    'anti_hoisting': True,
    'hoist_characters': ['!', '?', '.', '|', '*', '#'],
    
    # 10. Anti-Token Grabber
    'token_protection': True,
    'token_patterns': [
        r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}',  # Discord token
        r'mfa\.[A-Za-z0-9_-]{84}',  # MFA token
    ],
    
    # 11. Détection de Comportement Suspect
    'behavior_analysis': True,
    'trust_score_enabled': True,
    'auto_quarantine_threshold': 30,  # Score < 30 = quarantaine
    
    # ===== SYSTÈME DE SANCTIONS =====
    'warn_threshold': 3,
    'mute_duration': 1800,  # 30 min
    'warn_reset_days': 7,
    'progressive_sanctions': True,  # Sanctions progressives
    
    # ===== EXCEPTIONS =====
    'immune_roles': [],
    'immune_users': [],
    'ignored_channels': [],
    'verified_role': None,  # Rôle vérifié = immunité partielle
    
    # ===== NOTIFICATIONS =====
    'dm_warnings': True,
    'dm_sanctions': True,
    'staff_ping_role': None,
    'detailed_logs': True,
}

# ========== PATTERNS DE DÉTECTION ==========

# Discord invites (tous formats)
DISCORD_INVITE = re.compile(
    r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/|discord\.me/)[a-zA-Z0-9\-]+',
    re.IGNORECASE
)

# URLs complètes
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
    re.IGNORECASE
)

# IPs (IPv4 et IPv6)
IP_PATTERN = re.compile(
    r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b|\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'
)

# URL shorteners
URL_SHORTENERS = [
    'bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ow.ly', 'buff.ly',
    'adf.ly', 'bit.do', 'short.io', 'rebrand.ly', 'cutt.ly', 'is.gd'
]

# Zalgo detection
def is_zalgo(text):
    """Détecte le texte zalgo (corruption Unicode)"""
    zalgo_chars = sum(1 for c in text if '\u0300' <= c <= '\u036f')
    return zalgo_chars > len(text) * 0.4

# Normalisation de texte avancée
def normalize_text(text):
    """Normalise le texte pour détecter contournements"""
    # Supprimer espaces, underscores, tirets
    text = re.sub(r'[\s_\-.]', '', text)
    # Remplacer caractères similaires
    replacements = {
        '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
        '7': 't', '8': 'b', '@': 'a', '$': 's', '€': 'e'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Supprimer répétitions
    text = re.compile(r'(.)\1+').sub(r'\1', text)
    return text.lower()

# Similarité de messages (Levenshtein simplifié)
def message_similarity(msg1, msg2):
    """Calcule la similarité entre deux messages (0-100%)"""
    if msg1 == msg2:
        return 100
    
    len1, len2 = len(msg1), len(msg2)
    if abs(len1 - len2) > max(len1, len2) * 0.5:
        return 0
    
    # Compter caractères communs
    common = sum(1 for a, b in zip(msg1, msg2) if a == b)
    return int((common / max(len1, len2)) * 100)

# Hash de message pour détecter duplicatas
def message_hash(content):
    """Crée un hash du message"""
    normalized = normalize_text(content)
    return hashlib.md5(normalized.encode()).hexdigest()

# ========== FONCTIONS UTILITAIRES ==========

def get_config(guild_id):
    """Récupère la config d'un serveur"""
    if guild_id not in lunera_config:
        lunera_config[guild_id] = DEFAULT_CONFIG.copy()
    return lunera_config[guild_id]

def is_immune(member, config):
    """Vérifie si un membre est immunisé"""
    # Admins toujours immunisés
    if member.guild_permissions.administrator:
        return True
    
    # Utilisateurs immunisés
    if member.id in config.get('immune_users', []):
        return True
    
    # Rôles immunisés
    for role in member.roles:
        if role.id in config.get('immune_roles', []):
            return True
    
    # Rôle vérifié = immunité partielle
    verified_role_id = config.get('verified_role')
    if verified_role_id:
        if any(r.id == verified_role_id for r in member.roles):
            return True
    
    return False

def update_trust_score(user_id, guild_id, delta):
    """Met à jour le score de confiance d'un utilisateur"""
    key = f"{guild_id}_{user_id}"
    user_trust_scores[key] = max(0, min(100, user_trust_scores[key] + delta))
    return user_trust_scores[key]

def get_trust_score(user_id, guild_id):
    """Récupère le score de confiance"""
    key = f"{guild_id}_{user_id}"
    return user_trust_scores.get(key, 100)

async def log_security_event(guild, event_type, user, reason, severity='medium', extra_data=None):
    """Log un événement de sécurité"""
    config = get_config(guild.id)
    log_channel_id = config.get('log_channel')
    
    if not log_channel_id:
        return
    
    log_channel = guild.get_channel(log_channel_id)
    if not log_channel:
        return
    
    # Couleurs selon sévérité
    colors = {
        'low': 0x57F287,      # Vert
        'medium': 0xFEE75C,   # Jaune
        'high': 0xED4245,     # Rouge
        'critical': 0x5865F2  # Bleu foncé
    }
    
    # Emojis selon type
    emojis = {
        'spam': '🚫',
        'raid': '🛡️',
        'phishing': '🎣',
        'scam': '⚠️',
        'word': '🔤',
        'link': '🔗',
        'mention': '👥',
        'token': '🔑',
        'suspicious': '🔍',
        'quarantine': '🔒',
        'ban': '🔨',
        'mute': '🔇',
        'warn': '⚠️'
    }
    
    embed = discord.Embed(
        title=f"{emojis.get(event_type, '🛡️')} Lunera Security - {event_type.upper()}",
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
        value=reason,
        inline=True
    )
    
    embed.add_field(
        name="🎯 Sévérité",
        value=severity.upper(),
        inline=True
    )
    
    # Score de confiance
    trust_score = get_trust_score(user.id, guild.id)
    trust_emoji = "🟢" if trust_score >= 70 else "🟡" if trust_score >= 40 else "🔴"
    embed.add_field(
        name="📊 Score de confiance",
        value=f"{trust_emoji} {trust_score}/100",
        inline=True
    )
    
    # Infractions totales
    infractions = user_infractions[user.id]
    embed.add_field(
        name="📋 Historique",
        value=f"Warns: {infractions['warns']} | Mutes: {infractions['mutes']} | Kicks: {infractions['kicks']}",
        inline=True
    )
    
    # Données supplémentaires
    if extra_data and config.get('detailed_logs', True):
        for key, value in extra_data.items():
            embed.add_field(name=key, value=str(value), inline=True)
    
    embed.set_footer(text="🌙 Lunera Security", icon_url=guild.icon.url if guild.icon else None)
    embed.set_thumbnail(url=user.display_avatar.url)
    
    try:
        await log_channel.send(embed=embed)
    except:
        pass

async def apply_sanction(message, reason, action='warn', duration=None, severity='medium'):
    """Applique une sanction avec le système Lunera"""
    config = get_config(message.guild.id)
    user = message.author
    
    # Message de notification pour l'utilisateur
    notification_sent = False
    
    # === DELETE (avec notification) ===
    if action == 'delete':
        try:
            await message.delete()
            
            # Notifier l'utilisateur en DM
            if config.get('dm_warnings', True):
                try:
                    embed = discord.Embed(
                        title="🗑️ Message supprimé - Lunera Security",
                        description=f"**Serveur:** {message.guild.name}\n**Salon:** {message.channel.mention}",
                        color=0xFEE75C,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.add_field(name="💬 Votre message", value=f"```{message.content[:200]}```", inline=False)
                    embed.add_field(name="💡 Conseil", value="Veuillez respecter les règles du serveur", inline=False)
                    embed.set_footer(text="🌙 Lunera Security")
                    await user.send(embed=embed)
                    notification_sent = True
                except:
                    pass
            
            # Message dans le salon (temporaire)
            if not notification_sent:
                try:
                    embed = discord.Embed(
                        description=f"🗑️ Message de {user.mention} supprimé\n**Raison:** {reason}",
                        color=0xFEE75C
                    )
                    await message.channel.send(embed=embed, delete_after=5)
                except:
                    pass
            
            await log_security_event(message.guild, 'delete', user, reason, severity)
        except:
            pass
        return
    
    # Supprimer le message pour toutes les autres actions
    try:
        await message.delete()
    except:
        pass
    
    # === WARN ===
    if action == 'warn':
        user_warnings[user.id].append({
            'guild_id': message.guild.id,
            'reason': reason,
            'timestamp': datetime.now()
        })
        
        user_infractions[user.id]['warns'] += 1
        update_trust_score(user.id, message.guild.id, -5)
        
        # Nettoyer anciens warns
        reset_days = config.get('warn_reset_days', 7)
        cutoff = datetime.now() - timedelta(days=reset_days)
        user_warnings[user.id] = [
            w for w in user_warnings[user.id]
            if w['timestamp'] > cutoff
        ]
        
        warn_count = len([w for w in user_warnings[user.id] if w['guild_id'] == message.guild.id])
        threshold = config.get('warn_threshold', 3)
        
        # Notification DM DÉTAILLÉE
        if config.get('dm_warnings', True):
            try:
                embed = discord.Embed(
                    title="⚠️ Avertissement - Lunera Security",
                    description=f"Vous avez reçu un avertissement sur **{message.guild.name}**",
                    color=0xFEE75C,
                    timestamp=datetime.now()
                )
                embed.add_field(name="📝 Raison", value=reason, inline=False)
                embed.add_field(name="💬 Votre message", value=f"```{message.content[:200]}```", inline=False)
                embed.add_field(name="📊 Avertissements", value=f"**{warn_count}/{threshold}**", inline=True)
                
                trust_score = get_trust_score(user.id, message.guild.id)
                trust_emoji = "🟢" if trust_score >= 70 else "🟡" if trust_score >= 40 else "🔴"
                embed.add_field(name="💯 Score de confiance", value=f"{trust_emoji} {trust_score}/100", inline=True)
                
                if warn_count >= threshold - 1:
                    embed.add_field(
                        name="⚠️ ATTENTION",
                        value=f"Vous êtes à **{warn_count}/{threshold}** warns. Le prochain avertissement entraînera une sanction automatique.",
                        inline=False
                    )
                
                embed.set_footer(text="🌙 Lunera Security - Système de modération automatique")
                await user.send(embed=embed)
                notification_sent = True
            except:
                pass
        
        # Message public temporaire
        try:
            embed = discord.Embed(
                title="⚠️ Avertissement",
                description=f"**{user.mention}** a reçu un avertissement\n\n**Raison:** {reason}\n**Warns:** {warn_count}/{threshold}",
                color=0xFEE75C
            )
            await message.channel.send(embed=embed, delete_after=8)
        except:
            pass
        
        await log_security_event(
            message.guild, 'warn', user, reason, severity,
            {'Warns': f"{warn_count}/{threshold}", 'Message': message.content[:100]}
        )
        
        # Auto-escalade si seuil atteint
        if warn_count >= threshold and config.get('progressive_sanctions', True):
            action = 'mute'
            duration = config.get('mute_duration', 1800)
    
    # === MUTE ===
    if action == 'mute':
        try:
            mute_duration = duration or config.get('mute_duration', 1800)
            timeout_until = datetime.now() + timedelta(seconds=mute_duration)
            
            await user.timeout(timeout_until, reason=f"Lunera Security: {reason}")
            
            user_infractions[user.id]['mutes'] += 1
            update_trust_score(user.id, message.guild.id, -15)
            
            mins = mute_duration // 60
            
            # Notification DM DÉTAILLÉE
            if config.get('dm_sanctions', True):
                try:
                    embed = discord.Embed(
                        title="🔇 Vous avez été mis en timeout - Lunera Security",
                        description=f"Vous ne pouvez plus envoyer de messages sur **{message.guild.name}**",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.add_field(name="⏱️ Durée", value=f"**{mins} minutes**", inline=True)
                    
                    # Calculer l'heure de fin
                    end_time = datetime.now() + timedelta(seconds=mute_duration)
                    embed.add_field(name="🕐 Fin du timeout", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
                    
                    trust_score = get_trust_score(user.id, message.guild.id)
                    trust_emoji = "🟢" if trust_score >= 70 else "🟡" if trust_score >= 40 else "🔴"
                    embed.add_field(name="💯 Score de confiance", value=f"{trust_emoji} {trust_score}/100", inline=True)
                    
                    embed.add_field(
                        name="💡 Que faire maintenant ?",
                        value="• Attendez la fin du timeout\n• Lisez les règles du serveur\n• Évitez de répéter ce comportement",
                        inline=False
                    )
                    
                    embed.set_footer(text="🌙 Lunera Security")
                    await user.send(embed=embed)
                    notification_sent = True
                except:
                    pass
            
            # Message public
            try:
                embed = discord.Embed(
                    title="🔇 Membre mis en timeout",
                    description=f"**{user.mention}** ne peut plus parler pendant **{mins} minutes**\n\n**Raison:** {reason}",
                    color=0xED4245,
                    timestamp=datetime.now()
                )
                embed.set_footer(text="🌙 Lunera Security")
                await message.channel.send(embed=embed, delete_after=10)
            except:
                pass
            
            await log_security_event(
                message.guild, 'mute', user, reason, 'high',
                {'Durée': f"{mins} min", 'Message': message.content[:100]}
            )
        except:
            pass
    
    # === KICK ===
    if action == 'kick':
        try:
            # Notification AVANT le kick
            if config.get('dm_sanctions', True):
                try:
                    embed = discord.Embed(
                        title="👢 Vous avez été expulsé - Lunera Security",
                        description=f"Vous avez été expulsé de **{message.guild.name}**",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.add_field(
                        name="💡 Que faire ?",
                        value="• Vous pouvez rejoindre à nouveau le serveur si vous avez un lien d'invitation\n• Assurez-vous de respecter les règles à l'avenir",
                        inline=False
                    )
                    embed.set_footer(text="🌙 Lunera Security")
                    await user.send(embed=embed)
                except:
                    pass
            
            await user.kick(reason=f"Lunera Security: {reason}")
            
            user_infractions[user.id]['kicks'] += 1
            update_trust_score(user.id, message.guild.id, -30)
            
            await log_security_event(
                message.guild, 'kick', user, reason, 'high',
                {'Message': message.content[:100]}
            )
        except:
            pass
    
    # === BAN ===
    if action == 'ban':
        try:
            # Notification AVANT le ban
            if config.get('dm_sanctions', True):
                try:
                    embed = discord.Embed(
                        title="🔨 Vous avez été banni - Lunera Security",
                        description=f"Vous avez été **définitivement banni** de **{message.guild.name}**",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="📝 Raison", value=reason, inline=False)
                    embed.add_field(
                        name="⚠️ Important",
                        value="Ce bannissement est permanent. Contactez les administrateurs du serveur si vous pensez qu'il s'agit d'une erreur.",
                        inline=False
                    )
                    embed.set_footer(text="🌙 Lunera Security")
                    await user.send(embed=embed)
                except:
                    pass
            
            await user.ban(reason=f"Lunera Security: {reason}", delete_message_days=1)
            
            update_trust_score(user.id, message.guild.id, -100)
            
            await log_security_event(
                message.guild, 'ban', user, reason, 'critical',
                {'Message': message.content[:100]}
            )
        except:
            pass
    
    # === QUARANTINE ===
    if action == 'quarantine':
        quarantine_role_id = config.get('quarantine_role')
        if quarantine_role_id:
            role = message.guild.get_role(quarantine_role_id)
            if role:
                try:
                    await user.add_roles(role, reason=f"Lunera Security: {reason}")
                    
                    # Notification quarantaine
                    if config.get('dm_sanctions', True):
                        try:
                            embed = discord.Embed(
                                title="🔒 Vous avez été mis en quarantaine - Lunera Security",
                                description=f"Votre compte a été placé en quarantaine sur **{message.guild.name}**",
                                color=0xED4245,
                                timestamp=datetime.now()
                            )
                            embed.add_field(name="📝 Raison", value=reason, inline=False)
                            embed.add_field(
                                name="💡 Que faire ?",
                                value="• Contactez un modérateur pour faire lever la quarantaine\n• Prouvez que vous n'êtes pas une menace pour le serveur",
                                inline=False
                            )
                            embed.set_footer(text="🌙 Lunera Security")
                            await user.send(embed=embed)
                        except:
                            pass
                    
                    await log_security_event(
                        message.guild, 'quarantine', user, reason, 'high'
                    )
                except:
                    pass

# ========== FILTRES DE SÉCURITÉ ==========

async def check_spam(message, config):
    """Détection de spam avancée"""
    if not config.get('spam_protection', True):
        return False
    
    user_id = message.author.id
    now = datetime.now()
    
    # Historique de messages
    message_history[user_id].append(now)
    
    # Vérifier fréquence
    interval = config.get('spam_interval', 4)
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
    
    # Vérifier messages dupliqués
    if config.get('spam_duplicate_check', True):
        msg_hash = message_hash(message.content)
        duplicate_messages[user_id].append((msg_hash, now))
        
        # Compter duplicatas récents
        recent_duplicates = [
            h for h, ts in duplicate_messages[user_id]
            if (now - ts).total_seconds() < 30 and h == msg_hash
        ]
        
        if len(recent_duplicates) >= 3:
            await apply_sanction(
                message,
                "Spam de messages identiques",
                'mute',
                300,
                'high'
            )
            return True
    
    return False

async def check_phishing(message, config):
    """Détection de phishing/scam"""
    if not config.get('phishing_protection', True):
        return False
    
    content = message.content.lower()
    
    # Domaines de scam connus
    scam_domains = config.get('known_scam_domains', [])
    for domain in scam_domains:
        if domain in content:
            await apply_sanction(
                message,
                f"🎣 Tentative de phishing détectée: {domain}",
                config.get('phishing_action', 'ban'),
                severity='critical'
            )
            return True
    
    # TLD suspects
    suspicious_tld = config.get('suspicious_tld', [])
    urls = URL_PATTERN.findall(content)
    for url in urls:
        for tld in suspicious_tld:
            if tld in url:
                # Vérifier mots-clés de scam
                scam_keywords = ['free', 'nitro', 'gift', 'steam', 'giveaway', 'prize']
                if any(keyword in content for keyword in scam_keywords):
                    await apply_sanction(
                        message,
                        f"🎣 Lien suspect avec TLD {tld}",
                        'ban',
                        severity='critical'
                    )
                    return True
    
    # Patterns de token grabber
    if config.get('token_protection', True):
        token_patterns = config.get('token_patterns', [])
        for pattern in token_patterns:
            if re.search(pattern, content):
                await apply_sanction(
                    message,
                    "🔑 Token Discord détecté - Protection activée",
                    'ban',
                    severity='critical'
                )
                return True
    
    return False

async def check_words(message, config):
    """Filtre de mots avancé"""
    if not config.get('word_filter', True):
        return False
    
    content = message.content
    content_normalized = normalize_text(content)
    
    banned_words = config.get('banned_words', [])
    
    for word in banned_words:
        word_normalized = normalize_text(word)
        
        # Recherche exacte et normalisée
        if word_normalized in content_normalized or word.lower() in content.lower():
            await apply_sanction(
                message,
                f"Mot interdit détecté: **{word}**",
                config.get('word_filter_action', 'delete'),
                severity='medium'
            )
            return True
    
    return False

async def check_links(message, config):
    """Vérification des liens avancée"""
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
    
    # IPs (souvent malveillant)
    if config.get('block_ip_links', True):
        if IP_PATTERN.search(content):
            await apply_sanction(
                message,
                "Lien IP bloqué (potentiellement dangereux)",
                'delete',
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
    
    # Liens génériques
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

async def check_mentions(message, config):
    """Vérification des mentions"""
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
    
    # Trop de mentions utilisateurs
    max_mentions = config.get('max_mentions', 4)
    if user_mentions > max_mentions:
        await apply_sanction(
            message,
            f"Spam de mentions ({user_mentions} mentions)",
            config.get('mention_action', 'warn'),
            severity='medium'
        )
        return True
    
    # Trop de mentions de rôles
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

async def check_caps_emoji_flood(message, config):
    """Vérification caps, emoji et flood"""
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
    
    # Flood de caractères
    if config.get('flood_protection', True):
        max_repeated = config.get('max_repeated_chars', 10)
        if re.search(r'(.)\1{' + str(max_repeated) + ',}', content):
            await apply_sanction(
                message,
                "Flood de caractères répétés",
                'delete',
                severity='low'
            )
            return True
    
    # Caps abuse
    if config.get('caps_filter', True):
        min_length = config.get('min_caps_length', 8)
        if len(content) >= min_length:
            caps_count = sum(1 for c in content if c.isupper())
            alpha_count = sum(1 for c in content if c.isalpha())
            
            if alpha_count > 0:
                caps_percentage = (caps_count / alpha_count) * 100
                max_caps = config.get('max_caps_percentage', 65)
                
                if caps_percentage > max_caps:
                    await apply_sanction(
                        message,
                        f"Abus de majuscules ({int(caps_percentage)}%)",
                        'delete',
                        severity='low'
                    )
                    return True
    
    # Emoji spam
    if config.get('emoji_filter', True):
        custom_emojis = len(re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', content))
        unicode_emojis = len(re.findall(r'[\U00010000-\U0010ffff]', content))
        total_emojis = custom_emojis + unicode_emojis
        
        max_emojis = config.get('max_emojis', 8)
        if total_emojis > max_emojis:
            await apply_sanction(
                message,
                f"Spam d'emojis ({total_emojis})",
                'delete',
                severity='low'
            )
            return True
    
    return False

async def check_images(message, config):
    """Vérification des images/fichiers"""
    if not config.get('image_protection', True):
        return False
    
    if not message.attachments:
        return False
    
    user_id = message.author.id
    now = datetime.now()
    
    # Vérifier nombre d'images
    if len(message.attachments) > config.get('max_images_per_message', 5):
        await apply_sanction(
            message,
            f"Trop d'images ({len(message.attachments)})",
            'delete',
            severity='medium'
        )
        return True
    
    # Vérifier extensions dangereuses
    suspicious_ext = config.get('suspicious_file_extensions', [])
    for attachment in message.attachments:
        filename = attachment.filename.lower()
        for ext in suspicious_ext:
            if filename.endswith(ext):
                await apply_sanction(
                    message,
                    f"Fichier suspect détecté: {ext}",
                    'delete',
                    severity='critical'
                )
                return True
    
    # Spam d'images
    attachment_history[user_id].append(now)
    recent_images = [ts for ts in attachment_history[user_id] if (now - ts).total_seconds() < 10]
    
    if len(recent_images) >= config.get('image_spam_threshold', 3):
        await apply_sanction(
            message,
            "Spam d'images détecté",
            'mute',
            300,
            severity='medium'
        )
        return True
    
    return False

# ========== ANTI-RAID ==========

async def on_lunera_member_join(member):
    """Gestion des joins - Anti-raid intelligent"""
    guild = member.guild
    config = get_config(guild.id)
    
    if not config.get('raid_protection', True):
        return
    
    now = datetime.now()
    raid_tracker[guild.id].append((member.id, now))
    
    # Nettoyer anciennes entrées
    interval = config.get('raid_interval', 10)
    raid_tracker[guild.id] = [
        (uid, ts) for uid, ts in raid_tracker[guild.id]
        if (now - ts).total_seconds() < interval
    ]
    
    recent_joins = len(raid_tracker[guild.id])
    threshold = config.get('raid_joins', 8)
    
    # Vérifier âge du compte
    account_age = (now - member.created_at.replace(tzinfo=None)).days
    min_age = config.get('raid_account_age', 7)
    
    # Score de suspicion
    is_suspicious = False
    
    # Compte très récent
    if account_age < min_age:
        is_suspicious = True
        update_trust_score(member.id, guild.id, -20)
    
    # Avatar par défaut
    if member.avatar is None:
        update_trust_score(member.id, guild.id, -10)
    
    # Nom suspect (hoisting)
    if config.get('anti_hoisting', True):
        hoist_chars = config.get('hoist_characters', [])
        if any(member.name.startswith(char) for char in hoist_chars):
            is_suspicious = True
            update_trust_score(member.id, guild.id, -15)
    
    # RAID DÉTECTÉ
    if recent_joins >= threshold:
        # Auto-lockdown
        if config.get('raid_auto_lockdown', True):
            locked = 0
            for channel in guild.text_channels:
                try:
                    await channel.set_permissions(
                        guild.default_role,
                        send_messages=False
                    )
                    locked += 1
                except:
                    pass
        
        # Kick compte suspect pendant raid
        if is_suspicious:
            try:
                await member.kick(reason=f"Lunera Security: Raid - Compte de {account_age} jours")
                
                await log_security_event(
                    guild, 'raid', member,
                    f"Kick pendant raid (compte {account_age}j)",
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
                    title="🚨 RAID DÉTECTÉ - LUNERA SECURITY",
                    description=f"**{recent_joins} utilisateurs** ont rejoint en {interval}s !",
                    color=0xED4245,
                    timestamp=datetime.now()
                )
                embed.add_field(name="⚡ Action", value="Lockdown automatique activé", inline=False)
                embed.add_field(name="🛡️ Protection", value="Comptes suspects kick automatique", inline=False)
                embed.add_field(name="🔧 Commandes", value="`/lunera unlockdown` pour débloquer", inline=False)
                embed.set_footer(text="🌙 Lunera Security - Protection maximale")
                
                try:
                    await alert_channel.send(f"{ping}", embed=embed)
                except:
                    pass
    
    # Quarantaine des comptes très suspects
    elif is_suspicious and account_age < 1:
        trust_score = get_trust_score(member.id, guild.id)
        quarantine_threshold = config.get('auto_quarantine_threshold', 30)
        
        if trust_score < quarantine_threshold:
            quarantine_role_id = config.get('quarantine_role')
            if quarantine_role_id:
                role = guild.get_role(quarantine_role_id)
                if role:
                    try:
                        await member.add_roles(role, reason="Lunera Security: Compte très suspect")
                        
                        await log_security_event(
                            guild, 'quarantine', member,
                            f"Auto-quarantaine (score: {trust_score}, âge: {account_age}j)",
                            'high'
                        )
                    except:
                        pass

async def on_lunera_voice_join(member, channel):
    """Protection anti-raid vocal"""
    guild = member.guild
    config = get_config(guild.id)
    
    if not config.get('raid_voice_protection', True):
        return
    
    now = datetime.now()
    voice_raid_tracker[guild.id].append((member.id, now))
    
    # Nettoyer
    voice_raid_tracker[guild.id] = [
        (uid, ts) for uid, ts in voice_raid_tracker[guild.id]
        if (now - ts).total_seconds() < 10
    ]
    
    recent_voice_joins = len(voice_raid_tracker[guild.id])
    max_voice_joins = config.get('raid_max_voice_joins', 5)
    
    if recent_voice_joins >= max_voice_joins:
        # Kick du vocal
        try:
            await member.move_to(None, reason="Lunera Security: Raid vocal détecté")
            
            await log_security_event(
                guild, 'raid', member,
                f"Raid vocal détecté ({recent_voice_joins} joins)",
                'high'
            )
        except:
            pass

# ========== EVENT HANDLERS ==========

async def on_lunera_message(message):
    """Handler principal Lunera Security"""
    if message.author.bot:
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
    
    # Vérifier score de confiance - Quarantaine auto
    if config.get('trust_score_enabled', True):
        trust_score = get_trust_score(message.author.id, message.guild.id)
        threshold = config.get('auto_quarantine_threshold', 30)
        
        if trust_score < threshold:
            quarantine_role_id = config.get('quarantine_role')
            if quarantine_role_id:
                role = message.guild.get_role(quarantine_role_id)
                if role and role not in message.author.roles:
                    try:
                        await message.author.add_roles(role, reason=f"Lunera: Score trop bas ({trust_score})")
                        await log_security_event(
                            message.guild, 'quarantine', message.author,
                            f"Score de confiance critique: {trust_score}/100",
                            'high'
                        )
                    except:
                        pass
    
    # === EXÉCUTER LES FILTRES ===
    filters = [
        check_phishing,      # PRIORITÉ 1: Phishing
        check_images,        # PRIORITÉ 2: Fichiers dangereux
        check_spam,          # PRIORITÉ 3: Spam
        check_words,         # PRIORITÉ 4: Mots interdits
        check_links,         # PRIORITÉ 5: Liens
        check_mentions,      # PRIORITÉ 6: Mentions
        check_caps_emoji_flood,  # PRIORITÉ 7: Abus divers
    ]
    
    for filter_func in filters:
        try:
            if await filter_func(message, config):
                return  # Stop au premier match
        except Exception as e:
            print(f"Erreur Lunera {filter_func.__name__}: {e}")
    
    # Message légitime = augmenter légèrement le score
    if config.get('trust_score_enabled', True):
        update_trust_score(message.author.id, message.guild.id, 0.5)

# ========== COMMANDES SLASH ==========

async def setup_lunera_commands(bot):
    """Configure les commandes Lunera Security"""
    
    @bot.tree.command(name="lunera", description="🌙 Panneau principal Lunera Security")
    async def lunera_panel(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        
        embed = discord.Embed(
            title="🌙 LUNERA SECURITY",
            description="**Système de sécurité et modération avancée**\n\n"
                       "Protégez votre serveur avec une intelligence de pointe et des filtres ultra-performants.",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # Modules actifs
        modules = {
            'spam_protection': '🚫 Anti-spam',
            'raid_protection': '🛡️ Anti-raid',
            'phishing_protection': '🎣 Anti-phishing',
            'word_filter': '🔤 Filtre mots',
            'link_filter': '🔗 Filtre liens',
            'mention_protection': '👥 Anti-mentions',
            'image_protection': '🖼️ Sécurité fichiers',
            'token_protection': '🔑 Protection tokens',
            'behavior_analysis': '🔍 Analyse comportement',
        }
        
        status_list = []
        for key, name in modules.items():
            status = "✅" if config.get(key, True) else "❌"
            status_list.append(f"{status} {name}")
        
        embed.add_field(
            name="📋 Modules de Sécurité",
            value="\n".join(status_list[:5]),
            inline=True
        )
        
        embed.add_field(
            name="⚙️ Modules Avancés",
            value="\n".join(status_list[5:]),
            inline=True
        )
        
        # Niveau de protection
        protection_level = config.get('protection_level', 'medium')
        level_emojis = {
            'low': '🟢',
            'medium': '🟡',
            'high': '🟠',
            'maximum': '🔴'
        }
        
        embed.add_field(
            name="🎯 Niveau de Protection",
            value=f"{level_emojis.get(protection_level)} **{protection_level.upper()}**",
            inline=False
        )
        
        # Statistiques
        total_warns = sum(len([w for w in warns if w['guild_id'] == interaction.guild.id]) 
                         for warns in user_warnings.values())
        
        embed.add_field(name="📊 Warns actifs", value=str(total_warns), inline=True)
        embed.add_field(name="🔒 Quarantaine", value=str(len(suspicious_users.get(interaction.guild.id, set()))), inline=True)
        
        embed.set_footer(text="🌙 Lunera Security v2.0 - Protection de nouvelle génération")
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_config", description="⚙️ Configurer Lunera Security")
    @app_commands.describe(
        niveau="Niveau de protection global",
        logs="Salon pour les logs de sécurité",
        quarantine_role="Rôle de quarantaine"
    )
    @app_commands.choices(niveau=[
        app_commands.Choice(name="🟢 Faible (permissif)", value="low"),
        app_commands.Choice(name="🟡 Moyen (recommandé)", value="medium"),
        app_commands.Choice(name="🟠 Élevé (strict)", value="high"),
        app_commands.Choice(name="🔴 Maximum (très strict)", value="maximum"),
    ])
    async def lunera_configure(
        interaction: discord.Interaction,
        niveau: str = None,
        logs: discord.TextChannel = None,
        quarantine_role: discord.Role = None
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        changes = []
        
        if niveau:
            config['protection_level'] = niveau
            
            # Ajuster les paramètres selon le niveau
            presets = {
                'low': {
                    'spam_messages': 7, 'spam_interval': 5,
                    'max_mentions': 6, 'max_emojis': 12,
                    'warn_threshold': 4
                },
                'medium': {
                    'spam_messages': 5, 'spam_interval': 4,
                    'max_mentions': 4, 'max_emojis': 8,
                    'warn_threshold': 3
                },
                'high': {
                    'spam_messages': 4, 'spam_interval': 3,
                    'max_mentions': 3, 'max_emojis': 5,
                    'warn_threshold': 2
                },
                'maximum': {
                    'spam_messages': 3, 'spam_interval': 2,
                    'max_mentions': 2, 'max_emojis': 3,
                    'warn_threshold': 2,
                    'raid_joins': 5, 'raid_interval': 8
                }
            }
            
            config.update(presets[niveau])
            changes.append(f"🎯 Niveau: **{niveau.upper()}**")
        
        if logs:
            config['log_channel'] = logs.id
            config['alert_channel'] = logs.id
            changes.append(f"📋 Logs: {logs.mention}")
        
        if quarantine_role:
            config['quarantine_role'] = quarantine_role.id
            changes.append(f"🔒 Quarantaine: {quarantine_role.mention}")
        
        if changes:
            embed = discord.Embed(
                title="✅ Lunera Security - Configuration mise à jour",
                description="\n".join(changes),
                color=0x57F287,
                timestamp=datetime.now()
            )
            embed.set_footer(text="🌙 Lunera Security")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucun changement spécifié", ephemeral=True)
    
    @bot.tree.command(name="lunera_toggle", description="🔄 Activer/Désactiver un module")
    @app_commands.describe(
        module="Module à activer/désactiver",
        activer="État du module"
    )
    @app_commands.choices(module=[
        app_commands.Choice(name="🚫 Anti-spam", value="spam_protection"),
        app_commands.Choice(name="🛡️ Anti-raid", value="raid_protection"),
        app_commands.Choice(name="🎣 Anti-phishing", value="phishing_protection"),
        app_commands.Choice(name="🔤 Filtre mots", value="word_filter"),
        app_commands.Choice(name="🔗 Filtre liens", value="link_filter"),
        app_commands.Choice(name="👥 Anti-mentions", value="mention_protection"),
        app_commands.Choice(name="🖼️ Protection fichiers", value="image_protection"),
        app_commands.Choice(name="🔑 Protection tokens", value="token_protection"),
    ])
    async def lunera_toggle(interaction: discord.Interaction, module: str, activer: bool):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        config[module] = activer
        
        status = "✅ activé" if activer else "❌ désactivé"
        
        embed = discord.Embed(
            title="🔄 Module modifié",
            description=f"**{module.replace('_', ' ').title()}** {status}",
            color=0x5865F2 if activer else 0xED4245
        )
        embed.set_footer(text="🌙 Lunera Security")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_trust", description="📊 Voir le score de confiance d'un utilisateur")
    @app_commands.describe(utilisateur="Utilisateur à analyser")
    async def lunera_trust_score(interaction: discord.Interaction, utilisateur: discord.Member):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        trust_score = get_trust_score(utilisateur.id, interaction.guild.id)
        infractions = user_infractions[utilisateur.id]
        
        # Couleur selon score
        if trust_score >= 70:
            color = 0x57F287  # Vert
            status = "🟢 Fiable"
        elif trust_score >= 40:
            color = 0xFEE75C  # Jaune
            status = "🟡 Neutre"
        else:
            color = 0xED4245  # Rouge
            status = "🔴 Suspect"
        
        embed = discord.Embed(
            title=f"📊 Analyse de confiance - {utilisateur.name}",
            color=color,
            timestamp=datetime.now()
        )
        
        embed.set_thumbnail(url=utilisateur.display_avatar.url)
        
        embed.add_field(
            name="💯 Score de Confiance",
            value=f"**{trust_score}/100**\n{status}",
            inline=True
        )
        
        # Âge du compte
        account_age = (datetime.now() - utilisateur.created_at.replace(tzinfo=None)).days
        embed.add_field(
            name="📅 Âge du compte",
            value=f"{account_age} jours",
            inline=True
        )
        
        # Infractions
        guild_warns = len([w for w in user_warnings[utilisateur.id] if w['guild_id'] == interaction.guild.id])
        
        embed.add_field(
            name="⚠️ Infractions",
            value=f"Warns: {guild_warns}\n"
                  f"Mutes: {infractions['mutes']}\n"
                  f"Kicks: {infractions['kicks']}",
            inline=True
        )
        
        # Risque
        if trust_score < 30:
            risk = "🔴 CRITIQUE - Quarantaine recommandée"
        elif trust_score < 50:
            risk = "🟠 ÉLEVÉ - Surveillance recommandée"
        elif trust_score < 70:
            risk = "🟡 MOYEN - Sous surveillance"
        else:
            risk = "🟢 FAIBLE - Utilisateur fiable"
        
        embed.add_field(
            name="🎯 Niveau de Risque",
            value=risk,
            inline=False
        )
        
        embed.set_footer(text="🌙 Lunera Security - Analyse comportementale")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_lockdown", description="🔒 Verrouiller le serveur (anti-raid)")
    async def lunera_lockdown(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        locked = 0
        for channel in interaction.guild.text_channels:
            try:
                await channel.set_permissions(
                    interaction.guild.default_role,
                    send_messages=False
                )
                locked += 1
            except:
                pass
        
        embed = discord.Embed(
            title="🔒 SERVEUR VERROUILLÉ",
            description=f"**{locked} salons** ont été verrouillés avec succès",
            color=0xED4245,
            timestamp=datetime.now()
        )
        embed.add_field(name="🛡️ Protection", value="Raid Protection activée", inline=False)
        embed.add_field(name="🔓 Déverrouillage", value="Utilisez `/lunera unlockdown`", inline=False)
        embed.set_footer(text="🌙 Lunera Security")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        await log_security_event(
            interaction.guild, 'raid', interaction.user,
            f"Lockdown manuel activé ({locked} salons)",
            'critical'
        )
    
    @bot.tree.command(name="lunera_unlockdown", description="🔓 Déverrouiller le serveur")
    async def lunera_unlockdown(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        unlocked = 0
        for channel in interaction.guild.text_channels:
            try:
                await channel.set_permissions(
                    interaction.guild.default_role,
                    send_messages=None
                )
                unlocked += 1
            except:
                pass
        
        embed = discord.Embed(
            title="🔓 SERVEUR DÉVERROUILLÉ",
            description=f"**{unlocked} salons** ont été déverrouillés",
            color=0x57F287,
            timestamp=datetime.now()
        )
        embed.set_footer(text="🌙 Lunera Security")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_stats", description="📈 Statistiques de sécurité")
    async def lunera_stats(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        
        # Compter les warns actifs
        total_warns = sum(
            len([w for w in warns if w['guild_id'] == guild_id])
            for warns in user_warnings.values()
        )
        
        # Compter les infractions
        total_mutes = sum(inf['mutes'] for inf in user_infractions.values())
        total_kicks = sum(inf['kicks'] for inf in user_infractions.values())
        
        embed = discord.Embed(
            title="📈 Statistiques Lunera Security",
            description=f"Statistiques de sécurité pour **{interaction.guild.name}**",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        embed.add_field(name="⚠️ Warns Actifs", value=str(total_warns), inline=True)
        embed.add_field(name="🔇 Mutes", value=str(total_mutes), inline=True)
        embed.add_field(name="👢 Kicks", value=str(total_kicks), inline=True)
        
        # Utilisateurs en quarantaine
        quarantined = len(suspicious_users.get(guild_id, set()))
        embed.add_field(name="🔒 Quarantaine", value=str(quarantined), inline=True)
        
        # Score moyen
        guild_trust_scores = [
            score for key, score in user_trust_scores.items()
            if key.startswith(f"{guild_id}_")
        ]
        
        if guild_trust_scores:
            avg_trust = sum(guild_trust_scores) / len(guild_trust_scores)
            trust_emoji = "🟢" if avg_trust >= 70 else "🟡" if avg_trust >= 50 else "🔴"
            embed.add_field(
                name="📊 Score Confiance Moyen",
                value=f"{trust_emoji} {avg_trust:.1f}/100",
                inline=True
            )
        
        embed.set_footer(text="🌙 Lunera Security - Statistiques en temps réel")
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ========== COMMANDES DE GESTION MANUELLE ==========
    
    @bot.tree.command(name="lunera_warn", description="⚠️ Avertir manuellement un utilisateur")
    @app_commands.describe(
        utilisateur="Utilisateur à avertir",
        raison="Raison de l'avertissement"
    )
    async def lunera_manual_warn(interaction: discord.Interaction, utilisateur: discord.Member, raison: str):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        # Ajouter le warn
        user_warnings[utilisateur.id].append({
            'guild_id': interaction.guild.id,
            'reason': raison,
            'timestamp': datetime.now(),
            'moderator': interaction.user.id
        })
        
        user_infractions[utilisateur.id]['warns'] += 1
        update_trust_score(utilisateur.id, interaction.guild.id, -5)
        
        config = get_config(interaction.guild.id)
        warn_count = len([w for w in user_warnings[utilisateur.id] if w['guild_id'] == interaction.guild.id])
        threshold = config.get('warn_threshold', 3)
        
        # Notifier l'utilisateur
        try:
            embed = discord.Embed(
                title="⚠️ Avertissement - Lunera Security",
                description=f"Vous avez reçu un avertissement sur **{interaction.guild.name}**",
                color=0xFEE75C,
                timestamp=datetime.now()
            )
            embed.add_field(name="📝 Raison", value=raison, inline=False)
            embed.add_field(name="👮 Par", value=interaction.user.mention, inline=True)
            embed.add_field(name="📊 Warns", value=f"{warn_count}/{threshold}", inline=True)
            embed.set_footer(text="🌙 Lunera Security")
            await utilisateur.send(embed=embed)
        except:
            pass
        
        # Log
        await log_security_event(
            interaction.guild, 'warn', utilisateur, raison, 'medium',
            {'Moderator': interaction.user.name, 'Warns': f"{warn_count}/{threshold}"}
        )
        
        # Confirmation
        embed = discord.Embed(
            title="✅ Avertissement donné",
            description=f"{utilisateur.mention} a reçu un avertissement\n\n**Raison:** {raison}\n**Warns:** {warn_count}/{threshold}",
            color=0x57F287
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_unwarn", description="🔓 Retirer un avertissement")
    @app_commands.describe(
        utilisateur="Utilisateur",
        nombre="Nombre de warns à retirer (par défaut: 1)"
    )
    async def lunera_unwarn(interaction: discord.Interaction, utilisateur: discord.Member, nombre: int = 1):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        guild_warns = [w for w in user_warnings[utilisateur.id] if w['guild_id'] == interaction.guild.id]
        
        if not guild_warns:
            await interaction.response.send_message(f"❌ {utilisateur.mention} n'a aucun warn", ephemeral=True)
            return
        
        # Retirer les warns
        removed = 0
        for _ in range(min(nombre, len(guild_warns))):
            for i, w in enumerate(user_warnings[utilisateur.id]):
                if w['guild_id'] == interaction.guild.id:
                    user_warnings[utilisateur.id].pop(i)
                    removed += 1
                    user_infractions[utilisateur.id]['warns'] = max(0, user_infractions[utilisateur.id]['warns'] - 1)
                    update_trust_score(utilisateur.id, interaction.guild.id, +5)
                    break
        
        # Notifier
        try:
            embed = discord.Embed(
                title="✅ Avertissement(s) retiré(s)",
                description=f"**{removed}** avertissement(s) vous ont été retirés sur **{interaction.guild.name}**",
                color=0x57F287
            )
            embed.add_field(name="👮 Par", value=interaction.user.mention, inline=True)
            embed.set_footer(text="🌙 Lunera Security")
            await utilisateur.send(embed=embed)
        except:
            pass
        
        remaining = len([w for w in user_warnings[utilisateur.id] if w['guild_id'] == interaction.guild.id])
        
        embed = discord.Embed(
            title="✅ Warns retirés",
            description=f"{removed} warn(s) retiré(s) pour {utilisateur.mention}\n**Warns restants:** {remaining}",
            color=0x57F287
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_mute", description="🔇 Timeout manuel")
    @app_commands.describe(
        utilisateur="Utilisateur à mute",
        duree="Durée en minutes",
        raison="Raison du timeout"
    )
    async def lunera_manual_mute(interaction: discord.Interaction, utilisateur: discord.Member, duree: int, raison: str):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        try:
            timeout_until = datetime.now() + timedelta(minutes=duree)
            await utilisateur.timeout(timeout_until, reason=f"Lunera Security: {raison} (Par {interaction.user.name})")
            
            user_infractions[utilisateur.id]['mutes'] += 1
            update_trust_score(utilisateur.id, interaction.guild.id, -10)
            
            # Notifier
            try:
                embed = discord.Embed(
                    title="🔇 Timeout - Lunera Security",
                    description=f"Vous avez été mis en timeout sur **{interaction.guild.name}**",
                    color=0xED4245,
                    timestamp=datetime.now()
                )
                embed.add_field(name="📝 Raison", value=raison, inline=False)
                embed.add_field(name="👮 Par", value=interaction.user.mention, inline=True)
                embed.add_field(name="⏱️ Durée", value=f"{duree} minutes", inline=True)
                embed.add_field(name="🕐 Fin", value=f"<t:{int(timeout_until.timestamp())}:R>", inline=True)
                embed.set_footer(text="🌙 Lunera Security")
                await utilisateur.send(embed=embed)
            except:
                pass
            
            # Log
            await log_security_event(
                interaction.guild, 'mute', utilisateur, raison, 'high',
                {'Moderator': interaction.user.name, 'Durée': f"{duree} min"}
            )
            
            embed = discord.Embed(
                title="✅ Timeout appliqué",
                description=f"{utilisateur.mention} a été mis en timeout\n\n**Durée:** {duree} minutes\n**Raison:** {raison}",
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)
    
    @bot.tree.command(name="lunera_unmute", description="🔊 Retirer le timeout")
    @app_commands.describe(utilisateur="Utilisateur à unmute")
    async def lunera_unmute(interaction: discord.Interaction, utilisateur: discord.Member):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        try:
            await utilisateur.timeout(None, reason=f"Timeout retiré par {interaction.user.name}")
            
            update_trust_score(utilisateur.id, interaction.guild.id, +5)
            
            # Notifier
            try:
                embed = discord.Embed(
                    title="🔊 Timeout retiré",
                    description=f"Votre timeout a été levé sur **{interaction.guild.name}**",
                    color=0x57F287
                )
                embed.add_field(name="👮 Par", value=interaction.user.mention, inline=True)
                embed.set_footer(text="🌙 Lunera Security")
                await utilisateur.send(embed=embed)
            except:
                pass
            
            embed = discord.Embed(
                title="✅ Timeout retiré",
                description=f"Le timeout de {utilisateur.mention} a été levé",
                color=0x57F287
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)
    
    @bot.tree.command(name="lunera_reset", description="🔄 Réinitialiser toutes les sanctions d'un utilisateur")
    @app_commands.describe(utilisateur="Utilisateur")
    async def lunera_reset(interaction: discord.Interaction, utilisateur: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée (Admin requis)", ephemeral=True)
            return
        
        # Reset warns
        old_warns = len([w for w in user_warnings[utilisateur.id] if w['guild_id'] == interaction.guild.id])
        user_warnings[utilisateur.id] = [
            w for w in user_warnings[utilisateur.id]
            if w['guild_id'] != interaction.guild.id
        ]
        
        # Reset infractions
        user_infractions[utilisateur.id] = {'warns': 0, 'mutes': 0, 'kicks': 0}
        
        # Reset score de confiance
        key = f"{interaction.guild.id}_{utilisateur.id}"
        user_trust_scores[key] = 100
        
        # Notifier
        try:
            embed = discord.Embed(
                title="🔄 Sanctions réinitialisées",
                description=f"Toutes vos sanctions ont été effacées sur **{interaction.guild.name}**",
                color=0x57F287
            )
            embed.add_field(name="👮 Par", value=interaction.user.mention, inline=True)
            embed.add_field(name="💯 Nouveau score", value="100/100", inline=True)
            embed.set_footer(text="🌙 Lunera Security")
            await utilisateur.send(embed=embed)
        except:
            pass
        
        embed = discord.Embed(
            title="✅ Utilisateur réinitialisé",
            description=f"Toutes les sanctions de {utilisateur.mention} ont été effacées",
            color=0x57F287
        )
        embed.add_field(name="⚠️ Warns supprimés", value=str(old_warns), inline=True)
        embed.add_field(name="💯 Nouveau score", value="100/100", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_set_action", description="⚙️ Configurer l'action d'un filtre")
    @app_commands.describe(
        filtre="Filtre à configurer",
        action="Action à appliquer"
    )
    @app_commands.choices(
        filtre=[
            app_commands.Choice(name="Spam", value="spam_action"),
            app_commands.Choice(name="Mots interdits", value="banned_words_action"),
            app_commands.Choice(name="Liens", value="link_action"),
            app_commands.Choice(name="Caps/Flood", value="caps_action"),
            app_commands.Choice(name="Mentions", value="mention_action"),
        ],
        action=[
            app_commands.Choice(name="Supprimer seulement", value="delete"),
            app_commands.Choice(name="Avertir", value="warn"),
            app_commands.Choice(name="Timeout", value="mute"),
            app_commands.Choice(name="Kick", value="kick"),
        ]
    )
    async def lunera_set_action(interaction: discord.Interaction, filtre: str, action: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        config[filtre] = action
        
        filter_names = {
            'spam_action': '🚫 Anti-spam',
            'banned_words_action': '🔤 Mots interdits',
            'link_action': '🔗 Liens',
            'caps_action': '📢 Caps/Flood',
            'mention_action': '👥 Mentions',
        }
        
        action_names = {
            'delete': '🗑️ Supprimer',
            'warn': '⚠️ Avertir',
            'mute': '🔇 Timeout',
            'kick': '👢 Kick',
        }
        
        embed = discord.Embed(
            title="✅ Action configurée",
            description=f"**Filtre:** {filter_names.get(filtre, filtre)}\n**Nouvelle action:** {action_names.get(action, action)}",
            color=0x57F287
        )
        embed.set_footer(text="🌙 Lunera Security")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    
    @bot.tree.command(name="lunera_actions", description="⚙️ Panneau de configuration des actions")
    async def lunera_actions_panel(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        
        embed = discord.Embed(
            title="⚙️ Configuration des Actions - Lunera Security",
            description="```ansi\n[2;36m╔════════════════════════════════════════╗\n║  PERSONNALISATION DES SANCTIONS     ║\n╚════════════════════════════════════════╝[0m\n```\nConfigurez l'action appliquée pour chaque type de violation",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        
        # Actions actuelles avec emojis stylés
        actions_emoji = {
            'delete': '🗑️ Supprimer',
            'warn': '⚠️ Avertir',
            'mute': '🔇 Timeout',
            'kick': '👢 Expulser',
            'ban': '🔨 Bannir'
        }
        
        filters = {
            'spam_action': ('🚫 Anti-Spam', config.get('spam_action', 'mute')),
            'banned_words_action': ('🔤 Mots Interdits', config.get('banned_words_action', 'warn')),
            'link_action': ('🔗 Liens Non Autorisés', config.get('link_action', 'delete')),
            'caps_action': ('📢 Abus Majuscules', config.get('caps_action', 'delete')),
            'emoji_action': ('😀 Spam Emojis', config.get('emoji_action', 'delete')),
            'mention_action': ('👥 Spam Mentions', config.get('mention_action', 'warn')),
        }
        
        for filter_key, (filter_name, current_action) in filters.items():
            action_display = actions_emoji.get(current_action, current_action)
            embed.add_field(
                name=filter_name,
                value=f"```yaml\nAction: {action_display}\n```",
                inline=True
            )
        
        embed.add_field(
            name="📝 Comment modifier ?",
            value="```fix\nUtilisez /lunera_set_action pour changer une action\n```",
            inline=False
        )
        
        embed.set_footer(text="🌙 Lunera Security • Personnalisation avancée")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_set_action", description="⚙️ Configurer l'action d'un filtre")
    @app_commands.describe(
        filtre="Filtre à configurer",
        action="Action à appliquer"
    )
    @app_commands.choices(
        filtre=[
            app_commands.Choice(name="🚫 Anti-Spam", value="spam_action"),
            app_commands.Choice(name="🔤 Mots interdits", value="banned_words_action"),
            app_commands.Choice(name="🔗 Liens non autorisés", value="link_action"),
            app_commands.Choice(name="📢 Abus majuscules", value="caps_action"),
            app_commands.Choice(name="😀 Spam emojis", value="emoji_action"),
            app_commands.Choice(name="👥 Spam mentions", value="mention_action"),
        ],
        action=[
            app_commands.Choice(name="🗑️ Supprimer seulement", value="delete"),
            app_commands.Choice(name="⚠️ Avertir", value="warn"),
            app_commands.Choice(name="🔇 Timeout", value="mute"),
            app_commands.Choice(name="👢 Expulser", value="kick"),
        ]
    )
    async def lunera_set_action(interaction: discord.Interaction, filtre: str, action: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        config[filtre] = action
        
        filter_names = {
            'spam_action': '🚫 Anti-Spam',
            'banned_words_action': '🔤 Mots interdits',
            'link_action': '🔗 Liens non autorisés',
            'caps_action': '📢 Abus majuscules',
            'emoji_action': '😀 Spam emojis',
            'mention_action': '👥 Spam mentions',
        }
        
        action_names = {
            'delete': '🗑️ Supprimer',
            'warn': '⚠️ Avertir',
            'mute': '🔇 Timeout',
            'kick': '👢 Expulser',
        }
        
        embed = discord.Embed(
            title="✅ Action Configurée",
            description=f"```ansi\n[2;32m╔════════════════════════════════════════╗\n║     CONFIGURATION MISE À JOUR        ║\n╚════════════════════════════════════════╝[0m\n```",
            color=0x57F287,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📋 Filtre",
            value=f"```{filter_names.get(filtre, filtre)}```",
            inline=True
        )
        
        embed.add_field(
            name="⚡ Nouvelle Action",
            value=f"```{action_names.get(action, action)}```",
            inline=True
        )
        
        embed.set_footer(text="🌙 Lunera Security • Les changements sont effectifs immédiatement")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="lunera_set_threshold", description="📊 Configurer les seuils de détection")
    @app_commands.describe(
        parametre="Paramètre à modifier",
        valeur="Nouvelle valeur"
    )
    @app_commands.choices(parametre=[
        app_commands.Choice(name="🚫 Messages spam (nombre)", value="spam_messages"),
        app_commands.Choice(name="⏱️ Intervalle spam (secondes)", value="spam_interval"),
        app_commands.Choice(name="📢 Max majuscules (%)", value="max_caps_percentage"),
        app_commands.Choice(name="😀 Max emojis", value="max_emojis"),
        app_commands.Choice(name="👥 Max mentions", value="max_mentions"),
        app_commands.Choice(name="⚠️ Warns avant sanction", value="warn_threshold"),
        app_commands.Choice(name="🔇 Durée mute (secondes)", value="mute_duration"),
    ])
    async def lunera_set_threshold(interaction: discord.Interaction, parametre: str, valeur: int):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        old_value = config.get(parametre, 0)
        config[parametre] = valeur
        
        param_names = {
            'spam_messages': '🚫 Messages spam',
            'spam_interval': '⏱️ Intervalle spam',
            'max_caps_percentage': '📢 Max majuscules',
            'max_emojis': '😀 Max emojis',
            'max_mentions': '👥 Max mentions',
            'warn_threshold': '⚠️ Seuil warns',
            'mute_duration': '🔇 Durée mute',
        }
        
        embed = discord.Embed(
            title="✅ Seuil Modifié",
            description=f"```ansi\n[2;32m╔════════════════════════════════════════╗\n║       PARAMÈTRE MIS À JOUR           ║\n╚════════════════════════════════════════╝[0m\n```",
            color=0x57F287,
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="📋 Paramètre",
            value=f"```{param_names.get(parametre, parametre)}```",
            inline=False
        )
        
        embed.add_field(
            name="📉 Ancienne valeur",
            value=f"```{old_value}```",
            inline=True
        )
        
        embed.add_field(
            name="📈 Nouvelle valeur",
            value=f"```{valeur}```",
            inline=True
        )
        
        embed.set_footer(text="🌙 Lunera Security • Changement effectif immédiatement")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

print("🌙 ✅ Lunera Security chargé avec succès")
