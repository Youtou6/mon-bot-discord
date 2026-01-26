"""
AutoMod - Système de modération automatique
Simple, rapide, efficace - Zéro dépendance externe
"""

import discord
from discord.ext import commands
from discord import app_commands
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque
import asyncio

# ========== STOCKAGE DES DONNÉES ==========
automod_config = {}  # {guild_id: config}
user_warnings = defaultdict(list)  # {user_id: [{guild_id, reason, timestamp, mod}]}
message_history = defaultdict(lambda: deque(maxlen=10))  # {user_id: [timestamps]}
spam_tracker = defaultdict(lambda: deque(maxlen=5))  # {user_id: [messages]}
raid_tracker = defaultdict(list)  # {guild_id: [(user_id, join_time)]}

# ========== CONFIGURATION PAR DÉFAUT ==========
DEFAULT_CONFIG = {
    # Modules
    'enabled': True,
    'spam_protection': True,
    'word_filter': True,
    'link_filter': True,
    'caps_filter': True,
    'emoji_filter': True,
    'mention_filter': True,
    'raid_protection': True,
    
    # Spam
    'spam_messages': 5,  # messages
    'spam_interval': 3,  # secondes
    'spam_action': 'mute',  # warn/mute/kick
    'spam_mute_duration': 300,  # 5 minutes
    
    # Mots interdits
    'banned_words': [
        'connard', 'salope', 'pute', 'fdp', 'ntm', 'pd', 'enculé',
        'nique', 'niquer', 'ta mère', 'tamere', 'batard', 'fils de pute'
    ],
    'banned_words_action': 'warn',
    
    # Liens
    'allow_links': False,
    'whitelist_domains': ['youtube.com', 'youtu.be', 'twitter.com', 'x.com'],
    'block_discord_invites': True,
    'block_url_shorteners': True,
    'link_action': 'delete',
    
    # Caps
    'max_caps_percentage': 70,
    'min_caps_length': 10,
    'caps_action': 'warn',
    
    # Emoji
    'max_emojis': 10,
    'emoji_action': 'delete',
    
    # Mentions
    'max_mentions': 5,
    'mention_action': 'warn',
    
    # Raid
    'raid_joins': 10,  # utilisateurs
    'raid_interval': 10,  # secondes
    'raid_account_age': 7,  # jours minimum
    'raid_action': 'kick',
    'auto_slowmode': True,
    
    # Sanctions
    'warn_threshold': 3,  # warns avant mute
    'mute_duration': 600,  # 10 minutes
    'warn_reset_days': 7,  # reset après 7 jours
    
    # Exceptions
    'immune_roles': [],  # IDs des rôles exemptés
    'ignored_channels': [],  # IDs des salons exemptés
    'log_channel': None,
    
    # Anti-zalgo
    'zalgo_protection': True,
}

# ========== REGEX & PATTERNS ==========
# Discord invites
DISCORD_INVITE_PATTERN = re.compile(
    r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)[a-zA-Z0-9]+',
    re.IGNORECASE
)

# URL shorteners
URL_SHORTENERS = [
    'bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ow.ly',
    'buff.ly', 'adf.ly', 'bit.do', 'short.io', 'rebrand.ly'
]

# Liens génériques
URL_PATTERN = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
    re.IGNORECASE
)

# Anti-contournement de mots (i n s u l t e)
def normalize_text(text):
    """Normalise le texte pour détecter les contournements"""
    # Retirer espaces, underscores, tirets
    text = re.sub(r'[\s_\-.]', '', text)
    # Retirer caractères répétés (coooool -> cool)
    text = re.compile(r'(.)\1+').sub(r'\1', text)
    return text.lower()

# Détection Zalgo
def is_zalgo(text):
    """Détecte les caractères zalgo (diacritiques excessifs)"""
    zalgo_chars = 0
    for char in text:
        if '\u0300' <= char <= '\u036f':  # Combining diacritical marks
            zalgo_chars += 1
    return zalgo_chars > len(text) * 0.5

# ========== FONCTIONS UTILITAIRES ==========

def get_config(guild_id):
    """Récupère la config d'un serveur"""
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_CONFIG.copy()
    return automod_config[guild_id]

def is_immune(member, config):
    """Vérifie si un membre est exempt"""
    if member.guild_permissions.administrator:
        return True
    if member.guild_permissions.manage_messages:
        return True
    
    for role in member.roles:
        if role.id in config.get('immune_roles', []):
            return True
    return False

def is_ignored_channel(channel_id, config):
    """Vérifie si un salon est ignoré"""
    return channel_id in config.get('ignored_channels', [])

async def log_action(guild, action_type, user, reason, moderator=None, duration=None):
    """Enregistre une action dans les logs"""
    config = get_config(guild.id)
    log_channel_id = config.get('log_channel')
    
    if not log_channel_id:
        return
    
    log_channel = guild.get_channel(log_channel_id)
    if not log_channel:
        return
    
    # Couleurs selon l'action
    colors = {
        'warn': discord.Color.orange(),
        'mute': discord.Color.red(),
        'kick': discord.Color.dark_red(),
        'delete': discord.Color.yellow(),
        'raid': discord.Color.purple(),
    }
    
    embed = discord.Embed(
        title=f"🛡️ AutoMod - {action_type.upper()}",
        color=colors.get(action_type, discord.Color.blue()),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👤 Utilisateur", value=f"{user.mention}\n`{user.id}`", inline=True)
    embed.add_field(name="📝 Raison", value=reason, inline=True)
    
    if duration:
        embed.add_field(name="⏱️ Durée", value=f"{duration}s", inline=True)
    
    if moderator:
        embed.set_footer(text=f"Par {moderator.name}", icon_url=moderator.display_avatar.url)
    else:
        embed.set_footer(text="Action automatique")
    
    try:
        await log_channel.send(embed=embed)
    except:
        pass

async def add_warning(guild, user, reason, moderator=None):
    """Ajoute un avertissement"""
    user_warnings[user.id].append({
        'guild_id': guild.id,
        'reason': reason,
        'timestamp': datetime.now(),
        'moderator': moderator.id if moderator else None
    })
    
    # Nettoyer les anciens warns
    config = get_config(guild.id)
    reset_days = config.get('warn_reset_days', 7)
    cutoff = datetime.now() - timedelta(days=reset_days)
    
    user_warnings[user.id] = [
        w for w in user_warnings[user.id]
        if w['timestamp'] > cutoff and w['guild_id'] == guild.id
    ]
    
    return len([w for w in user_warnings[user.id] if w['guild_id'] == guild.id])

async def apply_sanction(message, reason, action_type='warn', duration=None):
    """Applique une sanction"""
    config = get_config(message.guild.id)
    
    if action_type == 'delete':
        try:
            await message.delete()
            await log_action(message.guild, 'delete', message.author, reason)
        except:
            pass
        return
    
    if action_type == 'warn':
        warn_count = await add_warning(message.guild, message.author, reason)
        
        try:
            embed = discord.Embed(
                title="⚠️ Avertissement",
                description=f"**Raison:** {reason}\n**Warns:** {warn_count}/{config.get('warn_threshold', 3)}",
                color=discord.Color.orange()
            )
            await message.channel.send(f"{message.author.mention}", embed=embed, delete_after=10)
            await message.delete()
        except:
            pass
        
        await log_action(message.guild, 'warn', message.author, reason)
        
        # Auto-mute si seuil atteint
        if warn_count >= config.get('warn_threshold', 3):
            action_type = 'mute'
            duration = config.get('mute_duration', 600)
    
    if action_type == 'mute':
        try:
            mute_duration = duration or config.get('mute_duration', 600)
            timeout_until = datetime.now() + timedelta(seconds=mute_duration)
            
            await message.author.timeout(timeout_until, reason=f"AutoMod: {reason}")
            
            embed = discord.Embed(
                title="🔇 Timeout",
                description=f"**Raison:** {reason}\n**Durée:** {mute_duration}s",
                color=discord.Color.red()
            )
            await message.channel.send(f"{message.author.mention}", embed=embed, delete_after=10)
            await message.delete()
            
            await log_action(message.guild, 'mute', message.author, reason, duration=mute_duration)
        except:
            pass
    
    if action_type == 'kick':
        try:
            await message.author.kick(reason=f"AutoMod: {reason}")
            await log_action(message.guild, 'kick', message.author, reason)
        except:
            pass

# ========== FILTRES ==========

async def check_spam(message, config):
    """Détecte le spam de messages"""
    if not config.get('spam_protection', True):
        return False
    
    user_id = message.author.id
    now = datetime.now()
    
    # Ajouter le timestamp
    message_history[user_id].append(now)
    
    # Compter messages récents
    interval = config.get('spam_interval', 3)
    threshold = config.get('spam_messages', 5)
    
    recent = [ts for ts in message_history[user_id] if (now - ts).total_seconds() < interval]
    
    if len(recent) >= threshold:
        action = config.get('spam_action', 'mute')
        duration = config.get('spam_mute_duration', 300) if action == 'mute' else None
        await apply_sanction(message, f"Spam ({len(recent)} messages en {interval}s)", action, duration)
        
        # Clear history
        message_history[user_id].clear()
        return True
    
    return False

async def check_words(message, config):
    """Filtre les mots interdits"""
    if not config.get('word_filter', True):
        return False
    
    banned_words = config.get('banned_words', [])
    if not banned_words:
        return False
    
    content_normalized = normalize_text(message.content)
    
    for word in banned_words:
        word_normalized = normalize_text(word)
        if word_normalized in content_normalized:
            action = config.get('banned_words_action', 'warn')
            await apply_sanction(message, f"Mot interdit: **{word}**", action)
            return True
    
    return False

async def check_links(message, config):
    """Filtre les liens"""
    if not config.get('link_filter', True):
        return False
    
    content = message.content
    
    # Discord invites
    if config.get('block_discord_invites', True):
        if DISCORD_INVITE_PATTERN.search(content):
            await apply_sanction(message, "Lien d'invitation Discord non autorisé", 'delete')
            return True
    
    # URL shorteners
    if config.get('block_url_shorteners', True):
        for shortener in URL_SHORTENERS:
            if shortener in content.lower():
                await apply_sanction(message, "Lien raccourci non autorisé", 'delete')
                return True
    
    # Tous les liens
    if not config.get('allow_links', False):
        urls = URL_PATTERN.findall(content)
        if urls:
            # Vérifier whitelist
            whitelist = config.get('whitelist_domains', [])
            for url in urls:
                allowed = False
                for domain in whitelist:
                    if domain in url.lower():
                        allowed = True
                        break
                
                if not allowed:
                    action = config.get('link_action', 'delete')
                    await apply_sanction(message, "Lien non autorisé", action)
                    return True
    
    return False

async def check_caps(message, config):
    """Détecte l'abus de majuscules"""
    if not config.get('caps_filter', True):
        return False
    
    content = message.content
    min_length = config.get('min_caps_length', 10)
    
    if len(content) < min_length:
        return False
    
    # Compter majuscules
    caps = sum(1 for c in content if c.isupper())
    total = sum(1 for c in content if c.isalpha())
    
    if total == 0:
        return False
    
    percentage = (caps / total) * 100
    max_percentage = config.get('max_caps_percentage', 70)
    
    if percentage > max_percentage:
        action = config.get('caps_action', 'warn')
        await apply_sanction(message, f"Abus de majuscules ({int(percentage)}%)", action)
        return True
    
    return False

async def check_emojis(message, config):
    """Détecte le spam d'emojis"""
    if not config.get('emoji_filter', True):
        return False
    
    content = message.content
    
    # Emojis Discord custom
    custom_emojis = len(re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', content))
    
    # Emojis Unicode
    unicode_emojis = len(re.findall(r'[\U00010000-\U0010ffff]', content))
    
    total_emojis = custom_emojis + unicode_emojis
    max_emojis = config.get('max_emojis', 10)
    
    if total_emojis > max_emojis:
        action = config.get('emoji_action', 'delete')
        await apply_sanction(message, f"Spam d'emojis ({total_emojis})", action)
        return True
    
    return False

async def check_mentions(message, config):
    """Détecte le spam de mentions"""
    if not config.get('mention_filter', True):
        return False
    
    mentions = len(message.mentions) + len(message.role_mentions)
    max_mentions = config.get('max_mentions', 5)
    
    if mentions > max_mentions:
        action = config.get('mention_action', 'warn')
        await apply_sanction(message, f"Spam de mentions ({mentions})", action)
        return True
    
    return False

async def check_flood(message, config):
    """Détecte la répétition de caractères"""
    content = message.content
    
    # Détecter répétitions (aaaaa, !!!!, etc)
    repeated = re.compile(r'(.)\1{10,}')
    if repeated.search(content):
        await apply_sanction(message, "Flood de caractères", 'delete')
        return True
    
    return False

async def check_zalgo(message, config):
    """Détecte le texte zalgo"""
    if not config.get('zalgo_protection', True):
        return False
    
    if is_zalgo(message.content):
        await apply_sanction(message, "Texte zalgo détecté", 'delete')
        return True
    
    return False

# ========== EVENTS ==========

async def on_automod_message(message):
    """Handler principal pour les messages"""
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
    
    # Vérifier salon ignoré
    if is_ignored_channel(message.channel.id, config):
        return
    
    # Exécuter les filtres dans l'ordre (stop au premier match)
    filters = [
        check_zalgo,
        check_spam,
        check_words,
        check_links,
        check_flood,
        check_caps,
        check_emojis,
        check_mentions,
    ]
    
    for filter_func in filters:
        try:
            if await filter_func(message, config):
                return  # Stop dès qu'un filtre déclenche
        except Exception as e:
            print(f"Erreur AutoMod {filter_func.__name__}: {e}")

async def on_automod_member_join(member):
    """Handler pour les joins (anti-raid)"""
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
    threshold = config.get('raid_joins', 10)
    
    # Vérifier âge du compte
    account_age = (now - member.created_at.replace(tzinfo=None)).days
    min_age = config.get('raid_account_age', 7)
    
    if account_age < min_age and recent_joins >= threshold // 2:
        # Kick comptes récents pendant raid
        try:
            await member.kick(reason=f"AutoMod: Compte trop récent ({account_age}j) pendant raid")
            await log_action(guild, 'kick', member, f"Raid - Compte de {account_age} jours")
        except:
            pass
        return
    
    # Raid détecté
    if recent_joins >= threshold:
        # Activer slowmode auto
        if config.get('auto_slowmode', True):
            for channel in guild.text_channels:
                if channel.slowmode_delay == 0:
                    try:
                        await channel.edit(slowmode_delay=10)
                    except:
                        pass
        
        # Log raid
        log_channel_id = config.get('log_channel')
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(
                    title="🚨 RAID DÉTECTÉ",
                    description=f"**{recent_joins} utilisateurs** ont rejoint en {interval}s",
                    color=discord.Color.purple(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Action", value="Slowmode activé sur tous les salons", inline=False)
                embed.set_footer(text="Utilisez /automod lockdown pour verrouiller le serveur")
                
                try:
                    await log_channel.send(embed=embed)
                except:
                    pass

# ========== COMMANDES ==========

async def setup_commands(bot):
    """Configure les commandes slash"""
    
    @bot.tree.command(name="automod", description="[ADMIN] Configurer l'AutoMod")
    @app_commands.describe(
        module="Module à configurer",
        activer="Activer ou désactiver"
    )
    @app_commands.choices(module=[
        app_commands.Choice(name="Protection spam", value="spam_protection"),
        app_commands.Choice(name="Filtre de mots", value="word_filter"),
        app_commands.Choice(name="Filtre de liens", value="link_filter"),
        app_commands.Choice(name="Filtre majuscules", value="caps_filter"),
        app_commands.Choice(name="Filtre emojis", value="emoji_filter"),
        app_commands.Choice(name="Filtre mentions", value="mention_filter"),
        app_commands.Choice(name="Protection anti-raid", value="raid_protection"),
    ])
    async def automod_toggle(interaction: discord.Interaction, module: str, activer: bool):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        config[module] = activer
        
        status = "✅ activé" if activer else "❌ désactivé"
        module_name = dict(automod_toggle.choices.get('module', []))
        
        await interaction.response.send_message(
            f"**{module}** {status}",
            ephemeral=True
        )
    
    @bot.tree.command(name="automod_logs", description="[ADMIN] Définir le salon de logs")
    @app_commands.describe(salon="Salon pour les logs AutoMod")
    async def automod_logs(interaction: discord.Interaction, salon: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        config['log_channel'] = salon.id
        
        await interaction.response.send_message(
            f"✅ Logs AutoMod configurés dans {salon.mention}",
            ephemeral=True
        )
    
    @bot.tree.command(name="automod_immune", description="[ADMIN] Rendre un rôle immunisé")
    @app_commands.describe(role="Rôle à immuniser")
    async def automod_immune(interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        
        if 'immune_roles' not in config:
            config['immune_roles'] = []
        
        if role.id in config['immune_roles']:
            config['immune_roles'].remove(role.id)
            await interaction.response.send_message(
                f"🔓 {role.mention} n'est plus immunisé",
                ephemeral=True
            )
        else:
            config['immune_roles'].append(role.id)
            await interaction.response.send_message(
                f"🛡️ {role.mention} est maintenant immunisé",
                ephemeral=True
            )
    
    @bot.tree.command(name="automod_ignore", description="[ADMIN] Ignorer un salon")
    @app_commands.describe(salon="Salon à ignorer")
    async def automod_ignore(interaction: discord.Interaction, salon: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        
        if 'ignored_channels' not in config:
            config['ignored_channels'] = []
        
        if salon.id in config['ignored_channels']:
            config['ignored_channels'].remove(salon.id)
            await interaction.response.send_message(
                f"✅ {salon.mention} n'est plus ignoré",
                ephemeral=True
            )
        else:
            config['ignored_channels'].append(salon.id)
            await interaction.response.send_message(
                f"🔇 {salon.mention} est maintenant ignoré",
                ephemeral=True
            )
    
    @bot.tree.command(name="warns", description="Voir les avertissements d'un utilisateur")
    @app_commands.describe(utilisateur="Utilisateur à vérifier")
    async def check_warns(interaction: discord.Interaction, utilisateur: discord.User = None):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        target = utilisateur or interaction.user
        guild_warns = [
            w for w in user_warnings[target.id]
            if w['guild_id'] == interaction.guild.id
        ]
        
        if not guild_warns:
            await interaction.response.send_message(
                f"✅ {target.mention} n'a aucun avertissement",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"⚠️ Avertissements - {target.name}",
            color=discord.Color.orange()
        )
        
        for i, warn in enumerate(guild_warns[-5:], 1):  # 5 derniers
            timestamp = warn['timestamp'].strftime("%d/%m/%Y %H:%M")
            embed.add_field(
                name=f"#{i} - {timestamp}",
                value=warn['reason'],
                inline=False
            )
        
        embed.set_footer(text=f"Total: {len(guild_warns)} warns")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="clearwarns", description="[STAFF] Effacer les warns d'un utilisateur")
    @app_commands.describe(utilisateur="Utilisateur")
    async def clear_warns(interaction: discord.Interaction, utilisateur: discord.User):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        user_warnings[utilisateur.id] = [
            w for w in user_warnings[utilisateur.id]
            if w['guild_id'] != interaction.guild.id
        ]
        
        await interaction.response.send_message(
            f"✅ Warns de {utilisateur.mention} effacés",
            ephemeral=True
        )
    
    @bot.tree.command(name="lockdown", description="[STAFF] Verrouiller le serveur (anti-raid)")
    async def lockdown(interaction: discord.Interaction):
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
            title="🔒 Serveur verrouillé",
            description=f"{locked} salons verrouillés",
            color=discord.Color.red()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_action(interaction.guild, 'raid', interaction.user, "Lockdown activé", interaction.user)
    
    @bot.tree.command(name="unlockdown", description="[STAFF] Déverrouiller le serveur")
    async def unlockdown(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        unlocked = 0
        for channel in interaction.guild.text_channels:
            try:
                await channel.set_permissions(
                    interaction.guild.default_role,
                    send_messages=None  # Reset to default
                )
                unlocked += 1
            except:
                pass
        
        embed = discord.Embed(
            title="🔓 Serveur déverrouillé",
            description=f"{unlocked} salons déverrouillés",
            color=discord.Color.green()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @bot.tree.command(name="automod_status", description="Voir l'état de l'AutoMod")
    async def automod_status(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
            return
        
        config = get_config(interaction.guild.id)
        
        embed = discord.Embed(
            title="🛡️ AutoMod - Statut",
            color=discord.Color.blue()
        )
        
        # Modules
        modules = {
            'spam_protection': '🚫 Anti-spam',
            'word_filter': '🔤 Filtre mots',
            'link_filter': '🔗 Filtre liens',
            'caps_filter': '📢 Anti-caps',
            'emoji_filter': '😀 Anti-emoji spam',
            'mention_filter': '👥 Anti-mention spam',
            'raid_protection': '🛡️ Anti-raid',
        }
        
        status_text = []
        for key, name in modules.items():
            status = "✅" if config.get(key, True) else "❌"
            status_text.append(f"{status} {name}")
        
        embed.add_field(
            name="Modules actifs",
            value="\n".join(status_text),
            inline=False
        )
        
        # Config
        embed.add_field(
            name="⚙️ Paramètres",
            value=f"• Seuil spam: {config.get('spam_messages')} msg/{config.get('spam_interval')}s\n"
                  f"• Max mentions: {config.get('max_mentions')}\n"
                  f"• Max emojis: {config.get('max_emojis')}\n"
                  f"• Warns avant sanction: {config.get('warn_threshold')}",
            inline=False
        )
        
        # Stats
        guild_warns = sum(
            1 for warns in user_warnings.values()
            for w in warns if w['guild_id'] == interaction.guild.id
        )
        
        embed.add_field(
            name="📊 Statistiques",
            value=f"• Warns actifs: {guild_warns}\n"
                  f"• Rôles immunisés: {len(config.get('immune_roles', []))}\n"
                  f"• Salons ignorés: {len(config.get('ignored_channels', []))}",
            inline=False
        )
        
        log_channel = config.get('log_channel')
        if log_channel:
            embed.set_footer(text=f"Logs: #{interaction.guild.get_channel(log_channel).name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== INITIALISATION ==========

print("✅ Module AutoMod chargé")
