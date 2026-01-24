# SYSTÈME AUTOMOD SIMPLE & PERFORMANT
# Architecture modulaire, aucune dépendance externe

import discord
from discord import app_commands
from datetime import datetime, timedelta
import re
from collections import defaultdict, deque
from typing import Optional

# ========== STOCKAGE ==========
automod_config = {}  # {guild_id: config}
user_warnings = defaultdict(list)  # {user_id: [timestamps]}
user_messages = defaultdict(lambda: deque(maxlen=10))  # {user_id: deque([timestamp, content])}
user_infractions = defaultdict(int)  # {user_id: count}
last_infraction = {}  # {user_id: timestamp}

# ========== CONFIGURATION PAR DÉFAUT ==========
DEFAULT_CONFIG = {
    'enabled': True,
    'log_channel': None,
    'immune_roles': [],
    'immune_channels': [],
    
    # Anti-spam
    'spam_enabled': True,
    'spam_messages': 5,
    'spam_seconds': 5,
    'spam_action': 'mute',
    
    # Anti-flood
    'flood_enabled': True,
    'flood_chars': 15,
    'flood_action': 'delete',
    
    # Anti-caps
    'caps_enabled': True,
    'caps_percent': 70,
    'caps_min_length': 10,
    'caps_action': 'delete',
    
    # Anti-emoji
    'emoji_enabled': True,
    'emoji_max': 10,
    'emoji_action': 'delete',
    
    # Mots interdits
    'badwords_enabled': True,
    'badwords_list': [],
    'badwords_action': 'delete',
    
    # Liens
    'links_enabled': True,
    'links_whitelist': [],
    'links_action': 'delete',
    'discord_invites': True,
    'discord_invites_action': 'delete',
    
    # Anti-mentions
    'mentions_enabled': True,
    'mentions_max': 5,
    'mentions_action': 'warn',
    
    # Anti-raid
    'newaccount_enabled': False,
    'newaccount_days': 7,
    'newaccount_action': 'kick',
    
    # Sanctions
    'sanctions_enabled': True,
    'warn_threshold': 3,
    'mute_duration': 600,  # 10 minutes
    'kick_threshold': 5,
    'ban_threshold': 10,
    'infraction_reset_days': 30,
}

# Mots interdits par défaut (français)
DEFAULT_BADWORDS = [
    'merde', 'connard', 'salope', 'pute', 'fdp', 'ntm', 
    'pd', 'enculé', 'débile', 'con', 'crétin'
]

# Patterns de scam connus
SCAM_PATTERNS = [
    r'(free|gratuit).*(nitro|steam)',
    r'discord\.gift',
    r'(claim|réclame).*(gift|cadeau)',
]

# ========== FONCTIONS DE DÉTECTION ==========

def is_immune(member: discord.Member, channel: discord.TextChannel, guild_id: int) -> bool:
    """Vérifie si un membre/salon est immunisé"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    # Admins toujours immunisés
    if member.guild_permissions.administrator:
        return True
    
    # Rôles immunisés
    for role in member.roles:
        if role.id in config.get('immune_roles', []):
            return True
    
    # Salons immunisés
    if channel.id in config.get('immune_channels', []):
        return True
    
    return False

def check_spam(user_id: int, guild_id: int) -> bool:
    """Détecte le spam de messages"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('spam_enabled', True):
        return False
    
    now = datetime.now()
    messages = user_messages[user_id]
    
    # Ajouter le message actuel
    messages.append(now)
    
    # Compter les messages dans la fenêtre de temps
    window = timedelta(seconds=config.get('spam_seconds', 5))
    recent = sum(1 for ts in messages if now - ts < window)
    
    return recent > config.get('spam_messages', 5)

def check_flood(content: str, guild_id: int) -> bool:
    """Détecte la répétition de caractères"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('flood_enabled', True):
        return False
    
    max_repeat = config.get('flood_chars', 15)
    
    # Chercher des séquences de caractères identiques
    for i in range(len(content) - max_repeat):
        if len(set(content[i:i+max_repeat])) == 1:
            return True
    
    return False

def check_caps(content: str, guild_id: int) -> bool:
    """Détecte l'excès de majuscules"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('caps_enabled', True):
        return False
    
    min_length = config.get('caps_min_length', 10)
    if len(content) < min_length:
        return False
    
    letters = [c for c in content if c.isalpha()]
    if not letters:
        return False
    
    caps = sum(1 for c in letters if c.isupper())
    percent = (caps / len(letters)) * 100
    
    return percent > config.get('caps_percent', 70)

def check_emoji_spam(content: str, guild_id: int) -> bool:
    """Détecte le spam d'emojis"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('emoji_enabled', True):
        return False
    
    # Unicode emojis + custom emojis
    emoji_pattern = r'<a?:\w+:\d+>|[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]'
    emojis = re.findall(emoji_pattern, content)
    
    return len(emojis) > config.get('emoji_max', 10)

def check_badwords(content: str, guild_id: int) -> Optional[str]:
    """Détecte les mots interdits avec anti-contournement"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('badwords_enabled', True):
        return None
    
    badwords = config.get('badwords_list', DEFAULT_BADWORDS)
    
    # Normaliser le texte (enlever espaces, caractères spéciaux)
    normalized = re.sub(r'[^a-zA-Z0-9àâäéèêëïîôùûüÿç]', '', content.lower())
    
    for word in badwords:
        # Version normale
        if word in content.lower():
            return word
        
        # Version avec espaces (c o n n a r d)
        spaced = ' '.join(word)
        if spaced in content.lower():
            return word
        
        # Version normalisée (anti-contournement)
        normalized_word = re.sub(r'[^a-z0-9]', '', word)
        if normalized_word in normalized:
            return word
    
    return None

def check_links(content: str, guild_id: int) -> Optional[str]:
    """Détecte et filtre les liens"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('links_enabled', True):
        return None
    
    # Liens Discord
    if config.get('discord_invites', True):
        discord_pattern = r'(discord\.gg/|discord\.com/invite/|discordapp\.com/invite/)'
        if re.search(discord_pattern, content.lower()):
            return 'discord_invite'
    
    # Scam patterns
    for pattern in SCAM_PATTERNS:
        if re.search(pattern, content.lower()):
            return 'scam'
    
    # Liens raccourcis suspects
    shortened = ['bit.ly', 'tinyurl.com', 'grabify', 'iplogger']
    for short in shortened:
        if short in content.lower():
            return 'suspicious_link'
    
    # Autres liens
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, content)
    
    if urls:
        whitelist = config.get('links_whitelist', [])
        for url in urls:
            # Vérifier whitelist
            if not any(domain in url.lower() for domain in whitelist):
                return 'unauthorized_link'
    
    return None

def check_mentions(message: discord.Message, guild_id: int) -> bool:
    """Détecte le spam de mentions"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('mentions_enabled', True):
        return False
    
    total = len(message.mentions) + len(message.role_mentions)
    
    if message.mention_everyone:
        total += 20  # Gros malus
    
    return total > config.get('mentions_max', 5)

def check_zalgo(content: str) -> bool:
    """Détecte le texte zalgo (caractères Unicode abusifs)"""
    # Compter les diacritiques
    combining = sum(1 for c in content if '\u0300' <= c <= '\u036f')
    
    if len(content) == 0:
        return False
    
    # Plus de 50% de caractères diacritiques = zalgo
    return (combining / len(content)) > 0.5

# ========== SYSTÈME DE SANCTIONS ==========

async def apply_action(message: discord.Message, action: str, reason: str, guild_id: int):
    """Applique une action de modération"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    # Supprimer le message
    if action in ['delete', 'warn', 'mute', 'kick', 'ban']:
        try:
            await message.delete()
        except:
            pass
    
    # Incrémenter infractions
    user_id = message.author.id
    user_infractions[user_id] += 1
    last_infraction[user_id] = datetime.now()
    
    infractions = user_infractions[user_id]
    
    # Sanctions progressives
    if config.get('sanctions_enabled', True):
        # Warn
        if infractions >= config.get('warn_threshold', 3) and action != 'ban':
            try:
                embed = discord.Embed(
                    title="⚠️ Avertissement AutoMod",
                    description=f"**Raison:** {reason}\n**Infractions:** {infractions}",
                    color=0xFEE75C
                )
                await message.author.send(embed=embed)
            except:
                pass
        
        # Mute
        if infractions >= config.get('warn_threshold', 3) and action in ['mute', 'kick', 'ban']:
            try:
                duration = timedelta(seconds=config.get('mute_duration', 600))
                await message.author.timeout(duration, reason=f"AutoMod: {reason}")
                action = 'mute'
            except:
                pass
        
        # Kick
        if infractions >= config.get('kick_threshold', 5) and action == 'kick':
            try:
                await message.author.kick(reason=f"AutoMod: {reason} ({infractions} infractions)")
                action = 'kick'
            except:
                pass
        
        # Ban
        if infractions >= config.get('ban_threshold', 10) or action == 'ban':
            try:
                await message.author.ban(reason=f"AutoMod: {reason}")
                action = 'ban'
            except:
                pass
    
    # Log
    await log_action(message.guild, message.author, message.channel, reason, action, guild_id)

async def log_action(guild: discord.Guild, user: discord.Member, channel: discord.TextChannel, reason: str, action: str, guild_id: int):
    """Log une action AutoMod"""
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    log_channel_id = config.get('log_channel')
    
    if not log_channel_id:
        return
    
    log_channel = guild.get_channel(log_channel_id)
    if not log_channel:
        return
    
    colors = {
        'delete': 0xED4245,
        'warn': 0xFEE75C,
        'mute': 0xF26522,
        'kick': 0xED4245,
        'ban': 0x5D0000,
    }
    
    embed = discord.Embed(
        title=f"🛡️ AutoMod • {action.upper()}",
        color=colors.get(action, 0x5865F2),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Utilisateur", value=f"{user.mention} (`{user.id}`)", inline=True)
    embed.add_field(name="Salon", value=channel.mention, inline=True)
    embed.add_field(name="Action", value=action.upper(), inline=True)
    embed.add_field(name="Raison", value=f"`{reason}`", inline=False)
    
    infractions = user_infractions.get(user.id, 0)
    if infractions > 0:
        embed.add_field(name="Total infractions", value=str(infractions), inline=True)
    
    embed.set_thumbnail(url=user.display_avatar.url)
    
    await log_channel.send(embed=embed)

# ========== ÉVÉNEMENT PRINCIPAL ==========

async def process_automod(message: discord.Message):
    """Traite un message avec l'AutoMod"""
    # Vérifications de base
    if message.author.bot:
        return
    
    if not message.guild:
        return
    
    guild_id = message.guild.id
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    if not config.get('enabled', True):
        return
    
    # Immunité
    if is_immune(message.author, message.channel, guild_id):
        return
    
    content = message.content
    
    # === VÉRIFICATIONS (ordre d'importance) ===
    
    # 1. Scam / Liens suspects (priorité max)
    link_type = check_links(content, guild_id)
    if link_type == 'scam':
        await apply_action(message, 'ban', 'Tentative de scam détectée', guild_id)
        return
    
    # 2. Comptes récents (raid)
    if config.get('newaccount_enabled', False):
        account_age = (datetime.now() - message.author.created_at.replace(tzinfo=None)).days
        if account_age < config.get('newaccount_days', 7):
            action = config.get('newaccount_action', 'kick')
            await apply_action(message, action, f'Compte trop récent ({account_age}j)', guild_id)
            return
    
    # 3. Spam de messages
    if check_spam(message.author.id, guild_id):
        action = config.get('spam_action', 'mute')
        await apply_action(message, action, 'Spam de messages', guild_id)
        return
    
    # 4. Mots interdits
    badword = check_badwords(content, guild_id)
    if badword:
        action = config.get('badwords_action', 'delete')
        await apply_action(message, action, f'Langage inapproprié', guild_id)
        return
    
    # 5. Liens Discord
    if link_type == 'discord_invite':
        action = config.get('discord_invites_action', 'delete')
        await apply_action(message, action, 'Invitation Discord non autorisée', guild_id)
        return
    
    # 6. Autres liens
    if link_type in ['unauthorized_link', 'suspicious_link']:
        action = config.get('links_action', 'delete')
        await apply_action(message, action, 'Lien non autorisé', guild_id)
        return
    
    # 7. Mentions excessives
    if check_mentions(message, guild_id):
        action = config.get('mentions_action', 'warn')
        await apply_action(message, action, 'Trop de mentions', guild_id)
        return
    
    # 8. Zalgo
    if check_zalgo(content):
        await apply_action(message, 'delete', 'Texte corrompu (zalgo)', guild_id)
        return
    
    # 9. Flood
    if check_flood(content, guild_id):
        action = config.get('flood_action', 'delete')
        await apply_action(message, action, 'Répétition excessive', guild_id)
        return
    
    # 10. Caps
    if check_caps(content, guild_id):
        action = config.get('caps_action', 'delete')
        await apply_action(message, action, 'Trop de majuscules', guild_id)
        return
    
    # 11. Emoji spam
    if check_emoji_spam(content, guild_id):
        action = config.get('emoji_action', 'delete')
        await apply_action(message, action, 'Spam d\'emojis', guild_id)
        return

# ========== COMMANDES DE CONFIGURATION ==========

@bot.tree.command(name="automod_setup", description="⚙️ [ADMIN] Configurer l'AutoMod")
@app_commands.describe(log_channel="Salon pour les logs AutoMod")
async def automod_setup(interaction: discord.Interaction, log_channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_CONFIG.copy()
    
    automod_config[guild_id]['log_channel'] = log_channel.id
    automod_config[guild_id]['enabled'] = True
    automod_config[guild_id]['badwords_list'] = DEFAULT_BADWORDS.copy()
    
    embed = discord.Embed(
        title="✅ AutoMod configuré !",
        description=f"L'AutoMod est maintenant actif sur ce serveur.",
        color=0x57F287
    )
    embed.add_field(name="📊 Logs", value=log_channel.mention, inline=False)
    embed.add_field(name="🛡️ Modules actifs", value="Tous (par défaut)", inline=False)
    embed.add_field(name="📝 Configuration", value="Utilisez `/automod_config` pour personnaliser", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="automod_toggle", description="🔄 [ADMIN] Activer/Désactiver l'AutoMod")
async def automod_toggle(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_CONFIG.copy()
    
    automod_config[guild_id]['enabled'] = not automod_config[guild_id]['enabled']
    status = "✅ ACTIVÉ" if automod_config[guild_id]['enabled'] else "❌ DÉSACTIVÉ"
    
    await interaction.response.send_message(f"AutoMod: {status}", ephemeral=True)

@bot.tree.command(name="automod_whitelist", description="➕ [ADMIN] Ajouter un domaine à la whitelist")
@app_commands.describe(domaine="Domaine à autoriser (ex: youtube.com)")
async def automod_whitelist(interaction: discord.Interaction, domaine: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_CONFIG.copy()
    
    if 'links_whitelist' not in automod_config[guild_id]:
        automod_config[guild_id]['links_whitelist'] = []
    
    automod_config[guild_id]['links_whitelist'].append(domaine.lower())
    
    await interaction.response.send_message(f"✅ `{domaine}` ajouté à la whitelist", ephemeral=True)

@bot.tree.command(name="automod_badword", description="🚫 [ADMIN] Ajouter un mot interdit")
@app_commands.describe(mot="Mot à bloquer")
async def automod_badword(interaction: discord.Interaction, mot: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_CONFIG.copy()
    
    if 'badwords_list' not in automod_config[guild_id]:
        automod_config[guild_id]['badwords_list'] = DEFAULT_BADWORDS.copy()
    
    automod_config[guild_id]['badwords_list'].append(mot.lower())
    
    await interaction.response.send_message(f"✅ `{mot}` ajouté à la liste noire", ephemeral=True)

@bot.tree.command(name="automod_immune", description="🛡️ [ADMIN] Immuniser un rôle/salon")
@app_commands.describe(
    role="Rôle à immuniser",
    salon="Salon à immuniser"
)
async def automod_immune(interaction: discord.Interaction, role: discord.Role = None, salon: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    if guild_id not in automod_config:
        automod_config[guild_id] = DEFAULT_CONFIG.copy()
    
    if role:
        if 'immune_roles' not in automod_config[guild_id]:
            automod_config[guild_id]['immune_roles'] = []
        automod_config[guild_id]['immune_roles'].append(role.id)
        await interaction.response.send_message(f"✅ Rôle {role.mention} immunisé", ephemeral=True)
    
    elif salon:
        if 'immune_channels' not in automod_config[guild_id]:
            automod_config[guild_id]['immune_channels'] = []
        automod_config[guild_id]['immune_channels'].append(salon.id)
        await interaction.response.send_message(f"✅ Salon {salon.mention} immunisé", ephemeral=True)
    
    else:
        await interaction.response.send_message("❌ Spécifiez un rôle ou un salon", ephemeral=True)

@bot.tree.command(name="automod_stats", description="📊 Voir les statistiques AutoMod")
async def automod_stats(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    config = automod_config.get(guild_id, DEFAULT_CONFIG)
    
    embed = discord.Embed(
        title="📊 Statistiques AutoMod",
        color=0x5865F2
    )
    
    status = "🟢 Actif" if config.get('enabled') else "🔴 Inactif"
    embed.add_field(name="Statut", value=status, inline=True)
    
    # Compter modules actifs
    modules = ['spam', 'flood', 'caps', 'emoji', 'badwords', 'links', 'mentions']
    active = sum(1 for m in modules if config.get(f'{m}_enabled', True))
    embed.add_field(name="Modules actifs", value=f"{active}/{len(modules)}", inline=True)
    
    # Top infractions
    top_users = sorted(user_infractions.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_users:
        top_text = "\n".join([f"<@{uid}>: {count}" for uid, count in top_users])
        embed.add_field(name="Top infractions", value=top_text, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="automod_reset", description="🔄 [ADMIN] Réinitialiser les infractions d'un user")
@app_commands.describe(utilisateur="Utilisateur à réinitialiser")
async def automod_reset(interaction: discord.Interaction, utilisateur: discord.User):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    if utilisateur.id in user_infractions:
        user_infractions[utilisateur.id] = 0
    
    await interaction.response.send_message(f"✅ Infractions de {utilisateur.mention} réinitialisées", ephemeral=True)
