import discord
from discord.ext import commands
from discord import app_commands
import requests
import json

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Stockage simple des comptes Roblox liés (en mémoire)
# Note: Ces données seront perdues au redémarrage. Pour une solution permanente, utilise une base de données
roblox_links = {}

# Événement de démarrage
@bot.event
async def on_ready():
    print(f'{bot.user} est connecté et prêt !')
    try:
        synced = await bot.tree.sync()
        print(f'Synchronisé {len(synced)} commandes slash')
    except Exception as e:
        print(f'Erreur de synchronisation: {e}')

# ========== COMMANDES DE MODÉRATION ==========

@bot.tree.command(name="kick", description="Expulser un membre du serveur")
@app_commands.describe(membre="Le membre à expulser", raison="La raison de l'expulsion")
async def kick(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission d'expulser des membres !", ephemeral=True)
        return
    
    try:
        await membre.kick(reason=raison)
        await interaction.response.send_message(f"✅ {membre.mention} a été expulsé. Raison : {raison}")
    except:
        await interaction.response.send_message("❌ Impossible d'expulser ce membre.", ephemeral=True)

@bot.tree.command(name="ban", description="Bannir un membre du serveur")
@app_commands.describe(membre="Le membre à bannir", raison="La raison du bannissement")
async def ban(interaction: discord.Interaction, membre: discord.Member, raison: str = "Aucune raison fournie"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de bannir des membres !", ephemeral=True)
        return
    
    try:
        await membre.ban(reason=raison)
        await interaction.response.send_message(f"✅ {membre.mention} a été banni. Raison : {raison}")
    except:
        await interaction.response.send_message("❌ Impossible de bannir ce membre.", ephemeral=True)

@bot.tree.command(name="clear", description="Supprimer des messages")
@app_commands.describe(nombre="Nombre de messages à supprimer (max 100)")
async def clear(interaction: discord.Interaction, nombre: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Tu n'as pas la permission de gérer les messages !", ephemeral=True)
        return
    
    if nombre > 100 or nombre < 1:
        await interaction.response.send_message("❌ Le nombre doit être entre 1 et 100 !", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(f"✅ {len(deleted)} message(s) supprimé(s) !", ephemeral=True)

@bot.tree.command(name="timeout", description="Mettre un membre en timeout")
@app_commands.describe(membre="Le membre à timeout", duree="Durée en minutes", raison="La raison")
async def timeout(interaction: discord.Interaction, membre: discord.Member, duree: int, raison: str = "Aucune raison fournie"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de timeout des membres !", ephemeral=True)
        return
    
    try:
        from datetime import timedelta
        await membre.timeout(timedelta(minutes=duree), reason=raison)
        await interaction.response.send_message(f"✅ {membre.mention} a été mis en timeout pour {duree} minutes. Raison : {raison}")
    except:
        await interaction.response.send_message("❌ Impossible de mettre ce membre en timeout.", ephemeral=True)

# ========== SYSTÈME ROBLOX ==========

@bot.tree.command(name="lier_roblox", description="Lier ton compte Roblox")
@app_commands.describe(nom_utilisateur="Ton nom d'utilisateur Roblox")
async def lier_roblox(interaction: discord.Interaction, nom_utilisateur: str):
    await interaction.response.defer()
    
    try:
        # Vérifier que l'utilisateur Roblox existe
        response = requests.get(f"https://users.roblox.com/v1/users/search?keyword={nom_utilisateur}&limit=1")
        data = response.json()
        
        if not data.get('data'):
            await interaction.followup.send(f"❌ Utilisateur Roblox '{nom_utilisateur}' introuvable !")
            return
        
        roblox_user = data['data'][0]
        roblox_id = roblox_user['id']
        roblox_name = roblox_user['name']
        
        # Stocker le lien
        roblox_links[interaction.user.id] = {
            'roblox_id': roblox_id,
            'roblox_name': roblox_name
        }
        
        embed = discord.Embed(
            title="✅ Compte Roblox lié !",
            description=f"Ton compte Discord est maintenant lié à **{roblox_name}**",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=150&height=150&format=png")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur lors de la liaison : {str(e)}")

@bot.tree.command(name="profil_roblox", description="Voir le profil Roblox d'un membre")
@app_commands.describe(membre="Le membre dont tu veux voir le profil (optionnel)")
async def profil_roblox(interaction: discord.Interaction, membre: discord.Member = None):
    user = membre or interaction.user
    
    if user.id not in roblox_links:
        await interaction.response.send_message(f"❌ {user.mention} n'a pas lié son compte Roblox !", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    roblox_data = roblox_links[user.id]
    roblox_id = roblox_data['roblox_id']
    roblox_name = roblox_data['roblox_name']
    
    try:
        # Récupérer les infos du profil
        response = requests.get(f"https://users.roblox.com/v1/users/{roblox_id}")
        profile = response.json()
        
        embed = discord.Embed(
            title=f"Profil Roblox de {user.display_name}",
            description=profile.get('description', 'Aucune description'),
            color=discord.Color.blue(),
            url=f"https://www.roblox.com/users/{roblox_id}/profile"
        )
        
        embed.add_field(name="Nom d'utilisateur", value=roblox_name, inline=True)
        embed.add_field(name="ID Roblox", value=roblox_id, inline=True)
        embed.add_field(name="Créé le", value=profile.get('created', 'Inconnu')[:10], inline=True)
        
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={roblox_id}&width=150&height=150&format=png")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {str(e)}")

# ========== COMMANDES UTILES ==========

@bot.tree.command(name="userinfo", description="Informations sur un membre")
@app_commands.describe(membre="Le membre (optionnel)")
async def userinfo(interaction: discord.Interaction, membre: discord.Member = None):
    user = membre or interaction.user
    
    embed = discord.Embed(title=f"Infos sur {user.name}", color=user.color)
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="ID", value=user.id, inline=True)
    embed.add_field(name="Pseudo", value=user.display_name, inline=True)
    embed.add_field(name="Compte créé le", value=user.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="A rejoint le", value=user.joined_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Rôles", value=f"{len(user.roles)-1} rôles", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Informations sur le serveur")
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
async def on_member_join(member):
    # Trouve un salon de bienvenue (modifie selon ton serveur)
    channel = discord.utils.get(member.guild.channels, name='bienvenue')
    if channel:
        embed = discord.Embed(
            title=f"Bienvenue {member.name} !",
            description=f"Bienvenue sur **{member.guild.name}** ! Tu es le membre n°{member.guild.member_count} !",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel = discord.utils.get(member.guild.channels, name='logs')
    if channel:
        await channel.send(f"👋 **{member.name}** a quitté le serveur.")

# Lance le bot
import os
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("❌ ERREUR: Token Discord non trouvé dans les variables d'environnement !")
else:
    bot.run(TOKEN)