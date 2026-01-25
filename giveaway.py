# SYSTÈME DE GIVEAWAY ULTRA-COMPLET
# À ajouter au bot principal

import discord
from discord import app_commands
from datetime import datetime, timedelta
import random
import asyncio
from collections import defaultdict

# ========== STOCKAGE ==========
giveaways = {}  # {message_id: données}
giveaway_participants = defaultdict(set)  # {message_id: {user_ids}}
giveaway_weights = defaultdict(dict)  # {message_id: {user_id: weight}}
giveaway_history = []
blocked_giveaway_users = set()

# ========== MODALS ==========

class GiveawayCreateModal(discord.ui.Modal, title="🎁 Créer un Giveaway"):
    prize_input = discord.ui.TextInput(
        label="🏆 Titre du lot",
        placeholder="Ex: Nitro Classic 1 mois",
        required=True,
        max_length=100
    )
    
    description_input = discord.ui.TextInput(
        label="📝 Description",
        style=discord.TextStyle.paragraph,
        placeholder="Décrivez le lot en détail...",
        required=False,
        max_length=500
    )
    
    duration_input = discord.ui.TextInput(
        label="⏱️ Durée (format: 1d 2h 30m ou 2h ou 30m)",
        placeholder="Ex: 1d 12h ou 2h 30m",
        required=True,
        max_length=20
    )
    
    winners_input = discord.ui.TextInput(
        label="👥 Nombre de gagnants",
        placeholder="Ex: 1 ou 5",
        required=True,
        max_length=2
    )
    
    image_input = discord.ui.TextInput(
        label="🖼️ URL de l'image (optionnel)",
        placeholder="https://...",
        required=False,
        max_length=200
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Parser la durée
        duration_str = self.duration_input.value.lower()
        duration_seconds = 0
        
        try:
            # Format: 1d 2h 30m 15s
            import re
            days = re.search(r'(\d+)d', duration_str)
            hours = re.search(r'(\d+)h', duration_str)
            minutes = re.search(r'(\d+)m', duration_str)
            seconds = re.search(r'(\d+)s', duration_str)
            
            if days:
                duration_seconds += int(days.group(1)) * 86400
            if hours:
                duration_seconds += int(hours.group(1)) * 3600
            if minutes:
                duration_seconds += int(minutes.group(1)) * 60
            if seconds:
                duration_seconds += int(seconds.group(1))
            
            if duration_seconds == 0:
                await interaction.followup.send("❌ Format de durée invalide ! Utilisez: `1d 2h 30m` ou `2h` ou `30m`", ephemeral=True)
                return
        except:
            await interaction.followup.send("❌ Erreur de format de durée", ephemeral=True)
            return
        
        # Valider nombre de gagnants
        try:
            winners_count = int(self.winners_input.value)
            if winners_count < 1 or winners_count > 20:
                await interaction.followup.send("❌ Le nombre de gagnants doit être entre 1 et 20", ephemeral=True)
                return
        except:
            await interaction.followup.send("❌ Nombre de gagnants invalide", ephemeral=True)
            return
        
        # Créer la vue de configuration
        view = GiveawayConfigView(
            prize=self.prize_input.value,
            description=self.description_input.value,
            duration=duration_seconds,
            winners=winners_count,
            image=self.image_input.value if self.image_input.value else None,
            creator=interaction.user
        )
        
        embed = discord.Embed(
            title="⚙️ Configuration du Giveaway",
            description="Configurez les paramètres avancés avant de lancer le giveaway.",
            color=0x5865F2
        )
        embed.add_field(name="🏆 Lot", value=self.prize_input.value, inline=False)
        embed.add_field(name="⏱️ Durée", value=format_duration(duration_seconds), inline=True)
        embed.add_field(name="👥 Gagnants", value=str(winners_count), inline=True)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class GiveawayConfigView(discord.ui.View):
    def __init__(self, prize, description, duration, winners, image, creator):
        super().__init__(timeout=300)
        self.prize = prize
        self.description = description
        self.duration = duration
        self.winners = winners
        self.image = image
        self.creator = creator
        
        # Config par défaut
        self.required_role = None
        self.forbidden_role = None
        self.min_account_age = 0
        self.weighted_mode = False
        self.booster_bonus = 1.5
        self.color = 0xF1C40F  # Or
        self.ping_role = None
        self.channel = None
    
    @discord.ui.button(label="✅ Lancer le Giveaway", style=discord.ButtonStyle.success, row=0)
    async def launch_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.channel:
            await interaction.response.send_message("❌ Veuillez d'abord sélectionner un salon avec `/giveaway_setchannel` !\n\n💡 Ou utilisez `/giveaway_quick` pour créer rapidement.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Créer l'embed du giveaway
        end_time = datetime.now() + timedelta(seconds=self.duration)
        
        embed = discord.Embed(
            title=f"🎁 {self.prize}",
            description=self.description if self.description else "Cliquez sur **Participer** pour tenter votre chance !",
            color=self.color,
            timestamp=end_time
        )
        
        embed.add_field(name="🏆 Gagnants", value=f"{self.winners} personne{'s' if self.winners > 1 else ''}", inline=True)
        embed.add_field(name="⏱️ Fin dans", value=format_duration(self.duration), inline=True)
        embed.add_field(name="👥 Participants", value="0", inline=True)
        
        if self.required_role:
            embed.add_field(name="📋 Rôle requis", value=f"<@&{self.required_role}>", inline=False)
        
        if self.min_account_age > 0:
            embed.add_field(name="⏰ Compte minimum", value=f"{self.min_account_age} jours", inline=True)
        
        if self.weighted_mode:
            embed.add_field(name="⚖️ Mode", value="Pondéré (boosters favorisés)", inline=True)
        
        if self.image:
            embed.set_image(url=self.image)
        
        embed.set_footer(text=f"Créé par {self.creator.name} • Se termine à", icon_url=self.creator.display_avatar.url)
        
        view = GiveawayParticipateView()
        
        # Envoyer dans le salon
        if self.ping_role:
            role = interaction.guild.get_role(self.ping_role)
            content = f"{role.mention} **NOUVEAU GIVEAWAY !**" if role else None
        else:
            content = "🎉 **NOUVEAU GIVEAWAY !**"
        
        message = await self.channel.send(content=content, embed=embed, view=view)
        
        # Sauvegarder le giveaway
        giveaways[message.id] = {
            'prize': self.prize,
            'description': self.description,
            'winners': self.winners,
            'end_time': end_time,
            'creator_id': self.creator.id,
            'guild_id': interaction.guild.id,
            'channel_id': self.channel.id,
            'message_id': message.id,
            'required_role': self.required_role,
            'forbidden_role': self.forbidden_role,
            'min_account_age': self.min_account_age,
            'weighted_mode': self.weighted_mode,
            'booster_bonus': self.booster_bonus,
            'active': True,
            'paused': False
        }
        
        # Lancer le countdown
        asyncio.create_task(giveaway_countdown(message.id, self.duration))
        
        await interaction.followup.send(f"✅ Giveaway lancé avec succès dans {self.channel.mention} !\n\n🔗 [Lien direct]({message.jump_url})", ephemeral=True)
        
        # Log
        await log_giveaway_action(interaction.guild, "🎁 Giveaway créé", self.creator, self.prize, message.jump_url)
    
    @discord.ui.button(label="📍 Sélectionner salon", style=discord.ButtonStyle.secondary, row=1)
    async def select_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("💡 Utilisez la commande `/giveaway_setchannel` pour définir le salon !", ephemeral=True)
    
    @discord.ui.button(label="👔 Rôle requis", style=discord.ButtonStyle.secondary, row=2)
    async def select_required_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("💡 Utilisez `/giveaway_setrole` pour définir un rôle requis !", ephemeral=True)
    
    @discord.ui.button(label="🔔 Rôle à ping", style=discord.ButtonStyle.secondary, row=3)
    async def select_ping_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("💡 Utilisez `/giveaway_setping` pour définir le rôle à ping !", ephemeral=True)
    
    @discord.ui.button(label="⚖️ Mode pondéré", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_weighted(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.weighted_mode = not self.weighted_mode
        status = "activé" if self.weighted_mode else "désactivé"
        button.style = discord.ButtonStyle.primary if self.weighted_mode else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"✅ Mode pondéré {status}", ephemeral=True)

class GiveawayParticipateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🎉 Participer", style=discord.ButtonStyle.success, custom_id="giveaway_participate")
    async def participate(self, interaction: discord.Interaction, button: discord.ui.Button):
        message_id = interaction.message.id
        
        if message_id not in giveaways:
            await interaction.response.send_message("❌ Ce giveaway n'existe plus", ephemeral=True)
            return
        
        giveaway = giveaways[message_id]
        
        if not giveaway['active']:
            await interaction.response.send_message("❌ Ce giveaway est terminé", ephemeral=True)
            return
        
        if giveaway['paused']:
            await interaction.response.send_message("⏸️ Ce giveaway est en pause", ephemeral=True)
            return
        
        # Vérifier si déjà participant
        if interaction.user.id in giveaway_participants[message_id]:
            # Retirer la participation
            giveaway_participants[message_id].remove(interaction.user.id)
            if message_id in giveaway_weights and interaction.user.id in giveaway_weights[message_id]:
                del giveaway_weights[message_id][interaction.user.id]
            
            await update_participant_count(interaction.message, message_id)
            await interaction.response.send_message("❌ Vous ne participez plus au giveaway", ephemeral=True)
            return
        
        # Vérifications d'éligibilité
        member = interaction.guild.get_member(interaction.user.id)
        
        # Bot check
        if interaction.user.bot:
            await interaction.response.send_message("❌ Les bots ne peuvent pas participer", ephemeral=True)
            return
        
        # Blacklist
        if interaction.user.id in blocked_giveaway_users:
            await interaction.response.send_message("🚫 Vous êtes bloqué des giveaways", ephemeral=True)
            return
        
        # Rôle requis
        if giveaway['required_role']:
            if not any(r.id == giveaway['required_role'] for r in member.roles):
                required_role = interaction.guild.get_role(giveaway['required_role'])
                await interaction.response.send_message(f"❌ Vous devez avoir le rôle {required_role.mention} pour participer", ephemeral=True)
                return
        
        # Rôle interdit
        if giveaway['forbidden_role']:
            if any(r.id == giveaway['forbidden_role'] for r in member.roles):
                await interaction.response.send_message("❌ Vous ne pouvez pas participer avec ce rôle", ephemeral=True)
                return
        
        # Âge du compte
        if giveaway['min_account_age'] > 0:
            account_age = (datetime.now() - interaction.user.created_at.replace(tzinfo=None)).days
            if account_age < giveaway['min_account_age']:
                await interaction.response.send_message(f"❌ Votre compte doit avoir au moins {giveaway['min_account_age']} jours", ephemeral=True)
                return
        
        # Ajouter le participant
        giveaway_participants[message_id].add(interaction.user.id)
        
        # Calculer le poids si mode pondéré
        weight = 1.0
        if giveaway['weighted_mode']:
            # Bonus booster
            if member.premium_since:
                weight *= giveaway['booster_bonus']
            
            # Bonus ancienneté (max x2)
            if member.joined_at:
                join_age = (datetime.now() - member.joined_at.replace(tzinfo=None)).days
                weight *= min(1 + (join_age / 365), 2.0)
        
        giveaway_weights[message_id][interaction.user.id] = weight
        
        await update_participant_count(interaction.message, message_id)
        
        confirm_embed = discord.Embed(
            title="✅ Participation confirmée !",
            description=f"Vous participez au giveaway **{giveaway['prize']}**",
            color=0x57F287
        )
        confirm_embed.add_field(name="👥 Participants", value=str(len(giveaway_participants[message_id])), inline=True)
        
        if giveaway['weighted_mode']:
            confirm_embed.add_field(name="⚖️ Votre poids", value=f"x{weight:.2f}", inline=True)
        
        confirm_embed.set_footer(text="Bon chance ! 🍀")
        
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

# ========== FONCTIONS UTILITAIRES ==========

def format_duration(seconds):
    """Formate une durée en texte lisible"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}j")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}min")
    if secs > 0 and not days and not hours:
        parts.append(f"{secs}s")
    
    return " ".join(parts) if parts else "0s"

async def update_participant_count(message, message_id):
    """Met à jour le nombre de participants dans l'embed"""
    try:
        embed = message.embeds[0]
        count = len(giveaway_participants[message_id])
        
        # Mettre à jour le champ participants
        for i, field in enumerate(embed.fields):
            if "Participants" in field.name:
                embed.set_field_at(i, name="👥 Participants", value=str(count), inline=True)
                break
        
        await message.edit(embed=embed)
    except:
        pass

async def giveaway_countdown(message_id, duration):
    """Compte à rebours et fin automatique"""
    await asyncio.sleep(duration)
    
    if message_id not in giveaways:
        return
    
    giveaway = giveaways[message_id]
    
    if not giveaway['active']:
        return
    
    # Terminer le giveaway
    await end_giveaway(message_id)

async def end_giveaway(message_id):
    """Termine un giveaway et sélectionne les gagnants"""
    if message_id not in giveaways:
        return
    
    giveaway = giveaways[message_id]
    giveaway['active'] = False
    
    # Récupérer le message
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
    
    # Sélectionner les gagnants
    winners = []
    
    if len(participants) == 0:
        # Aucun participant
        embed = discord.Embed(
            title="🎁 Giveaway terminé",
            description=f"**{giveaway['prize']}**\n\n❌ Aucun participant ! Le giveaway est annulé.",
            color=0xED4245,
            timestamp=datetime.now()
        )
        embed.set_footer(text="Giveaway annulé")
        
        await message.edit(embed=embed, view=None)
        return
    
    elif len(participants) < giveaway['winners']:
        # Pas assez de participants
        winners = participants
    else:
        # Sélection pondérée ou aléatoire
        if giveaway['weighted_mode']:
            weights = [giveaway_weights[message_id].get(p, 1.0) for p in participants]
            winners = random.choices(participants, weights=weights, k=giveaway['winners'])
        else:
            winners = random.sample(participants, giveaway['winners'])
    
    # Créer l'embed de fin
    embed = discord.Embed(
        title="🎉 Giveaway terminé !",
        description=f"**{giveaway['prize']}**",
        color=0x57F287,
        timestamp=datetime.now()
    )
    
    winners_mention = "\n".join([f"🏆 <@{w}>" for w in winners])
    embed.add_field(name=f"{'Gagnant' if len(winners) == 1 else 'Gagnants'}", value=winners_mention, inline=False)
    embed.add_field(name="👥 Participants", value=str(len(participants)), inline=True)
    
    embed.set_footer(text="Félicitations ! 🎉")
    
    await message.edit(embed=embed, view=None)
    
    # Annoncer les gagnants
    winners_text = ", ".join([f"<@{w}>" for w in winners])
    await channel.send(f"🎊 Félicitations {winners_text} ! Vous avez gagné **{giveaway['prize']}** !")
    
    # Envoyer DM aux gagnants
    for winner_id in winners:
        user = guild.get_member(winner_id)
        if user:
            try:
                dm_embed = discord.Embed(
                    title="🎉 Vous avez gagné !",
                    description=f"Félicitations ! Vous avez gagné le giveaway **{giveaway['prize']}** sur **{guild.name}** !",
                    color=0xF1C40F
                )
                dm_embed.add_field(name="📋 Prochaines étapes", value="Contactez un administrateur pour réclamer votre lot.", inline=False)
                dm_embed.set_footer(text=guild.name, icon_url=guild.icon.url if guild.icon else None)
                
                await user.send(embed=dm_embed)
            except:
                pass
    
    # Log
    creator = guild.get_member(giveaway['creator_id'])
    await log_giveaway_action(guild, "🏆 Giveaway terminé", creator, giveaway['prize'], f"{len(winners)} gagnant(s)")
    
    # Historique
    giveaway_history.append({
        'prize': giveaway['prize'],
        'winners': winners,
        'participants': len(participants),
        'end_time': datetime.now(),
        'guild_id': giveaway['guild_id']
    })

async def log_giveaway_action(guild, action, user, prize, details=""):
    """Log les actions giveaway"""
    # À implémenter selon ton système de logs
    pass

# ========== COMMANDES SLASH ==========

@bot.tree.command(name="giveaway_create", description="🎁 Créer un nouveau giveaway")
async def giveaway_create(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Permission refusée ! Vous devez avoir la permission **Gérer le serveur**", ephemeral=True)
        return
    
    modal = GiveawayCreateModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="giveaway_end", description="🏁 Terminer un giveaway immédiatement")
@app_commands.describe(message_id="L'ID du message du giveaway")
async def giveaway_end_cmd(interaction: discord.Interaction, message_id: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Permission refusée", ephemeral=True)
        return
    
    try:
        msg_id = int(message_id)
    except:
        await interaction.response.send_message("❌ ID de message invalide", ephemeral=True)
        return
    
    if msg_id not in giveaways:
        await interaction.response.send_message("❌ Giveaway introuvable", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    await end_giveaway(msg_id)
    await interaction.followup.send("✅ Giveaway terminé !", ephemeral=True)

@bot.tree.command(name="giveaway_reroll", description="🎲 Re-tirer un gagnant")
@app_commands.describe(message_id="L'ID du message du giveaway")
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
        await interaction.response.send_message("❌ Giveaway introuvable", ephemeral=True)
        return
    
    giveaway = giveaways[msg_id]
    participants = list(giveaway_participants[msg_id])
    
    if len(participants) == 0:
        await interaction.response.send_message("❌ Aucun participant", ephemeral=True)
        return
    
    # Nouveau gagnant
    if giveaway['weighted_mode']:
        weights = [giveaway_weights[msg_id].get(p, 1.0) for p in participants]
        new_winner = random.choices(participants, weights=weights, k=1)[0]
    else:
        new_winner = random.choice(participants)
    
    await interaction.response.send_message(f"🎉 Nouveau gagnant : <@{new_winner}> !", ephemeral=False)

@bot.tree.command(name="giveaway_list", description="📋 Liste des giveaways actifs")
async def giveaway_list(interaction: discord.Interaction):
    active_giveaways = [g for g in giveaways.values() if g['active'] and g['guild_id'] == interaction.guild.id]
    
    if not active_giveaways:
        await interaction.response.send_message("✅ Aucun giveaway actif", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📋 Giveaways actifs",
        color=0xF1C40F
    )
    
    for g in active_giveaways[:10]:
        time_left = (g['end_time'] - datetime.now()).total_seconds()
        embed.add_field(
            name=f"🎁 {g['prize']}",
            value=f"Fin dans: {format_duration(int(time_left))}\nGagnants: {g['winners']}\nParticipants: {len(giveaway_participants[g['message_id']])}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
