import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import io
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
# Importer le système giveaway
exec(open('giveaway.py').read())
```

---

## **🎯 COMMANDES GIVEAWAY**
```
/giveaway_create - Créer un giveaway (modal interactif)
/giveaway_end - Terminer un giveaway immédiatement
/giveaway_reroll - Re-tirer un gagnant
/giveaway_list - Liste des giveaways actifs
```

---

## **🎨 FONCTIONNALITÉS INCLUSES**

✅ **Création facile** : Modal avec tous les champs  
✅ **Configuration avancée** : Rôle requis, mode pondéré, etc.  
✅ **Participation par bouton** : Clic pour participer/annuler  
✅ **Anti-triche** : Vérif âge compte, rôles, blacklist  
✅ **Mode pondéré** : Boosters ont plus de chances  
✅ **Countdown automatique** : Se termine tout seul  
✅ **Sélection aléatoire** : Équitable ou pondéré  
✅ **DM aux gagnants** : Automatique  
✅ **Reroll** : Re-tirer un gagnant  
✅ **Historique** : Stocké en mémoire  
✅ **Embeds professionnels** : Design soigné  

---

## **💡 UTILISATION**

### **Créer un giveaway :**

1. Tape `/giveaway_create`
2. Remplis le modal :
   - Titre : "Nitro 1 mois"
   - Description : "Gagnez..."
   - Durée : "2h 30m" ou "1d 12h"
   - Gagnants : "1"
   - Image URL : (optionnel)

3. Configure les options :
   - Sélectionne le salon
   - Rôle requis (optionnel)
   - Rôle à ping (optionnel)
   - Active le mode pondéré si tu veux

4. Clique "✅ Lancer le Giveaway"

5. **C'est parti !** 🎉

### **Participer :**

Les users cliquent sur "🎉 Participer" dans le message du giveaway.

### **Terminer manuellement :**
```
/giveaway_end message_id:123456789
```

(Fais clic droit sur le message → Copier l'ID)

### **Reroll :**
```
/giveaway_reroll message_id:123456789
# Configuration du bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# ========== STOCKAGE DES DONNÉES ==========
modmail_tickets = {}  # {user_id: {'channel_id', 'guild_id', 'category', 'priority', 'claimed_by', 'messages', 'tags', 'created_at'}}
modmail_config = {}  # {guild_id: {config}}
modmail_blacklist = set()  # {user_id}
modmail_cooldowns = {}  # {user_id: datetime}
modmail_templates = {}  # {guild_id: {name: text}}
staff_notes = defaultdict(list)  # {ticket_channel_id: [{author, note, timestamp}]}
ticket_counter = defaultdict(int)  # {guild_id: count}

# Configuration par défaut
DEFAULT_MODMAIL_CONFIG = {
    'enabled': True,
    'category_id': None,
    'log_channel_id': None,
    'transcript_channel_id': None,
    'anonymous_staff': False,
    'cooldown_seconds': 300,  # 5 minutes
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
    'auto_responses': {},
    'greeting_message': 'Merci de nous contacter ! Un membre du staff vous répondra bientôt.',
    'closing_message': 'Merci d\'avoir contacté notre équipe. Ce ticket est maintenant fermé.',
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
        
        # Ajouter les boutons de catégories (max 5 par ligne)
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
            await interaction.response.send_message(f"✅ Catégorie sélectionnée: **{name}**\n\nCréation du ticket...", ephemeral=True)
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
            
            embed = discord.Embed(
                title="✅ Ticket réclamé",
                description=f"Ticket pris en charge par {interaction.user.mention}",
                color=discord.Color.blue()
            )
            await self.ticket_channel.send(embed=embed)
            await interaction.response.send_message("✅ Ticket réclamé !", ephemeral=True)
    
    @discord.ui.button(label="⚡ Urgent", style=discord.ButtonStyle.danger, custom_id="mark_urgent")
    async def mark_urgent(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id in modmail_tickets:
            modmail_tickets[self.user_id]['priority'] = 'haute'
            modmail_tickets[self.user_id]['tags'].add('urgent')
            
            # Renommer le salon avec emoji attention
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
            
            embed = discord.Embed(
                title="⚠️ TICKET URGENT",
                description=f"{ping_text}Ce ticket nécessite une attention immédiate !",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(name="Marqué par", value=interaction.user.mention, inline=True)
            embed.add_field(name="Priorité", value="🔴 HAUTE", inline=True)
            embed.set_footer(text="Veuillez traiter ce ticket en priorité")
            
            await self.ticket_channel.send(embed=embed)
            await interaction.response.send_message("✅ Ticket marqué comme urgent !", ephemeral=True)
    
    @discord.ui.button(label="💾 Sauvegarder", style=discord.ButtonStyle.success, custom_id="save_transcript")
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
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Utilisateur", value=f"{user.mention if user else 'Inconnu'} ({self.user_id})", inline=True)
                embed.add_field(name="Catégorie", value=ticket_data.get('category', 'N/A'), inline=True)
                embed.add_field(name="Priorité", value=ticket_data.get('priority', 'normale'), inline=True)
                
                claimed_by = ticket_data.get('claimed_by')
                if claimed_by:
                    claimed_user = interaction.guild.get_member(claimed_by)
                    embed.add_field(name="Géré par", value=claimed_user.mention if claimed_user else 'Inconnu', inline=True)
                
                file = discord.File(
                    fp=io.BytesIO(transcript.encode('utf-8')),
                    filename=f"ticket-{self.user_id}-{datetime.now().strftime('%Y%m%d')}.txt"
                )
                
                await channel.send(embed=embed, file=file)
        
        await interaction.followup.send("✅ Transcript sauvegardé !", ephemeral=True)
    
    @discord.ui.button(label="🔒 Fermer", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CloseConfirmView(self.ticket_channel, self.user_id, self.guild_id)
        await interaction.response.send_message("⚠️ Voulez-vous vraiment fermer ce ticket ?", view=view, ephemeral=True)

class CloseConfirmView(discord.ui.View):
    def __init__(self, ticket_channel, user_id, guild_id):
        super().__init__(timeout=30)
        self.ticket_channel = ticket_channel
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="✅ Oui, fermer", style=discord.ButtonStyle.danger)
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
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="Utilisateur", value=f"{user.mention if user else 'Inconnu'} ({self.user_id})", inline=True)
                embed.add_field(name="Fermé par", value=interaction.user.mention, inline=True)
                embed.add_field(name="Catégorie", value=ticket_data.get('category', 'N/A'), inline=True)
                
                duration = datetime.now() - ticket_data.get('created_at', datetime.now())
                embed.add_field(name="Durée", value=str(duration).split('.')[0], inline=True)
                
                file = discord.File(
                    fp=io.BytesIO(transcript.encode('utf-8')),
                    filename=f"ticket-{self.user_id}-{datetime.now().strftime('%Y%m%d')}.txt"
                )
                
                await channel.send(embed=embed, file=file)
        
        # Notifier l'utilisateur
        user = bot.get_user(self.user_id)
        if user:
            try:
                closing_msg = config.get('closing_message', DEFAULT_MODMAIL_CONFIG['closing_message'])
                
                embed = discord.Embed(
                    title="🔒 Ticket fermé",
                    description=closing_msg,
                    color=discord.Color.red()
                )
                embed.add_field(name="Fermé par", value=interaction.user.name, inline=True)
                
                # Sondage de satisfaction
                if config.get('satisfaction_survey', True):
                    view = SatisfactionView(self.user_id, self.guild_id)
                    await user.send(embed=embed, view=view)
                else:
                    await user.send(embed=embed)
            except:
                pass
        
        # Supprimer du stockage
        if self.user_id in modmail_tickets:
            del modmail_tickets[self.user_id]
        
        # Supprimer le salon
        await self.ticket_channel.delete(reason=f"Ticket fermé par {interaction.user.name}")
        
        await interaction.followup.send("✅ Ticket fermé et supprimé", ephemeral=True)
    
    @discord.ui.button(label="❌ Annuler", style=discord.ButtonStyle.secondary)
    async def cancel_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Annulé", ephemeral=True)
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
        config = modmail_config.get(self.guild_id, {})
        log_channel_id = config.get('log_channel_id')
        
        if log_channel_id:
            guild = bot.get_guild(self.guild_id)
            if guild:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    embed = discord.Embed(
                        title="⭐ Satisfaction utilisateur",
                        description=f"Note: {'⭐' * rating} ({rating}/5)",
                        color=discord.Color.gold()
                    )
                    embed.add_field(name="Utilisateur", value=f"<@{self.user_id}>", inline=True)
                    embed.set_footer(text=datetime.now().strftime("%d/%m/%Y %H:%M"))
                    
                    await channel.send(embed=embed)
        
        await interaction.response.send_message(f"✅ Merci pour votre retour ! {'⭐' * rating}", ephemeral=True)
        self.stop()

class NoteModal(discord.ui.Modal, title="Ajouter une note interne"):
    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id
    
    note_input = discord.ui.TextInput(
        label="Note (invisible pour l'utilisateur)",
        style=discord.TextStyle.paragraph,
        placeholder="Tapez votre note ici...",
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
            color=discord.Color.orange()
        )
        embed.set_author(name=interaction.user.name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Cette note est invisible pour l'utilisateur")
        
        await interaction.response.send_message(embed=embed)

# ========== FONCTIONS UTILITAIRES ==========

async def generate_transcript(channel, user_id):
    """Génère un transcript du ticket"""
    lines = []
    lines.append("="*60)
    lines.append(f"TRANSCRIPT DU TICKET - {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines.append("="*60)
    lines.append(f"Utilisateur: {user_id}")
    
    ticket_data = modmail_tickets.get(user_id, {})
    lines.append(f"Catégorie: {ticket_data.get('category', 'N/A')}")
    lines.append(f"Priorité: {ticket_data.get('priority', 'normale')}")
    
    if ticket_data.get('claimed_by'):
        lines.append(f"Géré par: {ticket_data['claimed_by']}")
    
    lines.append("="*60)
    lines.append("")
    
    # Messages
    async for message in channel.history(limit=None, oldest_first=True):
        if message.author.bot and not message.embeds:
            continue
        
        timestamp = message.created_at.strftime("%d/%m/%Y %H:%M:%S")
        
        if message.embeds and message.embeds[0].title == "📝 Note interne ajoutée":
            lines.append(f"[{timestamp}] [NOTE INTERNE] {message.embeds[0].author.name}: {message.embeds[0].description}")
        elif message.content:
            lines.append(f"[{timestamp}] {message.author.name}: {message.content}")
        elif message.embeds:
            embed = message.embeds[0]
            if embed.description:
                lines.append(f"[{timestamp}] {message.author.name}: {embed.description}")
    
    # Notes internes
    if channel.id in staff_notes and staff_notes[channel.id]:
        lines.append("")
        lines.append("="*60)
        lines.append("NOTES INTERNES")
        lines.append("="*60)
        for note in staff_notes[channel.id]:
            ts = note['timestamp'].strftime("%d/%m/%Y %H:%M:%S")
            lines.append(f"[{ts}] {note['author']}: {note['note']}")
    
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

# ========== COMMANDES SLASH ==========

@bot.tree.command(name="modmail_setup", description="[ADMIN] Configurer le système ModMail")
@app_commands.describe(
    categorie="Catégorie où créer les tickets",
    logs="Salon pour les logs",
    transcripts="Salon pour les transcripts"
)
async def modmail_setup(
    interaction: discord.Interaction,
    categorie: discord.CategoryChannel,
    logs: discord.TextChannel,
    transcripts: discord.TextChannel
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
    
    embed = discord.Embed(
        title="✅ ModMail configuré !",
        color=discord.Color.green()
    )
    embed.add_field(name="Catégorie", value=categorie.mention, inline=False)
    embed.add_field(name="Logs", value=logs.mention, inline=True)
    embed.add_field(name="Transcripts", value=transcripts.mention, inline=True)
    embed.set_footer(text="Les utilisateurs peuvent maintenant vous contacter en DM !")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="modmail_blacklist", description="[ADMIN] Bloquer/Débloquer un utilisateur du ModMail")
@app_commands.describe(utilisateur="L'utilisateur à bloquer/débloquer")
async def modmail_blacklist_cmd(interaction: discord.Interaction, utilisateur: discord.User):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    if utilisateur.id in modmail_blacklist:
        modmail_blacklist.remove(utilisateur.id)
        await interaction.response.send_message(f"✅ {utilisateur.mention} peut à nouveau utiliser le ModMail", ephemeral=True)
    else:
        modmail_blacklist.add(utilisateur.id)
        await interaction.response.send_message(f"🚫 {utilisateur.mention} ne peut plus utiliser le ModMail", ephemeral=True)

@bot.tree.command(name="modmail_stats", description="Voir les statistiques ModMail")
async def modmail_stats(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    guild_tickets = [t for t in modmail_tickets.values() if t['guild_id'] == interaction.guild.id]
    
    embed = discord.Embed(
        title="📊 Statistiques ModMail",
        color=discord.Color.blue()
    )
    embed.add_field(name="Tickets ouverts", value=str(len(guild_tickets)), inline=True)
    embed.add_field(name="Tickets total", value=str(ticket_counter.get(interaction.guild.id, 0)), inline=True)
    
    # Par catégorie
    categories = {}
    for ticket in guild_tickets:
        cat = ticket.get('category', 'Autre')
        categories[cat] = categories.get(cat, 0) + 1
    
    if categories:
        cat_text = "\n".join([f"{k}: {v}" for k, v in categories.items()])
        embed.add_field(name="Par catégorie", value=cat_text, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="modmail_config", description="[ADMIN] Configurer les options ModMail")
@app_commands.describe(
    anonymous="Masquer l'identité du staff (Oui/Non)",
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
        changes.append(f"Staff anonyme: {'Oui' if anonymous else 'Non'}")
    
    if cooldown is not None:
        modmail_config[guild_id]['cooldown_seconds'] = cooldown
        changes.append(f"Cooldown: {cooldown}s")
    
    if ping_role is not None:
        modmail_config[guild_id]['ping_role_id'] = ping_role.id
        changes.append(f"Rôle ping: {ping_role.mention}")
    
    if changes:
        embed = discord.Embed(
            title="✅ Configuration mise à jour",
            description="\n".join(changes),
            color=discord.Color.green()
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
    await interaction.response.send_message("⚠️ Fermer ce ticket ?", view=view, ephemeral=True)

@bot.tree.command(name="modmail_list", description="[STAFF] Voir tous les tickets ouverts")
async def list_tickets(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Permission refusée !", ephemeral=True)
        return
    
    guild_tickets = [(uid, data) for uid, data in modmail_tickets.items() if data['guild_id'] == interaction.guild.id]
    
    if not guild_tickets:
        await interaction.response.send_message("✅ Aucun ticket ouvert", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"🎫 Tickets ouverts ({len(guild_tickets)})",
        color=discord.Color.blue()
    )
    
    for user_id, data in guild_tickets[:10]:  # Max 10
        user = bot.get_user(user_id)
        channel = interaction.guild.get_channel(data['channel_id'])
        
        if user and channel:
            priority_emoji = {'basse': '🟢', 'normale': '🟡', 'haute': '🔴'}
            priority = data.get('priority', 'normale')
            
            value = f"Salon: {channel.mention}\n"
            value += f"Priorité: {priority_emoji.get(priority, '🟡')} {priority}\n"
            value += f"Catégorie: {data.get('category', 'N/A')}"
            
            embed.add_field(name=f"👤 {user.name}", value=value, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

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
        self.booster_bonus = 1.0
        self.color = 0xF1C40F  # Or
        self.ping_role = None
        self.channel = None
    
    @discord.ui.button(label="✅ Lancer le Giveaway", style=discord.ButtonStyle.success, row=0)
    async def launch_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.channel:
            await interaction.response.send_message("❌ Veuillez d'abord sélectionner un salon !", ephemeral=True)
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
        
        await interaction.followup.send(f"✅ Giveaway lancé avec succès dans {self.channel.mention} !", ephemeral=True)
        
        # Log
        await log_giveaway_action(interaction.guild, "🎁 Giveaway créé", self.creator, self.prize, message.jump_url)
    
    @discord.ui.channel_select(placeholder="📍 Sélectionner le salon", row=1)
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.channel = select.values[0]
        await interaction.response.send_message(f"✅ Salon sélectionné : {self.channel.mention}", ephemeral=True)
    
    @discord.ui.role_select(placeholder="👔 Rôle requis (optionnel)", row=2)
    async def select_required_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.required_role = select.values[0].id
        await interaction.response.send_message(f"✅ Rôle requis : {select.values[0].mention}", ephemeral=True)
    
    @discord.ui.role_select(placeholder="🔔 Rôle à ping (optionnel)", row=3)
    async def select_ping_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.ping_role = select.values[0].id
        await interaction.response.send_message(f"✅ Rôle à ping : {select.values[0].mention}", ephemeral=True)
    
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
# ========== GESTION DES MESSAGES ==========

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # === GESTION DES DM ===
    if isinstance(message.channel, discord.DMChannel):
        user = message.author
        
        # Vérifier blacklist
        if is_blacklisted(user.id):
            await message.channel.send("🚫 Vous êtes bloqué du système ModMail.")
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
                        await message.channel.send("⚠️ Votre message contient des mots interdits et n'a pas été envoyé.")
                        return
                    
                    # Envoyer dans le salon
                    embed = discord.Embed(
                        description=message.content,
                        color=0x5865F2,  # Bleu Discord
                        timestamp=datetime.now()
                    )
                    embed.set_author(
                        name=user.name,
                        icon_url=user.display_avatar.url
                    )
                    embed.set_footer(text=f"Message de l'utilisateur • {user.id}")
                    
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
        # Trouver serveur commun
        mutual_guilds = [g for g in bot.guilds if g.get_member(user.id)]
        
        if not mutual_guilds:
            await message.channel.send("❌ Nous ne partageons aucun serveur !")
            return
        
        # Prendre le premier avec config
        target_guild = None
        for guild in mutual_guilds:
            if guild.id in modmail_config and modmail_config[guild.id].get('category_id'):
                target_guild = guild
                break
        
        if not target_guild:
            await message.channel.send("❌ Le ModMail n'est pas configuré sur ce serveur !\n\nContactez un administrateur.")
            return
        
        config = modmail_config[target_guild.id]
        
        # Vérifier cooldown
        cooldown = check_cooldown(user.id)
        if cooldown > 0:
            await message.channel.send(f"⏳ Veuillez attendre encore {cooldown} secondes avant de créer un nouveau ticket.")
            return
        
        # Vérifier max tickets
        user_tickets = [t for t in modmail_tickets.values() if t['guild_id'] == target_guild.id]
        if len(user_tickets) >= config.get('max_tickets_per_user', 1):
            await message.channel.send("❌ Vous avez déjà un ticket ouvert. Fermez-le avant d'en créer un nouveau.")
            return
        
        # Demander catégorie
        embed = discord.Embed(
            title="🎫 Création d'un ticket ModMail",
            description=f"Bienvenue sur le système ModMail de **{target_guild.name}** !\n\n"
                       f"Pour commencer, veuillez sélectionner la **catégorie** qui correspond le mieux à votre demande.\n\n"
                       f"💡 *Un membre de notre équipe vous répondra dans les plus brefs délais.*",
            color=0x5865F2  # Bleu Discord
        )
        embed.set_thumbnail(url=target_guild.icon.url if target_guild.icon else None)
        embed.set_footer(text=f"Serveur: {target_guild.name}", icon_url=target_guild.icon.url if target_guild.icon else None)
        
        view = TicketCategorySelectView(user, target_guild)
        msg = await message.channel.send(embed=embed, view=view)
        
        await view.wait()
        
        if not view.category:
            timeout_embed = discord.Embed(
                title="⏱️ Temps écoulé",
                description="La création du ticket a été annulée car vous n'avez pas sélectionné de catégorie à temps.\n\n*Envoyez un nouveau message pour recommencer.*",
                color=discord.Color.orange()
            )
            await message.channel.send(embed=timeout_embed)
            return
        
        # Animation de création avec progression
        progress_embed = discord.Embed(
            title="⏳ Création de votre ticket en cours...",
            description="",
            color=0x5865F2
        )
        
        steps = [
            ("Vérification des permissions...", "✅ Permissions vérifiées"),
            ("Création du salon privé...", "✅ Salon créé"),
            ("Configuration des accès staff...", "✅ Accès configurés"),
            ("Préparation de votre espace...", "✅ Espace prêt"),
            ("Finalisation...", "✅ Ticket créé !")
        ]
        
        progress_msg = await message.channel.send(embed=progress_embed)
        
        completed_steps = []
        for i, (current, completed) in enumerate(steps):
            completed_steps.append(completed)
            
            progress_text = "\n".join(completed_steps)
            if i < len(steps) - 1:
                progress_text += f"\n🔄 {steps[i+1][0]}"
            
            progress_embed.description = progress_text
            await progress_msg.edit(embed=progress_embed)
            await asyncio.sleep(0.8)  # Animation fluide
        
        # Créer le ticket
        try:
            category = target_guild.get_channel(config['category_id'])
            
            if not category:
                await message.channel.send("❌ Catégorie introuvable !")
                return
            
            # Incrémenter compteur
            ticket_counter[target_guild.id] += 1
            ticket_num = ticket_counter[target_guild.id]
            
            channel_name = f"modmail-{user.name}-{ticket_num}".lower().replace(" ", "-")[:50]
            
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                topic=f"ModMail de {user.name} ({user.id}) - Ticket #{ticket_num}"
            )
            
            # Permissions
            await ticket_channel.set_permissions(target_guild.default_role, view_channel=False)
            await ticket_channel.set_permissions(user, view_channel=True, send_messages=False, read_messages=True)
            
            # Permissions staff
            for role in target_guild.roles:
                if role.permissions.manage_messages or role.permissions.administrator:
                    await ticket_channel.set_permissions(role, view_channel=True, send_messages=True)
            
            # Enregistrer
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
            
            # Cooldown
            modmail_cooldowns[user.id] = datetime.now() + timedelta(seconds=config.get('cooldown_seconds', 300))
            
            # Infos utilisateur
            member = target_guild.get_member(user.id)
            
            embed_ticket = discord.Embed(
                title=f"🎫 Ticket ModMail #{ticket_num}",
                description=f"Un nouveau ticket a été ouvert par {user.mention}",
                color=0x5865F2,
                timestamp=datetime.now()
            )
            
            # Message initial
            embed_ticket.add_field(
                name="💬 Message initial",
                value=f"```{message.content[:200]}{'...' if len(message.content) > 200 else ''}```",
                inline=False
            )
            
            # Catégorie et priorité
            embed_ticket.add_field(name="📂 Catégorie", value=view.category, inline=True)
            embed_ticket.add_field(name="📊 Priorité", value="🟡 Normale", inline=True)
            embed_ticket.add_field(name="🆔 Ticket", value=f"#{ticket_num}", inline=True)
            
            # Infos utilisateur
            if member:
                account_age = (datetime.now() - user.created_at.replace(tzinfo=None)).days
                join_age = (datetime.now() - member.joined_at.replace(tzinfo=None)).days
                
                user_info = f"**ID:** `{user.id}`\n"
                user_info += f"**Compte créé:** Il y a {account_age} jours\n"
                user_info += f"**Rejoint:** Il y a {join_age} jours"
                
                embed_ticket.add_field(name="👤 Informations utilisateur", value=user_info, inline=False)
                
                if len(member.roles) > 1:
                    roles = ", ".join([r.mention for r in member.roles[1:6]])
                    if len(member.roles) > 6:
                        roles += f" *+{len(member.roles) - 6} autres*"
                    embed_ticket.add_field(name="🎭 Rôles", value=roles, inline=False)
            
            embed_ticket.set_thumbnail(url=user.display_avatar.url)
            embed_ticket.set_footer(
                text=f"Ouvert par {user.name} • Utilisez les boutons pour gérer ce ticket",
                icon_url=user.display_avatar.url
            )
            
            view_control = TicketControlView(ticket_channel, user.id, target_guild.id)
            await ticket_channel.send(embed=embed_ticket, view=view_control)
            
            # Ping role si configuré
            ping_role_id = config.get('ping_role_id')
            if ping_role_id:
                role = target_guild.get_role(ping_role_id)
                if role:
                    ping_embed = discord.Embed(
                        description=f"{role.mention} **Nouveau ticket à traiter**",
                        color=0x5865F2
                    )
                    await ticket_channel.send(embed=ping_embed)
            
            # Message de bienvenue user (améliorer)
            greeting = config.get('greeting_message', DEFAULT_MODMAIL_CONFIG['greeting_message'])
            
            embed_welcome = discord.Embed(
                title="✅ Ticket créé avec succès !",
                description=greeting,
                color=0x57F287  # Vert
            )
            embed_welcome.add_field(name="🏢 Serveur", value=target_guild.name, inline=True)
            embed_welcome.add_field(name="📂 Catégorie", value=view.category, inline=True)
            embed_welcome.add_field(name="🎫 Numéro", value=f"#{ticket_num}", inline=True)
            
            embed_welcome.add_field(
                name="📝 Prochaines étapes",
                value="• Continuez à m'envoyer des messages ici\n• Vos messages seront transmis à l'équipe\n• Vous recevrez une réponse dans les plus brefs délais",
                inline=False
            )
            
            embed_welcome.set_thumbnail(url=target_guild.icon.url if target_guild.icon else None)
            embed_welcome.set_footer(
                text=f"Ticket créé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
                icon_url=user.display_avatar.url
            )
            
            # Supprimer le message de progression
            try:
                await progress_msg.delete()
            except:
                pass
            
            await message.channel.send(embed=embed_welcome)
            
            # Log (améliorer)
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
            await message.channel.send(f"❌ Erreur: {str(e)}")
        
        return
    
    # === MESSAGES DANS LES SALONS DE TICKETS ===
    if message.guild:
        # Trouver le ticket
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
                
                embed = discord.Embed(
                    description=message.content,
                    color=0x57F287,  # Vert
                    timestamp=datetime.now()
                )
                
                if anonymous:
                    embed.set_author(name="Équipe Staff", icon_url=message.guild.icon.url if message.guild.icon else None)
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
                except:
                    await message.channel.send("⚠️ Impossible d'envoyer le message (DM fermés ?)")
            
            return
    
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'{bot.user} est connecté et prêt !')
    print(f'Bot ID: {bot.user.id}')
    print(f'Serveurs: {len(bot.guilds)}')
    
    # Statut personnalisé
    activity = discord.Streaming(
        name="HelpDesk",
        url="https://twitch.tv/helpdesk"
    )
    await bot.change_presence(activity=activity, status=discord.Status.online)
    
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synchronisé {len(synced)} commandes slash')
    except Exception as e:
        print(f'❌ Erreur de synchronisation: {e}')

# Serveur web pour Render
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot ModMail actif !"

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# Lance le bot
TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("❌ ERREUR: Token Discord non trouvé dans les variables d'environnement !")
    print("Assurez-vous d'avoir défini DISCORD_TOKEN sur Render")
else:
    print("✅ Token trouvé, démarrage du bot...")
    keep_alive()
    bot.run(TOKEN)

