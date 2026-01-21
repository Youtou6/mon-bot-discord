import discord
from discord.ext import commands
from discord import app_commands
import requests
import json
import os
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Stockage des données (en mémoire)
roblox_links = {}
warnings = {}  # {user_id: [{'raison': str, 'moderateur': str, 'date': str}]}
config_serveur = {}  # {guild_id: {'salon_logs': id, 'salon_bienvenue': id, 'role_mute': id}}

# ========== SYSTÈME DE CONFIGURATION ==========

class ConfigView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=180)
        self.guild_id = guild_id
    
    @discord.ui.button(label="📝 Salon de Logs", style=discord.ButtonStyle.primary)
    async def logs_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Mention le salon pour les logs (ex: #logs) :", 
            ephemeral=True
        )
    
    @discord.ui.button(label="👋 Salon de Bienvenue", style=discord.ButtonStyle.primary)
    async def welcome_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Mention le salon de bienvenue (ex: #bienvenue) :", 
            ephemeral=True
        )
    
    @discord.ui.button(label="🔇 Rôle Mute", style=discord.ButtonStyle.primary)
    async def mute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Mention le rôle mute (ex: @Muted) :", 
            ephemeral=True
        )
    
    @discord.ui.button(label="✅ Afficher Config", style=discord.ButtonStyle.success)
    async def show_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = config_serveur.get(self.guild_id, {})
        
        embed = discord.Embed(
            title="⚙️ Configuration du Serveur",
            color=discord.Color.blue()
        )
        
        logs = f"<#{config.get('salon_logs')}>" if config.get('salon_logs') else "Non configuré"
        welcome = f"<#{config.get('salon_bienvenue')}>" if config.get('salon_bienvenue') else "Non configuré"
        mute = f"<@&{config.get('role_mute')}>" if config.get('role_mute') else "Non configuré"
        
        embed.add_field(name="📝 Salon Logs", value=logs, inline=False)
        embed.add_field(name="👋 Salon Bienvenue", value=welcome, inline=False)
        embed.add_field(name="🔇 Rôle Mute", value=mute, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="config", description="[ADMIN] Panel de configuration du serveur")
async def config_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Seuls les administrateurs peuvent utiliser cette commande !", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="⚙️ Panel de Configuration",
        description="Utilisez les boutons ci-dessous pour configurer le bot sur votre serveur.",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="📝 Salon de Logs", 
        value="Où les actions de modération seront enregistrées", 
        inline=False
    )
    embed.add_field(
        name="👋 Salon de Bienvenue", 
        value="Où les nouveaux membres seront accueillis", 
        inline=False
    )
    embed.add_field(
        name="🔇 Rôle Mute", 
        value="Le rôle à attribuer pour mute un membre", 
        inline=False
    )
    
    view = ConfigView(interaction.guild.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="setlogs", description="[ADMIN] Définir le salon des logs")
@app_commands.describe(salon="Le salon pour les logs")
async def set_logs(interaction: discord.Interaction, salon: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if interaction.guild.id not in config_serveur:
        config_serveur[interaction.guild.id] = {}
    
    config_serveur[interaction.guild.id]['salon_logs'] = salon.id
    await interaction.response.send_message(f"✅ Salon de logs défini sur {salon.mention}", ephemeral=True)

@bot.tree.command(name="setwelcome", description="[ADMIN] Définir le salon de bienvenue")
@app_commands.describe(salon="Le salon de bienvenue")
async def set_welcome(interaction: discord.Interaction, salon: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if interaction.guild.id not in config_serveur:
        config_serveur[interaction.guild.id] = {}
    
    config_serveur[interaction.guild.id]['salon_bienvenue'] = salon.id
    await interaction.response.send_message(f"✅ Salon de bienvenue défini sur {salon.mention}", ephemeral=True)

# ========== SYSTÈME DE LOGS ==========

async def log_action(guild, action_type, moderateur, cible, raison):
    """Enregistre une action de modération dans le salon de logs"""
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

# ========== COMMANDES DE MODÉRATION AVANCÉES ==========

@bot.tree.command(name="warn", description="Avertir un membre")
@app_commands.describe(membre="Le membre à avertir", raison="La raison de l'avertissement")
async def warn(interaction: discord.Interaction, membre: discord.Member, raison: str):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de modérer !", ephemeral=True)
        return
    
    if membre.id not in warnings:
        warnings[membre.id] = []
    
    warning_data = {
        'raison': raison,
        'moderateur': interaction.user.name,
        'date': datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    
    warnings[membre.id].append(warning_data)
    warn_count = len(warnings[membre.id])
    
    embed = discord.Embed(
        title="⚠️ Avertissement",
        description=f"{membre.mention} a reçu un avertissement !",
        color=discord.Color.orange()
    )
    embed.add_field(name="Raison", value=raison, inline=False)
    embed.add_field(name="Total d'avertissements", value=f"{warn_count}", inline=False)
    embed.set_footer(text=f"Modéré par {interaction.user.name}")
    
    await interaction.response.send_message(embed=embed)
    await log_action(interaction.guild, 'warn', interaction.user, membre, raison)
    
    # Actions automatiques selon le nombre de warns
    if warn_count == 3:
        try:
            await membre.timeout(timedelta(hours=1), reason="3 avertissements atteints")
            await interaction.followup.send(f"⏰ {membre.mention} a été timeout 1h (3 warns)")
        except:
            pass
    elif warn_count >= 5:
        try:
            await membre.kick(reason="5 avertissements atteints")
            await interaction.followup.send(f"👢 {membre.mention} a été expulsé (5 warns)")
        except:
            pass

@bot.tree.command(name="warns", description="Voir les avertissements d'un membre")
@app_commands.describe(membre="Le membre (optionnel)")
async def see_warns(interaction: discord.Interaction, membre: discord.Member = None):
    target = membre or interaction.user
    
    if target.id not in warnings or len(warnings[target.id]) == 0:
        await interaction.response.send_message(f"✅ {target.mention} n'a aucun avertissement !", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"⚠️ Avertissements de {target.name}",
        color=discord.Color.orange()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    
    for i, warn in enumerate(warnings[target.id], 1):
        embed.add_field(
            name=f"Warn #{i} - {warn['date']}",
            value=f"**Raison:** {warn['raison']}\n**Par:** {warn['moderateur']}",
            inline=False
        )
    
    embed.set_footer(text=f"Total: {len(warnings[target.id])} avertissement(s)")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="unwarn", description="Retirer un avertissement")
@app_commands.describe(membre="Le membre", numero="Numéro du warn à retirer")
async def unwarn(interaction: discord.Interaction, membre: discord.Member, numero: int):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if membre.id not in warnings or len(warnings[membre.id]) == 0:
        await interaction.response.send_message(f"❌ {membre.mention} n'a aucun avertissement !", ephemeral=True)
        return
    
    if numero < 1 or numero > len(warnings[membre.id]):
        await interaction.response.send_message(f"❌ Numéro invalide ! (1-{len(warnings[membre.id])})", ephemeral=True)
        return
    
    removed_warn = warnings[membre.id].pop(numero - 1)
    
    await interaction.response.send_message(
        f"✅ Avertissement #{numero} retiré de {membre.mention}\n**Raison:** {removed_warn['raison']}"
    )
    await log_action(interaction.guild, 'unwarn', interaction.user, membre, f"Warn #{numero} retiré")

@bot.tree.command(name="clearwarns", description="Effacer tous les avertissements d'un membre")
@app_commands.describe(membre="Le membre")
async def clear_warns(interaction: discord.Interaction, membre: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Seuls les admins peuvent faire ça !", ephemeral=True)
        return
    
    if membre.id in warnings:
        count = len(warnings[membre.id])
        warnings[membre.id] = []
        await interaction.response.send_message(f"✅ {count} avertissement(s) effacé(s) pour {membre.mention}")
    else:
        await interaction.response.send_message(f"✅ {membre.mention} n'avait aucun avertissement", ephemeral=True)

@bot.tree.command(name="kick", description="Expulser un membre")
@app_commands.describe(membre="Le membre à expulser", raison="La raison")
async def kick(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas expulser ce membre !", ephemeral=True)
        return
    
    try:
        await membre.kick(reason=raison)
        await interaction.response.send_message(f"✅ {membre.mention} a été expulsé.\n**Raison:** {raison}")
        await log_action(interaction.guild, 'kick', interaction.user, membre, raison)
    except:
        await interaction.response.send_message("❌ Impossible d'expulser ce membre.", ephemeral=True)

@bot.tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(membre="Le membre à bannir", raison="La raison", supprimer_messages="Supprimer les messages (jours)")
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie", supprimer_messages: int = 0):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas bannir ce membre !", ephemeral=True)
        return
    
    try:
        await membre.ban(reason=raison, delete_message_days=min(supprimer_messages, 7))
        await interaction.response.send_message(f"🔨 {membre.mention} a été banni.\n**Raison:** {raison}")
        await log_action(interaction.guild, 'ban', interaction.user, membre, raison)
    except:
        await interaction.response.send_message("❌ Impossible de bannir ce membre.", ephemeral=True)

@bot.tree.command(name="unban", description="Débannir un utilisateur")
@app_commands.describe(user_id="L'ID de l'utilisateur à débannir")
async def unban(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"✅ {user.mention} a été débanni !")
    except:
        await interaction.response.send_message("❌ Utilisateur introuvable ou non banni.", ephemeral=True)

@bot.tree.command(name="timeout", description="Mettre un membre en timeout")
@app_commands.describe(membre="Le membre", duree="Durée en minutes", raison="La raison")
async def timeout(interaction: discord.Interaction, membre: discord.Member, duree: int, raison: str = "Aucune raison fournie"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if membre.top_role >= interaction.user.top_role:
        await interaction.response.send_message("❌ Tu ne peux pas timeout ce membre !", ephemeral=True)
        return
    
    try:
        await membre.timeout(timedelta(minutes=duree), reason=raison)
        await interaction.response.send_message(f"⏰ {membre.mention} en timeout pour {duree} min.\n**Raison:** {raison}")
        await log_action(interaction.guild, 'timeout', interaction.user, membre, f"{raison} ({duree} min)")
    except:
        await interaction.response.send_message("❌ Erreur.", ephemeral=True)

@bot.tree.command(name="untimeout", description="Retirer le timeout d'un membre")
@app_commands.describe(membre="Le membre")
async def untimeout(interaction: discord.Interaction, membre: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    try:
        await membre.timeout(None)
        await interaction.response.send_message(f"✅ Timeout retiré pour {membre.mention}")
        await log_action(interaction.guild, 'unmute', interaction.user, membre, "Timeout retiré")
    except:
        await interaction.response.send_message("❌ Erreur.", ephemeral=True)

@bot.tree.command(name="clear", description="Supprimer des messages")
@app_commands.describe(nombre="Nombre de messages (1-100)")
async def clear(interaction: discord.Interaction, nombre: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if nombre < 1 or nombre > 100:
        await interaction.response.send_message("❌ Entre 1 et 100 !", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(f"✅ {len(deleted)} message(s) supprimé(s) !", ephemeral=True)

@bot.tree.command(name="lock", description="Verrouiller un salon")
@app_commands.describe(salon="Le salon à verrouiller (optionnel)")
async def lock(interaction: discord.Interaction, salon: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    channel = salon or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message(f"🔒 {channel.mention} verrouillé !")

@bot.tree.command(name="unlock", description="Déverrouiller un salon")
@app_commands.describe(salon="Le salon à déverrouiller (optionnel)")
async def unlock(interaction: discord.Interaction, salon: discord.TextChannel = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    channel = salon or interaction.channel
    await channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message(f"🔓 {channel.mention} déverrouillé !")

@bot.tree.command(name="slowmode", description="Définir le mode lent d'un salon")
@app_commands.describe(secondes="Délai en secondes (0 pour désactiver)")
async def slowmode(interaction: discord.Interaction, secondes: int):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if secondes < 0 or secondes > 21600:
        await interaction.response.send_message("❌ Entre 0 et 21600 secondes !", ephemeral=True)
        return
    
    await interaction.channel.edit(slowmode_delay=secondes)
    
    if secondes == 0:
        await interaction.response.send_message("✅ Mode lent désactivé !")
    else:
        await interaction.response.send_message(f"⏱️ Mode lent: {secondes}s entre chaque message")

# ========== SYSTÈME ROBLOX ==========

@bot.tree.command(name="lier_roblox", description="Lier ton compte Roblox")
@app_commands.describe(nom_utilisateur="Ton nom d'utilisateur Roblox")
async def lier_roblox(interaction: discord.Interaction, nom_utilisateur: str):
    await interaction.response.defer()
    
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/search?keyword={nom_utilisateur}&limit=1")
        data = response.json()
        
        if not data.get('data'):
            await interaction.followup.send(f"❌ Utilisateur '{nom_utilisateur}' introuvable !")
            return
        
        roblox_user = data['data'][0]
        roblox_id = roblox_user['id']
        roblox_name = roblox_user['name']
        
        roblox_links[interaction.user.id] = {
            'roblox_id': roblox_id,
            'roblox_name': roblox_name
        }
        
        embed = discord.Embed(
            title="✅ Compte Roblox lié !",
            description=f"Lié à **{roblox_name}**",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=150&height=150&format=png")
        
        await interaction.followup.send(embed=embed)
    except:
        await interaction.followup.send("❌ Erreur lors de la liaison.")

@bot.tree.command(name="profil_roblox", description="Voir le profil Roblox")
@app_commands.describe(membre="Le membre (optionnel)")
async def profil_roblox(interaction: discord.Interaction, membre: discord.Member = None):
    user = membre or interaction.user
    
    if user.id not in roblox_links:
        await interaction.response.send_message(f"❌ {user.mention} n'a pas lié son compte !", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    roblox_data = roblox_links[user.id]
    roblox_id = roblox_data['roblox_id']
    roblox_name = roblox_data['roblox_name']
    
    try:
        response = requests.get(f"https://users.roblox.com/v1/users/{roblox_id}")
        profile = response.json()
        
        embed = discord.Embed(
            title=f"Profil Roblox de {user.display_name}",
            description=profile.get('description', 'Aucune description'),
            color=discord.Color.blue(),
            url=f"https://www.roblox.com/users/{roblox_id}/profile"
        )
        
        embed.add_field(name="Nom", value=roblox_name, inline=True)
        embed.add_field(name="ID", value=roblox_id, inline=True)
        embed.add_field(name="Créé le", value=profile.get('created', 'Inconnu')[:10], inline=True)
        
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=150&height=150&format=png")
        
        await interaction.followup.send(embed=embed)
    except:
        await interaction.followup.send("❌ Erreur.")

# ========== COMMANDES UTILES ==========

@bot.tree.command(name="userinfo", description="Infos sur un membre")
@app_commands.describe(membre="Le membre (optionnel)")
async def userinfo(interaction: discord.Interaction, membre: discord.Member = None):
    user = membre or interaction.user
    
    embed = discord.Embed(title=f"Infos sur {user.name}", color=user.color)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Pseudo", value=user.display_name, inline=True)
    embed.add_field(name="Créé le", value=user.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="A rejoint le", value=user.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Rôles", value=f"{len(user.roles)-1}", inline=True)
    
    # Ajouter les warns si présents
    if user.id in warnings and len(warnings[user.id]) > 0:
        embed.add_field(name="⚠️ Warns", value=f"{len(warnings[user.id])}", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Infos sur le serveur")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    
    embed = discord.Embed(title=f"Infos sur {guild.name}", color=discord.Color.purple())
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    embed.add_field(name="Propriétaire", value=guild.owner.mention, inline=True)
    embed.add_field(name="Membres", value=guild.member_count, inline=True)
    embed.add_field(name="Créé le", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Salons", value=len(guild.channels), inline=True)
    embed.add_field(name="Rôles", value=len(guild.roles), inline=True)
    
    await interaction.response.send_message(embed=embed)

# ========== ÉVÉNEMENTS ==========

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté et prêt !')
    try:
        synced = await bot.tree.sync()
        print(f'Synchronisé {len(synced)} commandes slash')
    except Exception as e:
        print(f'Erreur: {e}')

@bot.event
async def on_member_join(member):
    config = config_serveur.get(member.guild.id, {})
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
async def on_member_remove(member):
    config = config_serveur.get(member.guild.id, {})
    logs_id = config.get('salon_logs')
    
    if logs_id:
        channel = member.guild.get_channel(logs_id)
        if channel:
            await channel.send(f"👋 **{member.name}** a quitté le serveur.")

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
    print("❌ ERREUR: Token Discord non trouvé !")
else:
    keep_alive()
    bot.run(TOKEN)
