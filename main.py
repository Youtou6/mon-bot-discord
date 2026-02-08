import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import re
import io
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio

# ========== IMPORT DES SYSTÈMES ==========
import sys
sys.path.append('.')

# Ajoutez ceci après vos autres imports
from security import SecurityModule

# Configuration du bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Tout en haut du fichier, après les imports
from votre_fichier_lunera import *  # Importer toutes les fonctions Lunera

# Puis ajoutez le contenu du fichier lunera_commands.py que je viens de créer
# ========== CHARGER LE SYSTÈME GIVEAWAY ==========
try:
    with open('giveaway.py', 'r', encoding='utf-8') as f:
        giveaway_code = f.read()
        exec(giveaway_code, globals())
    print("✅ Système Giveaway chargé avec succès !")
except Exception as e:
    print(f"⚠️ Erreur lors du chargement du système Giveaway: {e}")

# ========== CHARGER LE SYSTÈME AUTOMOD ==========
try:
    with open('automod.py', 'r', encoding='utf-8') as f:
        automod_code = f.read()
        exec(automod_code, globals())
    print("✅ Système AutoMod chargé avec succès !")
except Exception as e:
    print(f"⚠️ Erreur lors du chargement du système AutoMod: {e}")

# ========== CHARGER LUNERA SECURITY ==========
try:
    with open('lunera_security.py', 'r', encoding='utf-8') as f:
        lunera_code = f.read()
        exec(lunera_code, globals())
    print("🌙 ✅ Lunera Security chargé !")
except Exception as e:
    print(f"⚠️ Erreur Lunera: {e}")

# ========== STOCKAGE DES DONNÉES ==========
modmail_tickets = {}
modmail_config = {}
modmail_blacklist = set()
modmail_cooldowns = {}
modmail_templates = {}
staff_notes = defaultdict(list)
ticket_counter = defaultdict(int)
ticket_last_activity = {}  # {channel_id: datetime}

# Configuration par défaut
DEFAULT_MODMAIL_CONFIG = {
    'enabled': True,
    'category_id': None,
    'log_channel_id': None,
    'transcript_channel_id': None,
    'staff_role_id': None,  # NOUVEAU: Rôle staff autorisé
    'anonymous_staff': False,
    'cooldown_seconds': 300,
    'max_tickets_per_user': 1,
    'ping_role_id': None,
    'inactivity_timeout': 3600,  # NOUVEAU: 1h d'inactivité avant alerte
    'auto_close_timeout': 86400,  # NOUVEAU: 24h avant fermeture auto
    'categories': {
        '📢': 'Signalement',
        '❓': 'Question',
        '⚠️': 'Réclamation',
        '🚫': 'Appel de sanction',
        '🤝': 'Partenariat',
        '🛠': 'Support technique',
        '📋': 'Autre'
    },
    'auto_responses': {},
    'greeting_message': '✨ Merci de nous contacter !\n\n📝 Un membre de notre équipe vous répondra dans les plus brefs délais.\n⏰ Temps de réponse moyen : **< 2 heures**',
    'closing_message': '🔒 Merci d\'avoir contacté notre équipe !\n\nCe ticket est maintenant fermé. Si vous avez besoin d\'aide supplémentaire, n\'hésitez pas à nous recontacter.',
    'blocked_words': ['spam', 'insulte'],
    'satisfaction_survey': True,
}

# ========== VUES INTERACTIVES ==========

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
            await interaction.response.send_message(f"✅ Catégorie sélectionnée: **{name}**\n\n🔄 Création du ticket...", ephemeral=True)
        return callback

class TicketControlView(discord.ui.View):
    def __init__(self, ticket_channel, user_id, guild_id):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="✍️ Note", style=discord.ButtonStyle.secondary, custom_id="add_note", row=0)
    async def add_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = NoteModal(self.ticket_channel.id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🏷️ Claim", style=discord.ButtonStyle.primary, custom_id="claim_ticket", row=0)
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id in modmail_tickets:
            modmail_tickets[self.user_id]['claimed_by'] = interaction.user.id
            
            embed = discord.Embed(
                title="✅ Ticket réclamé",
                description=f"{interaction.user.mention} a pris en charge ce ticket",
                color=0x5865F2,
                timestamp=datetime.now()
            )
            embed.set_footer(text="Ce ticket est maintenant assigné", icon_url=interaction.user.display_avatar.url)
            await self.ticket_channel.send(embed=embed)
            await interaction.response.send_message("✅ Ticket réclamé !", ephemeral=True)
    
    @discord.ui.button(label="⚡ Urgent", style=discord.ButtonStyle.danger, custom_id="mark_urgent", row=0)
    async def mark_urgent(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id in modmail_tickets:
            modmail_tickets[self.user_id]['priority'] = 'haute'
            modmail_tickets[self.user_id]['tags'].add('urgent')
            
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
                    ping_text = f"{role.mention}\n\n"
            
            embed = discord.Embed(
                title="⚠️ TICKET URGENT",
                description=f"{ping_text}🚨 Ce ticket nécessite une **attention immédiate** !",
                color=0xED4245,
                timestamp=datetime.now()
            )
            embed.add_field(name="📌 Marqué par", value=interaction.user.mention, inline=True)
            embed.add_field(name="🔴 Priorité", value="HAUTE", inline=True)
            embed.set_footer(text="⏰ Veuillez traiter ce ticket en priorité")
            
            await self.ticket_channel.send(embed=embed)
            await interaction.response.send_message("✅ Ticket marqué comme urgent !", ephemeral=True)
    
    @discord.ui.button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, custom_id="save_transcript", row=1)
    async def save_transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        transcript = await generate_transcript(self.ticket_channel, self.user_id)
        
        config = modmail_config.get(self.guild_id, {})
        transcript_channel_id = config.get('transcript_channel_id')
        
        if transcript_channel_id:
            channel = interaction.guild.get_channel(transcript_channel_id)
            if channel:
                user = bot.get_user(self.user_id)
                ticket_data = modmail_tickets.get(self.user_id, {})
                
                embed = discord.Embed(
                    title="💾 Transcript sauvegardé",
                    description="Un transcript de conversation a été généré",
                    color=0x5865F2,
                    timestamp=datetime.now()
                )
                embed.add_field(
                    name="👤 Utilisateur",
                    value=f"{user.mention if user else 'Inconnu'}\n`{self.user_id}`",
                    inline=True
                )
                embed.add_field(
                    name="📂 Catégorie",
                    value=ticket_data.get('category', 'N/A'),
                    inline=True
                )
                embed.add_field(
                    name="📊 Priorité",
                    value=ticket_data.get('priority', 'normale').title(),
                    inline=True
                )
                
                claimed_by = ticket_data.get('claimed_by')
                if claimed_by:
                    claimed_user = interaction.guild.get_member(claimed_by)
                    embed.add_field(
                        name="🏷️ Géré par",
                        value=claimed_user.mention if claimed_user else 'Inconnu',
                        inline=True
                    )
                
                embed.set_footer(text="Sauvegardé manuellement", icon_url=interaction.user.display_avatar.url)
                
                file = discord.File(
                    fp=io.BytesIO(transcript.encode('utf-8')),
                    filename=f"ticket-{self.user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
                )
                
                await channel.send(embed=embed, file=file)
        
        await interaction.followup.send("✅ Transcript sauvegardé avec succès !", ephemeral=True)
    
    @discord.ui.button(label="🔒 Fermer", style=discord.ButtonStyle.danger, custom_id="close_ticket", row=1)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CloseConfirmView(self.ticket_channel, self.user_id, self.guild_id)
        embed = discord.Embed(
            title="⚠️ Confirmation de fermeture",
            description="Êtes-vous sûr de vouloir fermer ce ticket ?\n\n"
                       "• Le transcript sera sauvegardé automatiquement\n"
                       "• L'utilisateur sera notifié\n"
                       "• Le salon sera supprimé définitivement",
            color=0xFEE75C
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class CloseConfirmView(discord.ui.View):
    def __init__(self, ticket_channel, user_id, guild_id):
        super().__init__(timeout=30)
        self.ticket_channel = ticket_channel
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="✅ Confirmer", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # Sauvegarder le transcript
        transcript = await generate_transcript(self.ticket_channel, self.user_id)
        
        config = modmail_config.get(self.guild_id, {})
        transcript_channel_id = config.get('transcript_channel_id')
        
        if transcript_channel_id:
            channel = interaction.guild.get_channel(transcript_channel_id)
            if channel:
                user = bot.get_user(self.user_id)
                ticket_data = modmail_tickets.get(self.user_id, {})
                
                embed = discord.Embed(
                    title="🔒 Ticket fermé",
                    description="Le ticket a été fermé avec succès",
                    color=0xED4245,
                    timestamp=datetime.now()
                )
                embed.add_field(
                    name="👤 Utilisateur",
                    value=f"{user.mention if user else 'Inconnu'}\n`{self.user_id}`",
                    inline=True
                )
                embed.add_field(
                    name="👮 Fermé par",
                    value=interaction.user.mention,
                    inline=True
                )
                embed.add_field(
                    name="📂 Catégorie",
                    value=ticket_data.get('category', 'N/A'),
                    inline=True
                )
                
                created = ticket_data.get('created_at', datetime.now())
                duration = datetime.now() - created
                hours = int(duration.total_seconds() // 3600)
                minutes = int((duration.total_seconds() % 3600) // 60)
                
                embed.add_field(
                    name="⏱️ Durée",
                    value=f"{hours}h {minutes}min" if hours > 0 else f"{minutes}min",
                    inline=True
                )
                
                msg_count = len(ticket_data.get('messages', []))
                embed.add_field(
                    name="💬 Messages",
                    value=str(msg_count),
                    inline=True
                )
                
                claimed_by = ticket_data.get('claimed_by')
                if claimed_by:
                    claimed_user = interaction.guild.get_member(claimed_by)
                    embed.add_field(
                        name="🏷️ Géré par",
                        value=claimed_user.mention if claimed_user else 'Inconnu',
                        inline=True
                    )
                
                embed.set_footer(text=f"Ticket #{ticket_counter.get(self.guild_id, 0)}")
                
                file = discord.File(
                    fp=io.BytesIO(transcript.encode('utf-8')),
                    filename=f"ticket-{self.user_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
                )
                
                await channel.send(embed=embed, file=file)
        
        # Notifier l'utilisateur
        user = bot.get_user(self.user_id)
        if user:
            try:
                closing_msg = config.get('closing_message', DEFAULT_MODMAIL_CONFIG['closing_message'])
                
                embed = discord.Embed(
                    title="🔒 Votre ticket a été fermé",
                    description=closing_msg,
                    color=0x5865F2
                )
                embed.add_field(
                    name="👮 Fermé par",
                    value=interaction.user.name,
                    inline=True
                )
                embed.add_field(
                    name="🏢 Serveur",
                    value=interaction.guild.name,
                    inline=True
                )
                embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
                embed.set_footer(text=f"Fermé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
                
                if config.get('satisfaction_survey', True):
                    view = SatisfactionView(self.user_id, self.guild_id)
                    await user.send(embed=embed, view=view)
                else:
                    await user.send(embed=embed)
            except Exception as e:
                print(f"Erreur notification utilisateur: {e}")
        
        # Nettoyer
        if self.user_id in modmail_tickets:
            del modmail_tickets[self.user_id]
        if self.ticket_channel.id in ticket_last_activity:
            del ticket_last_activity[self.ticket_channel.id]
        
        # Supprimer le salon
        try:
            await self.ticket_channel.delete(reason=f"Ticket fermé par {interaction.user.name}")
        except:
            pass
        
        await interaction.followup.send("✅ Ticket fermé et supprimé avec succès", ephemeral=True)
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Fermeture annulée", ephemeral=True)
        self.stop()

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

class SatisfactionCommentModal(discord.ui.Modal, title="💬 Votre avis"):
    def __init__(self, rating, user_id, guild_id):
        super().__init__()
        self.rating = rating
        self.user_id = user_id
        self.guild_id = guild_id
    
    comment = discord.ui.TextInput(
        label="Commentaire (optionnel)",
        style=discord.TextStyle.paragraph,
        placeholder="Dites-nous ce que vous avez pensé de notre support...",
        required=False,
        max_length=500
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        config = modmail_config.get(self.guild_id, {})
        log_channel_id = config.get('log_channel_id')
        
        if log_channel_id:
            guild = bot.get_guild(self.guild_id)
            if guild:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    # Couleur selon note
                    colors = {
                        1: 0xED4245,
                        2: 0xF26522,
                        3: 0xFEE75C,
                        4: 0x57F287,
                        5: 0x00D166
                    }
                    
                    embed = discord.Embed(
                        title="⭐ Évaluation du support",
                        description=f"**Note:** {'⭐' * self.rating} **({self.rating}/5)**",
                        color=colors.get(self.rating, 0xFEE75C),
                        timestamp=datetime.now()
                    )
                    embed.add_field(
                        name="👤 Utilisateur",
                        value=f"<@{self.user_id}>",
                        inline=True
                    )
                    
                    if self.comment.value:
                        embed.add_field(
                            name="💬 Commentaire",
                            value=f"```{self.comment.value}```",
                            inline=False
                        )
                    
                    embed.set_footer(text=f"Évaluation • {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
                    
                    await channel.send(embed=embed)
        
        reactions = {
            1: "😢",
            2: "😕",
            3: "😐",
            4: "😊",
            5: "😍"
        }
        
        embed = discord.Embed(
            title=f"{reactions.get(self.rating, '⭐')} Merci pour votre retour !",
            description=f"Vous avez attribué **{self.rating}/5 étoiles**\n\n"
                       f"{'⭐' * self.rating}",
            color=0x57F287
        )
        
        if self.comment.value:
            embed.add_field(
                name="💬 Votre commentaire",
                value=f"*\"{self.comment.value}\"*",
                inline=False
            )
        
        embed.set_footer(text="Votre avis nous aide à améliorer notre service")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class NoteModal(discord.ui.Modal, title="📝 Note interne"):
    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id
    
    note_input = discord.ui.TextInput(
        label="Note (invisible pour l'utilisateur)",
        style=discord.TextStyle.paragraph,
        placeholder="Ajoutez une note interne à ce ticket...",
        required=True,
        max_length=1000
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        staff_notes[self.channel_id].append({
            'author': interaction.user.name,
            'note': self.note_input.value,
            'timestamp': datetime.now()
        })
        
        embed = discord.Embed(
            title="📝 Note interne ajoutée",
            description=self.note_input.value,
            color=0xFEE75C,
            timestamp=datetime.now()
        )
        embed.set_author(
            name=interaction.user.name,
            icon_url=interaction.user.display_avatar.url
        )
        embed.set_footer(text="🔒 Cette note est invisible pour l'utilisateur")
        
        await interaction.response.send_message(embed=embed)

# ========== FONCTIONS UTILITAIRES ==========

async def generate_transcript(channel, user_id):
    """Génère un transcript du ticket"""
    lines = []
    lines.append("="*70)
    lines.append(f"  TRANSCRIPT DU TICKET MODMAIL")
    lines.append("="*70)
    lines.append(f"Généré le: {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}")
    lines.append(f"Utilisateur: {user_id}")
    
    ticket_data = modmail_tickets.get(user_id, {})
    lines.append(f"Catégorie: {ticket_data.get('category', 'N/A')}")
    lines.append(f"Priorité: {ticket_data.get('priority', 'normale')}")
    
    if ticket_data.get('claimed_by'):
        lines.append(f"Assigné à: {ticket_data['claimed_by']}")
    
    lines.append("="*70)
    lines.append("")
    lines.append("--- HISTORIQUE DES MESSAGES ---")
    lines.append("")
    
    # Messages
    async for message in channel.history(limit=None, oldest_first=True):
        if message.author.bot and not message.embeds:
            continue
        
        timestamp = message.created_at.strftime("%d/%m/%Y %H:%M:%S")
        
        if message.embeds and message.embeds[0].title == "📝 Note interne ajoutée":
            lines.append(f"[{timestamp}] [NOTE STAFF] {message.embeds[0].author.name}:")
            lines.append(f"  > {message.embeds[0].description}")
            lines.append("")
        elif message.content:
            lines.append(f"[{timestamp}] {message.author.name}:")
            lines.append(f"  {message.content}")
            lines.append("")
        elif message.embeds:
            embed = message.embeds[0]
            if embed.description:
                author_name = embed.author.name if embed.author else message.author.name
                lines.append(f"[{timestamp}] {author_name}:")
                lines.append(f"  {embed.description}")
                lines.append("")
    
    # Notes internes
    if channel.id in staff_notes and staff_notes[channel.id]:
        lines.append("")
        lines.append("="*70)
        lines.append("--- NOTES INTERNES DU STAFF ---")
        lines.append("="*70)
        lines.append("")
        for note in staff_notes[channel.id]:
            ts = note['timestamp'].strftime("%d/%m/%Y %H:%M:%S")
            lines.append(f"[{ts}] {note['author']}:")
            lines.append(f"  {note['note']}")
            lines.append("")
    
    lines.append("="*70)
    lines.append("FIN DU TRANSCRIPT")
    lines.append("="*70)
    
    return "\n".join(lines)

def check_cooldown(user_id):
    """Vérifie si l'utilisateur est en cooldown"""
    if user_id in modmail_cooldowns:
        time_left = (modmail_cooldowns[user_id] - datetime.now()).total_seconds()
        if time_left > 0:
            return int(time_left)
    return 0

def is_blacklisted(user_id):
    """Vérifie si l'utilisateur est blacklisté"""
    return user_id in modmail_blacklist

def check_bad_words(content, guild_id):
    """Vérifie les mots interdits"""
    config = modmail_config.get(guild_id, {})
    blocked_words = config.get('blocked_words', [])
    
    content_lower = content.lower()
    for word in blocked_words:
        if word in content_lower:
            return True
    return False

def is_staff(member, guild_id):
    """Vérifie si un membre fait partie du staff"""
    if member.guild_permissions.administrator:
        return True
    if member.guild_permissions.manage_messages:
        return True
    
    config = modmail_config.get(guild_id, {})
    staff_role_id = config.get('staff_role_id')
    
    if staff_role_id:
        return any(role.id == staff_role_id for role in member.roles)
    
    return False

# ========== TÂCHE DE VÉRIFICATION D'INACTIVITÉ ==========

@tasks.loop(minutes=30)
async def check_inactive_tickets():
    """Vérifie les tickets inactifs"""
    now = datetime.now()
    
    for channel_id, last_activity in list(ticket_last_activity.items()):
        # Trouver le ticket
        ticket_user_id = None
        ticket_guild_id = None
        
        for user_id, data in modmail_tickets.items():
            if data['channel_id'] == channel_id:
                ticket_user_id = user_id
                ticket_guild_id = data['guild_id']
                break
        
        if not ticket_user_id:
            continue
        
        config = modmail_config.get(ticket_guild_id, DEFAULT_MODMAIL_CONFIG)
        inactivity_timeout = config.get('inactivity_timeout', 3600)
        auto_close_timeout = config.get('auto_close_timeout', 86400)
        
        inactive_duration = (now - last_activity).total_seconds()
        
        # Alerte d'inactivité (1h)
        if inactive_duration >= inactivity_timeout and inactive_duration < inactivity_timeout + 1800:
            guild = bot.get_guild(ticket_guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    user = bot.get_user(ticket_user_id)
                    
                    embed = discord.Embed(
                        title="⏰ Ticket inactif",
                        description=f"Ce ticket est inactif depuis plus d'**1 heure**.\n\n"
                                   f"**{user.mention}**, avez-vous encore besoin d'aide ?\n\n"
                                   f"⚠️ *Le ticket sera automatiquement fermé après 24h d'inactivité.*",
                        color=0xFEE75C,
                        timestamp=datetime.now()
                    )
                    embed.set_footer(text="Répondez à ce message pour garder le ticket ouvert")
                    
                    await channel.send(embed=embed)
        
        # Fermeture automatique (24h)
        elif inactive_duration >= auto_close_timeout:
            guild = bot.get_guild(ticket_guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    user = bot.get_user(ticket_user_id)
                    
                    # Notifier avant fermeture
                    embed_close = discord.Embed(
                        title="🔒 Fermeture automatique",
                        description=f"Ce ticket a été automatiquement fermé après **24 heures** d'inactivité.",
                        color=0xED4245,
                        timestamp=datetime.now()
                    )
                    embed_close.set_footer(text="Vous pouvez créer un nouveau ticket si nécessaire")
                    
                    await channel.send(embed=embed_close)
                    
                    # Notifier l'utilisateur
                    if user:
                        try:
                            user_embed = discord.Embed(
                                title="🔒 Ticket fermé automatiquement",
                                description=f"Votre ticket sur **{guild.name}** a été fermé après 24h d'inactivité.\n\n"
                                           f"Si vous avez encore besoin d'aide, n'hésitez pas à nous recontacter !",
                                color=0x5865F2
                            )
                            user_embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
                            await user.send(embed=user_embed)
                        except:
                            pass
                    
                    # Sauvegarder transcript
                    transcript = await generate_transcript(channel, ticket_user_id)
                    transcript_channel_id = config.get('transcript_channel_id')
                    
                    if transcript_channel_id:
                        transcript_channel = guild.get_channel(transcript_channel_id)
                        if transcript_channel:
                            embed = discord.Embed(
                                title="🔒 Ticket fermé (Inactivité)",
                                description="Fermeture automatique après 24h d'inactivité",
                                color=0xFEE75C,
                                timestamp=datetime.now()
                            )
                            embed.add_field(name="👤 Utilisateur", value=f"{user.mention}\n`{ticket_user_id}`", inline=True)
                            embed.add_field(name="⏰ Raison", value="Inactivité (24h)", inline=True)
                            
                            file = discord.File(
                                fp=io.BytesIO(transcript.encode('utf-8')),
                                filename=f"ticket-{ticket_user_id}-auto-close.txt"
                            )
                            
                            await transcript_channel.send(embed=embed, file=file)
                    
                    # Nettoyer
                    if ticket_user_id in modmail_tickets:
                        del modmail_tickets[ticket_user_id]
                    if channel_id in ticket_last_activity:
                        del ticket_last_activity[channel_id]
                    
                    # Supprimer le salon
                    try:
                        await channel.delete(reason="Fermeture automatique - Inactivité 24h")
                    except:
                        pass

# ========== COMMANDES SLASH ==========

@bot.tree.command(name="modmail_setup", description="[ADMIN] Configurer le système ModMail")
@app_commands.describe(
    categorie="Catégorie où créer les tickets",
    logs="Salon pour les logs",
    transcripts="Salon pour les transcripts",
    staff_role="Rôle du staff autorisé"
)
async def modmail_setup(
    interaction: discord.Interaction,
    categorie: discord.CategoryChannel,
    logs: discord.TextChannel,
    transcripts: discord.TextChannel,
    staff_role: discord.Role
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    if guild_id not in modmail_config:
        modmail_config[guild_id] = DEFAULT_MODMAIL_CONFIG.copy()
    
    modmail_config[guild_id]['category_id'] = categorie.id
    modmail_config[guild_id]['log_channel_id'] = logs.id
    modmail_config[guild_id]['transcript_channel_id'] = transcripts.id
    modmail_config[guild_id]['staff_role_id'] = staff_role.id
    
    embed = discord.Embed(
        title="✅ ModMail configuré avec succès !",
        description="Le système ModMail est maintenant opérationnel",
        color=0x57F287,
        timestamp=datetime.now()
    )
    embed.add_field(name="📁 Catégorie", value=categorie.mention, inline=False)
    embed.add_field(name="📋 Logs", value=logs.mention, inline=True)
    embed.add_field(name="💾 Transcripts", value=transcripts.mention, inline=True)
    embed.add_field(name="👥 Rôle Staff", value=staff_role.mention, inline=False)
    embed.set_footer(text="Les utilisateurs peuvent maintenant vous contacter en DM")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="modmail_blacklist", description="[ADMIN] Bloquer/Débloquer un utilisateur du ModMail")
@app_commands.describe(utilisateur="L'utilisateur à bloquer/débloquer")
async def modmail_blacklist_cmd(interaction: discord.Interaction, utilisateur: discord.User):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if utilisateur.id in modmail_blacklist:
        modmail_blacklist.remove(utilisateur.id)
        embed = discord.Embed(
            title="✅ Utilisateur débloqué",
            description=f"{utilisateur.mention} peut à nouveau utiliser le ModMail",
            color=0x57F287
        )
    else:
        modmail_blacklist.add(utilisateur.id)
        embed = discord.Embed(
            title="🚫 Utilisateur bloqué",
            description=f"{utilisateur.mention} ne peut plus utiliser le ModMail",
            color=0xED4245
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="modmail_stats", description="Voir les statistiques ModMail")
async def modmail_stats(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    guild_tickets = [t for t in modmail_tickets.values() if t['guild_id'] == interaction.guild.id]
    
    embed = discord.Embed(
        title="📊 Statistiques ModMail",
        description=f"Statistiques du serveur **{interaction.guild.name}**",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    embed.add_field(name="🎫 Tickets ouverts", value=str(len(guild_tickets)), inline=True)
    embed.add_field(name="📈 Total créés", value=str(ticket_counter.get(interaction.guild.id, 0)), inline=True)
    embed.add_field(name="🚫 Blacklistés", value=str(len(modmail_blacklist)), inline=True)
    
    # Par catégorie
    categories = {}
    for ticket in guild_tickets:
        cat = ticket.get('category', 'Autre')
        categories[cat] = categories.get(cat, 0) + 1
    
    if categories:
        cat_text = "\n".join([f"• {k}: **{v}**" for k, v in categories.items()])
        embed.add_field(name="📂 Par catégorie", value=cat_text, inline=False)
    
    # Tickets par priorité
    priorities = {'haute': 0, 'normale': 0, 'basse': 0}
    for ticket in guild_tickets:
        priority = ticket.get('priority', 'normale')
        priorities[priority] = priorities.get(priority, 0) + 1
    
    priority_text = f"🔴 Haute: **{priorities['haute']}**\n🟡 Normale: **{priorities['normale']}**\n🟢 Basse: **{priorities['basse']}**"
    embed.add_field(name="⚡ Par priorité", value=priority_text, inline=True)
    
    embed.set_footer(text=f"Demandé par {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="modmail_config", description="[ADMIN] Configurer les options ModMail")
@app_commands.describe(
    anonymous="Masquer l'identité du staff",
    cooldown="Temps entre deux tickets (secondes)",
    ping_role="Rôle à ping pour nouveaux tickets"
)
async def modmail_configure(
    interaction: discord.Interaction,
    anonymous: bool = None,
    cooldown: int = None,
    ping_role: discord.Role = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    
    if guild_id not in modmail_config:
        modmail_config[guild_id] = DEFAULT_MODMAIL_CONFIG.copy()
    
    changes = []
    
    if anonymous is not None:
        modmail_config[guild_id]['anonymous_staff'] = anonymous
        changes.append(f"👤 Staff anonyme: **{'Oui' if anonymous else 'Non'}**")
    
    if cooldown is not None:
        modmail_config[guild_id]['cooldown_seconds'] = cooldown
        changes.append(f"⏱️ Cooldown: **{cooldown}s**")
    
    if ping_role is not None:
        modmail_config[guild_id]['ping_role_id'] = ping_role.id
        changes.append(f"🔔 Rôle ping: {ping_role.mention}")
    
    if changes:
        embed = discord.Embed(
            title="✅ Configuration mise à jour",
            description="\n".join(changes),
            color=0x57F287,
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucun changement spécifié", ephemeral=True)

@bot.tree.command(name="close", description="[STAFF] Fermer le ticket actuel")
async def close_ticket_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    # Trouver le ticket
    ticket_user_id = None
    for user_id, data in modmail_tickets.items():
        if data['channel_id'] == interaction.channel.id:
            ticket_user_id = user_id
            break
    
    if not ticket_user_id:
        await interaction.response.send_message("❌ Ce n'est pas un salon de ticket !", ephemeral=True)
        return
    
    view = CloseConfirmView(interaction.channel, ticket_user_id, interaction.guild.id)
    embed = discord.Embed(
        title="⚠️ Confirmation de fermeture",
        description="Êtes-vous sûr de vouloir fermer ce ticket ?\n\n"
                   "• Le transcript sera sauvegardé\n"
                   "• L'utilisateur sera notifié\n"
                   "• Le salon sera supprimé",
        color=0xFEE75C
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="modmail_list", description="[STAFF] Voir tous les tickets ouverts")
async def list_tickets(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    guild_tickets = [(uid, data) for uid, data in modmail_tickets.items() if data['guild_id'] == interaction.guild.id]
    
    if not guild_tickets:
        embed = discord.Embed(
            title="✅ Aucun ticket ouvert",
            description="Il n'y a actuellement aucun ticket ouvert",
            color=0x57F287
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"🎫 Tickets ouverts ({len(guild_tickets)})",
        description=f"Liste des tickets actifs sur **{interaction.guild.name}**",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    
    for user_id, data in guild_tickets[:10]:
        user = bot.get_user(user_id)
        channel = interaction.guild.get_channel(data['channel_id'])
        
        if user and channel:
            priority_emoji = {'basse': '🟢', 'normale': '🟡', 'haute': '🔴'}
            priority = data.get('priority', 'normale')
            
            claimed = "✅" if data.get('claimed_by') else "⏳"
            
            value = f"{claimed} {channel.mention}\n"
            value += f"{priority_emoji.get(priority, '🟡')} **{priority.title()}** • {data.get('category', 'N/A')}"
            
            embed.add_field(name=f"👤 {user.name}", value=value, inline=False)
    
    if len(guild_tickets) > 10:
        embed.set_footer(text=f"Affichage de 10/{len(guild_tickets)} tickets")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== GESTION DES MESSAGES ==========
@bot.event
async def on_message(message):
    # Lunera Security check
    try:
        await on_lunera_message(message)
    except Exception as e:
        print(f"Erreur Lunera: {e}")
    
    # AutoMod check (AVANT TOUT)
    try:
        await on_automod_message(message)
    except Exception as e:
        print(f"Erreur AutoMod: {e}")
    
    if message.author.bot:
        return
    
    # === GESTION DES DM ===
    if isinstance(message.channel, discord.DMChannel):
        user = message.author
        
        # Vérifier blacklist
        if is_blacklisted(user.id):
            embed = discord.Embed(
                title="🚫 Accès refusé",
                description="Vous êtes bloqué du système ModMail.\n\nContactez un administrateur si vous pensez qu'il s'agit d'une erreur.",
                color=0xED4245
            )
            await message.channel.send(embed=embed)
            return
        
        # Ticket existant
        if user.id in modmail_tickets:
            ticket_data = modmail_tickets[user.id]
            guild = bot.get_guild(ticket_data['guild_id'])
            
            if guild:
                channel = guild.get_channel(ticket_data['channel_id'])
                
                if channel:
                    # Vérifier mots interdits
                    if check_bad_words(message.content, guild.id):
                        embed = discord.Embed(
                            title="⚠️ Message bloqué",
                            description="Votre message contient des mots interdits et n'a pas été envoyé.",
                            color=0xFEE75C
                        )
                        await message.channel.send(embed=embed)
                        return
                    
                    # Mettre à jour l'activité
                    ticket_last_activity[channel.id] = datetime.now()
                    
                    # Envoyer dans le salon
                    embed = discord.Embed(
                        description=message.content,
                        color=0x5865F2,
                        timestamp=datetime.now()
                    )
                    embed.set_author(
                        name=user.name,
                        icon_url=user.display_avatar.url
                    )
                    embed.set_footer(text=f"Message de l'utilisateur • ID: {user.id}")
                    
                    if message.attachments:
                        embed.set_image(url=message.attachments[0].url)
                    
                    await channel.send(embed=embed)
                    
                    # Sauvegarder
                    ticket_data['messages'].append({
                        'author': user.name,
                        'content': message.content,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    await message.add_reaction('✅')
                    return
        
        # Nouveau ticket
        mutual_guilds = [g for g in bot.guilds if g.get_member(user.id)]
        
        if not mutual_guilds:
            embed = discord.Embed(
                title="❌ Aucun serveur commun",
                description="Nous ne partageons aucun serveur !\n\nVous devez rejoindre un serveur avec ce bot pour utiliser le ModMail.",
                color=0xED4245
            )
            await message.channel.send(embed=embed)
            return
        
        target_guild = None
        for guild in mutual_guilds:
            if guild.id in modmail_config and modmail_config[guild.id].get('category_id'):
                target_guild = guild
                break
        
        if not target_guild:
            embed = discord.Embed(
                title="❌ ModMail non configuré",
                description="Le ModMail n'est pas configuré sur ce serveur.\n\nContactez un administrateur.",
                color=0xED4245
            )
            await message.channel.send(embed=embed)
            return
        
        config = modmail_config[target_guild.id]
        
        # Vérifier cooldown
        cooldown = check_cooldown(user.id)
        if cooldown > 0:
            minutes = cooldown // 60
            seconds = cooldown % 60
            embed = discord.Embed(
                title="⏳ Cooldown actif",
                description=f"Veuillez attendre encore **{minutes}min {seconds}s** avant de créer un nouveau ticket.",
                color=0xFEE75C
            )
            await message.channel.send(embed=embed)
            return
        
        # Vérifier max tickets
        user_tickets = [t for t in modmail_tickets.values() if t['guild_id'] == target_guild.id]
        if len(user_tickets) >= config.get('max_tickets_per_user', 1):
            embed = discord.Embed(
                title="❌ Ticket déjà ouvert",
                description="Vous avez déjà un ticket ouvert.\n\nFermez-le avant d'en créer un nouveau.",
                color=0xED4245
            )
            await message.channel.send(embed=embed)
            return
        
        # Demander catégorie
        embed = discord.Embed(
            title="🎫 Création d'un ticket ModMail",
            description=f"✨ Bienvenue sur le système ModMail de **{target_guild.name}** !\n\n"
                       f"📋 Pour commencer, veuillez sélectionner la **catégorie** qui correspond le mieux à votre demande.\n\n"
                       f"💡 *Un membre de notre équipe vous répondra dans les plus brefs délais.*",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=target_guild.icon.url if target_guild.icon else None)
        embed.set_footer(text=f"Serveur: {target_guild.name}", icon_url=target_guild.icon.url if target_guild.icon else None)
        
        view = TicketCategorySelectView(user, target_guild)
        msg = await message.channel.send(embed=embed, view=view)
        
        await view.wait()
        
        if not view.category:
            timeout_embed = discord.Embed(
                title="⏱️ Temps écoulé",
                description="La création du ticket a été annulée.\n\n*Envoyez un nouveau message pour recommencer.*",
                color=0xFEE75C
            )
            await message.channel.send(embed=timeout_embed)
            return
        
        # Animation de création
        progress_embed = discord.Embed(
            title="⏳ Création de votre ticket...",
            description="",
            color=0x5865F2
        )
        
        steps = [
            ("🔍 Vérification des permissions...", "✅ Permissions vérifiées"),
            ("📁 Création du salon privé...", "✅ Salon créé"),
            ("👥 Configuration des accès staff...", "✅ Accès configurés"),
            ("🎨 Préparation de votre espace...", "✅ Espace prêt"),
            ("🔧 Finalisation...", "✅ Ticket créé !")
        ]
        
        progress_msg = await message.channel.send(embed=progress_embed)
        
        completed_steps = []
        for i, (current, completed) in enumerate(steps):
            completed_steps.append(completed)
            
            progress_text = "\n".join(completed_steps)
            if i < len(steps) - 1:
                progress_text += f"\n{steps[i+1][0]}"
            
            progress_embed.description = progress_text
            await progress_msg.edit(embed=progress_embed)
            await asyncio.sleep(0.7)
        
        # Créer le ticket
        try:
            category = target_guild.get_channel(config['category_id'])
            
            if not category:
                await message.channel.send("❌ Catégorie introuvable !")
                return
            
            ticket_counter[target_guild.id] += 1
            ticket_num = ticket_counter[target_guild.id]
            
            channel_name = f"ticket-{user.name}-{ticket_num}".lower().replace(" ", "-")[:50]
            
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                topic=f"🎫 Ticket ModMail de {user.name} ({user.id}) • #{ticket_num}"
            )
            
            # PERMISSIONS CORRIGÉES - Seulement staff et utilisateur
            await ticket_channel.set_permissions(target_guild.default_role, view_channel=False)
            
            # Utilisateur (lecture seule)
            await ticket_channel.set_permissions(
                user,
                view_channel=True,
                send_messages=False,
                read_messages=True,
                read_message_history=True
            )
            
            # Rôle staff
            staff_role_id = config.get('staff_role_id')
            if staff_role_id:
                staff_role = target_guild.get_role(staff_role_id)
                if staff_role:
                    await ticket_channel.set_permissions(
                        staff_role,
                        view_channel=True,
                        send_messages=True,
                        read_messages=True,
                        read_message_history=True,
                        embed_links=True,
                        attach_files=True
                    )
            
            # Administrateurs (au cas où)
            for role in target_guild.roles:
                if role.permissions.administrator:
                    await ticket_channel.set_permissions(
                        role,
                        view_channel=True,
                        send_messages=True
                    )
            
            modmail_tickets[user.id] = {
                'channel_id': ticket_channel.id,
                'guild_id': target_guild.id,
                'category': view.category,
                'priority': 'normale',
                'claimed_by': None,
                'messages': [],
                'tags': set(),
                'created_at': datetime.now()
            }
            
            # Initialiser l'activité
            ticket_last_activity[ticket_channel.id] = datetime.now()
            
            modmail_cooldowns[user.id] = datetime.now() + timedelta(seconds=config.get('cooldown_seconds', 300))
            
            member = target_guild.get_member(user.id)
            
            embed_ticket = discord.Embed(
                title=f"🎫 Nouveau Ticket ModMail",
                description=f"Un nouveau ticket a été ouvert par {user.mention}",
                color=0x5865F2,
                timestamp=datetime.now()
            )
            
            embed_ticket.add_field(
                name="💬 Message initial",
                value=f"```{message.content[:300]}{'...' if len(message.content) > 300 else ''}```",
                inline=False
            )
            
            embed_ticket.add_field(name="📂 Catégorie", value=view.category, inline=True)
            embed_ticket.add_field(name="📊 Priorité", value="🟡 Normale", inline=True)
            embed_ticket.add_field(name="🆔 Numéro", value=f"#{ticket_num}", inline=True)
            
            if member:
                account_age = (datetime.now() - user.created_at.replace(tzinfo=None)).days
                join_age = (datetime.now() - member.joined_at.replace(tzinfo=None)).days
                
                user_info = f"**ID:** `{user.id}`\n"
                user_info += f"**Compte créé:** {account_age} jours\n"
                user_info += f"**Membre depuis:** {join_age} jours"
                
                embed_ticket.add_field(name="👤 Informations", value=user_info, inline=False)
                
                if len(member.roles) > 1:
                    roles = ", ".join([r.mention for r in member.roles[1:5]])
                    if len(member.roles) > 5:
                        roles += f" *+{len(member.roles) - 5}*"
                    embed_ticket.add_field(name="🎭 Rôles", value=roles, inline=False)
            
            embed_ticket.set_thumbnail(url=user.display_avatar.url)
            embed_ticket.set_footer(
                text=f"Ticket #{ticket_num} • Ouvert le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
                icon_url=user.display_avatar.url
            )
            
            view_control = TicketControlView(ticket_channel, user.id, target_guild.id)
            await ticket_channel.send(embed=embed_ticket, view=view_control)
            
            ping_role_id = config.get('ping_role_id')
            if ping_role_id:
                role = target_guild.get_role(ping_role_id)
                if role:
                    ping_embed = discord.Embed(
                        description=f"🔔 {role.mention} **Nouveau ticket à traiter !**",
                        color=0x5865F2
                    )
                    await ticket_channel.send(embed=ping_embed)
            
            greeting = config.get('greeting_message', DEFAULT_MODMAIL_CONFIG['greeting_message'])
            
            embed_welcome = discord.Embed(
                title="✅ Ticket créé avec succès !",
                description=greeting,
                color=0x57F287,
                timestamp=datetime.now()
            )
            embed_welcome.add_field(name="🏢 Serveur", value=target_guild.name, inline=True)
            embed_welcome.add_field(name="📂 Catégorie", value=view.category, inline=True)
            embed_welcome.add_field(name="🎫 Numéro", value=f"#{ticket_num}", inline=True)
            
            embed_welcome.add_field(
                name="📝 Prochaines étapes",
                value="• Continuez à m'envoyer des messages ici\n"
                      "• Vos messages seront transmis à l'équipe\n"
                      "• Vous recevrez une réponse rapidement\n"
                      "• Le ticket sera fermé après résolution",
                inline=False
            )
            
            embed_welcome.set_thumbnail(url=target_guild.icon.url if target_guild.icon else None)
            embed_welcome.set_footer(
                text=f"Créé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
                icon_url=user.display_avatar.url
            )
            
            try:
                await progress_msg.delete()
            except:
                pass
            
            await message.channel.send(embed=embed_welcome)
            
            log_channel_id = config.get('log_channel_id')
            if log_channel_id:
                log_channel = target_guild.get_channel(log_channel_id)
                if log_channel:
                    log_embed = discord.Embed(
                        title="📨 Nouveau ticket ModMail",
                        description=f"Un ticket a été créé par {user.mention}",
                        color=0x5865F2,
                        timestamp=datetime.now()
                    )
                    log_embed.add_field(name="👤 Utilisateur", value=f"{user.name}\n`{user.id}`", inline=True)
                    log_embed.add_field(name="📂 Catégorie", value=view.category, inline=True)
                    log_embed.add_field(name="🎫 Numéro", value=f"#{ticket_num}", inline=True)
                    log_embed.add_field(name="📍 Salon", value=ticket_channel.mention, inline=False)
                    log_embed.set_thumbnail(url=user.display_avatar.url)
                    log_embed.set_footer(text=f"Ticket #{ticket_num}")
                    
                    await log_channel.send(embed=log_embed)
        
        except Exception as e:
            print(f"Erreur création ticket: {e}")
            await message.channel.send(f"❌ Erreur lors de la création: {str(e)}")
        
        return
    
    # === MESSAGES DANS LES SALONS DE TICKETS ===
    if message.guild:
        ticket_user_id = None
        for user_id, data in modmail_tickets.items():
            if data['channel_id'] == message.channel.id:
                ticket_user_id = user_id
                break
        
        if ticket_user_id:
            # Vérifier que c'est bien un membre du staff
            if not is_staff(message.author, message.guild.id):
                return
            
            user = bot.get_user(ticket_user_id)
            
            if user:
                config = modmail_config.get(message.guild.id, {})
                anonymous = config.get('anonymous_staff', False)
                
                # Mettre à jour l'activité
                ticket_last_activity[message.channel.id] = datetime.now()
                
                embed = discord.Embed(
                    description=message.content,
                    color=0x57F287,
                    timestamp=datetime.now()
                )
                
                if anonymous:
                    embed.set_author(
                        name="Équipe Support",
                        icon_url=message.guild.icon.url if message.guild.icon else None
                    )
                else:
                    embed.set_author(
                        name=f"{message.author.name} (Staff)",
                        icon_url=message.author.display_avatar.url
                    )
                
                embed.set_footer(
                    text=f"{message.guild.name} • Réponse du support",
                    icon_url=message.guild.icon.url if message.guild.icon else None
                )
                
                if message.attachments:
                    embed.set_image(url=message.attachments[0].url)
                
                try:
                    await user.send(embed=embed)
                    await message.add_reaction('✅')
                    
                    modmail_tickets[ticket_user_id]['messages'].append({
                        'author': message.author.name,
                        'content': message.content,
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception as e:
                    error_embed = discord.Embed(
                        title="⚠️ Erreur d'envoi",
                        description="Impossible d'envoyer le message à l'utilisateur.\n\n**Raison possible:**\n• DM fermés\n• Utilisateur bloqué le bot\n• Utilisateur quitté le serveur",
                        color=0xFEE75C
                    )
                    await message.channel.send(embed=error_embed)
            
            return
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    try:
        await on_lunera_member_join(member)
    except Exception as e:
        print(f"Erreur Lunera join: {e}")
    
    try:
        await on_automod_member_join(member)
    except Exception as e:
        print(f"Erreur AutoMod join: {e}")

@bot.event
async def on_ready():
    try:
        await setup_lunera_commands(bot)
        print("🌙 Commandes Lunera enregistrées")
    except Exception as e:
        print(f"⚠️ Erreur Lunera commands: {e}")
    
    print("="*50)
    print(f'✅ {bot.user} est connecté et prêt !')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'🌐 Serveurs: {len(bot.guilds)}')
    print(f'👥 Utilisateurs: {sum(g.member_count for g in bot.guilds)}')
    print("="*50)
    # Statut personnalisé
    activity = discord.Streaming(
        name="🎫 DM pour ouvrir un ticket",
        url="https://twitch.tv/helpdesk"
    )
    await bot.change_presence(activity=activity, status=discord.Status.online)
    
    # Setup AutoMod
    try:
        await setup_commands(bot)
        print("✅ Commandes AutoMod enregistrées")
    except Exception as e:
        print(f"⚠️ Erreur AutoMod commands: {e}")
    
    # Sync commandes
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synchronisé {len(synced)} commandes slash')
    except Exception as e:
        print(f'❌ Erreur de synchronisation: {e}')
    
    # Démarrer la vérification d'inactivité
    if not check_inactive_tickets.is_running():
        check_inactive_tickets.start()
        print("✅ Vérification d'inactivité démarrée")
    
    print("="*50)
    print("🚀 Bot opérationnel !")
    print("="*50)
@bot.event
async def on_ready():
    # ... votre code existant ...
    
    # Démarrer la vérification d'inactivité
    if not check_inactive_tickets.is_running():
        check_inactive_tickets.start()
        print("✅ Vérification d'inactivité démarrée")
    
    print("="*50)
    print("🚀 Bot opérationnel !")
    print("="*50)
    
    # ✅ AJOUTEZ CES LIGNES ICI
    try:
        await bot.add_cog(SecurityModule(bot))
        print("🛡️ ✅ Module de sécurité chargé et activé !")
    except Exception as e:
        print(f"⚠️ Erreur chargement module sécurité: {e}")
```

## 3️⃣ Structure finale des fichiers
```

# Serveur web pour Render
app = Flask(__name__)

@app.route('/')
def home():
    uptime = datetime.now() - bot.start_time if hasattr(bot, 'start_time') else timedelta(0)
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ModMail Bot Status</title>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }}
            .container {{
                text-align: center;
                background: rgba(255, 255, 255, 0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
            }}
            h1 {{
                font-size: 3em;
                margin: 0;
            }}
            .status {{
                display: inline-block;
                width: 20px;
                height: 20px;
                background: #00ff00;
                border-radius: 50%;
                animation: pulse 2s infinite;
                margin-right: 10px;
            }}
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.5; }}
            }}
            .info {{
                margin-top: 30px;
                font-size: 1.2em;
            }}
            .info div {{
                margin: 10px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1><span class="status"></span>Bot Actif</h1>
            <div class="info">
                <div>🎫 <strong>ModMail</strong> • 🛡️ <strong>AutoMod</strong> • 🎉 <strong>Giveaways</strong></div>
                <div>⏱️ Uptime: {str(uptime).split('.')[0]}</div>
                <div>🌐 Serveurs: {len(bot.guilds)}</div>
                <div>🎫 Tickets ouverts: {len(modmail_tickets)}</div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# Lance le bot
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("❌ ERREUR: Token Discord non trouvé dans les variables d'environnement !")
    print("Assurez-vous d'avoir défini DISCORD_TOKEN sur Render")
else:
    print("✅ Token trouvé, démarrage du bot...")
    bot.start_time = datetime.now()
    keep_alive()
    bot.run(TOKEN)







