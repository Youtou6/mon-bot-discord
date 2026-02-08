import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
import re
import json
import os

class SecurityModule(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Configuration
        self.config = {
            "anti_spam": {
                "enabled": True,
                "max_messages": 5,
                "time_window": 5,  # secondes
                "mute_duration": 300  # 5 minutes
            },
            "anti_caps": {
                "enabled": True,
                "threshold": 0.7,  # 70% de majuscules
                "min_length": 10
            },
            "anti_links": {
                "enabled": True,
                "whitelist": []
            },
            "anti_mention": {
                "enabled": True,
                "max_mentions": 5
            },
            "anti_raid": {
                "enabled": True,
                "max_joins": 5,
                "time_window": 10,  # secondes
                "account_age_hours": 24
            },
            "anti_emoji_spam": {
                "enabled": True,
                "max_emojis": 10
            },
            "file_protection": {
                "enabled": True,
                "max_files_per_min": 3,
                "blocked_extensions": [".exe", ".bat", ".scr", ".vbs", ".jar", ".com"]
            },
            "warning_system": {
                "escalation": True,
                "warn_threshold": 3,
                "mute_threshold": 5,
                "kick_threshold": 7,
                "ban_threshold": 10
            }
        }
        
        # Stockage des données
        self.user_warnings = defaultdict(int)
        self.user_messages = defaultdict(lambda: deque(maxlen=10))
        self.user_files = defaultdict(lambda: deque(maxlen=5))
        self.recent_joins = deque(maxlen=20)
        self.muted_users = {}
        self.lockdown_channels = set()
        
        # Mots interdits (chargeables depuis un fichier)
        self.load_forbidden_words()
        
        # Whitelist (rôles/utilisateurs exemptés)
        self.whitelisted_roles = set()
        self.whitelisted_users = set()
        
        # Patterns de détection
        self.invite_pattern = re.compile(r'(discord\.gg|discord\.com/invite)/[\w-]+')
        self.link_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        self.repetition_pattern = re.compile(r'(.)\1{4,}')  # Détecte aaaa, !!!!, etc.
        
        # Logs channel
        self.log_channel_id = None
        
        # Task de nettoyage
        self.cleanup_task = self.bot.loop.create_task(self.cleanup_old_data())
    
    def load_forbidden_words(self):
        """Charge les mots interdits depuis un fichier JSON"""
        try:
            if os.path.exists('forbidden_words.json'):
                with open('forbidden_words.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.forbidden_words = set(data.get('words', []))
            else:
                self.forbidden_words = {
                    # Mots par défaut
                    "connard", "salope", "pute", "merde", "fdp", "ntm", "pd", "fils de pute"
                }
                self.save_forbidden_words()
        except Exception as e:
            print(f"Erreur chargement mots interdits: {e}")
            self.forbidden_words = set()
    
    def save_forbidden_words(self):
        """Sauvegarde les mots interdits dans un fichier JSON"""
        try:
            with open('forbidden_words.json', 'w', encoding='utf-8') as f:
                json.dump({'words': list(self.forbidden_words)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Erreur sauvegarde mots interdits: {e}")
    
    def is_whitelisted(self, member: discord.Member) -> bool:
        """Vérifie si un membre est dans la whitelist"""
        if member.guild_permissions.administrator:
            return True
        if member.id in self.whitelisted_users:
            return True
        for role in member.roles:
            if role.id in self.whitelisted_roles:
                return True
        return False
    
    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        """Envoie un log dans le salon de logs"""
        if self.log_channel_id:
            channel = guild.get_channel(self.log_channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                except:
                    pass
    
    def normalize_text(self, text: str) -> str:
        """Normalise le texte pour détecter les bypasses (leet speak, accents, etc.)"""
        replacements = {
            '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '8': 'b',
            '@': 'a', '€': 'e', '$': 's', '!': 'i', '|': 'l',
            'à': 'a', 'â': 'a', 'ä': 'a', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'î': 'i', 'ï': 'i', 'ô': 'o', 'ö': 'o', 'ù': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c', 'ñ': 'n'
        }
        
        text = text.lower()
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        # Enlève les espaces et caractères spéciaux
        text = re.sub(r'[^a-z0-9]', '', text)
        return text
    
    def contains_forbidden_word(self, text: str) -> bool:
        """Vérifie si le texte contient un mot interdit"""
        normalized = self.normalize_text(text)
        for word in self.forbidden_words:
            normalized_word = self.normalize_text(word)
            if normalized_word in normalized:
                return True
        return False
    
    async def add_warning(self, member: discord.Member, reason: str) -> int:
        """Ajoute un avertissement et retourne le nombre total"""
        self.user_warnings[member.id] += 1
        warnings = self.user_warnings[member.id]
        
        # Log
        embed = discord.Embed(
            title="⚠️ Avertissement",
            description=f"{member.mention} a reçu un avertissement",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Raison", value=reason)
        embed.add_field(name="Total avertissements", value=str(warnings))
        await self.log_action(member.guild, embed)
        
        # Escalade
        if self.config["warning_system"]["escalation"]:
            if warnings >= self.config["warning_system"]["ban_threshold"]:
                await self.auto_ban(member, f"Trop d'avertissements ({warnings})")
            elif warnings >= self.config["warning_system"]["kick_threshold"]:
                await self.auto_kick(member, f"Trop d'avertissements ({warnings})")
            elif warnings >= self.config["warning_system"]["mute_threshold"]:
                await self.auto_mute(member, 3600, f"Trop d'avertissements ({warnings})")
        
        return warnings
    
    async def auto_mute(self, member: discord.Member, duration: int, reason: str):
        """Mute automatique d'un membre"""
        try:
            # Cherche le rôle "Muted" ou le crée
            muted_role = discord.utils.get(member.guild.roles, name="Muted")
            if not muted_role:
                muted_role = await member.guild.create_role(
                    name="Muted",
                    reason="Rôle de mute automatique"
                )
                # Configure les permissions pour tous les salons
                for channel in member.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False)
            
            await member.add_roles(muted_role, reason=reason)
            self.muted_users[member.id] = datetime.utcnow() + timedelta(seconds=duration)
            
            # Log
            embed = discord.Embed(
                title="🔇 Mute automatique",
                description=f"{member.mention} a été mute",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Raison", value=reason)
            embed.add_field(name="Durée", value=f"{duration}s")
            await self.log_action(member.guild, embed)
            
            # Unmute automatique
            await asyncio.sleep(duration)
            if member.id in self.muted_users:
                await member.remove_roles(muted_role, reason="Fin du mute automatique")
                del self.muted_users[member.id]
                
        except Exception as e:
            print(f"Erreur auto_mute: {e}")
    
    async def auto_kick(self, member: discord.Member, reason: str):
        """Kick automatique d'un membre"""
        try:
            await member.kick(reason=reason)
            
            embed = discord.Embed(
                title="👢 Kick automatique",
                description=f"{member.mention} a été expulsé",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Raison", value=reason)
            await self.log_action(member.guild, embed)
        except Exception as e:
            print(f"Erreur auto_kick: {e}")
    
    async def auto_ban(self, member: discord.Member, reason: str):
        """Ban automatique d'un membre"""
        try:
            await member.ban(reason=reason, delete_message_days=1)
            
            embed = discord.Embed(
                title="🔨 Ban automatique",
                description=f"{member.mention} a été banni",
                color=discord.Color.dark_red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Raison", value=reason)
            await self.log_action(member.guild, embed)
        except Exception as e:
            print(f"Erreur auto_ban: {e}")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Analyse tous les messages"""
        # Ignore bots et messages DM
        if message.author.bot or not message.guild:
            return
        
        # Ignore whitelist
        if self.is_whitelisted(message.author):
            return
        
        # Lockdown
        if message.channel.id in self.lockdown_channels:
            await message.delete()
            return
        
        # Anti-spam messages
        if self.config["anti_spam"]["enabled"]:
            self.user_messages[message.author.id].append(datetime.utcnow())
            recent_messages = [
                ts for ts in self.user_messages[message.author.id]
                if datetime.utcnow() - ts < timedelta(seconds=self.config["anti_spam"]["time_window"])
            ]
            
            if len(recent_messages) > self.config["anti_spam"]["max_messages"]:
                await message.delete()
                await self.add_warning(message.author, "Spam de messages")
                await self.auto_mute(message.author, self.config["anti_spam"]["mute_duration"], "Spam détecté")
                return
        
        # Anti-mots interdits
        if self.contains_forbidden_word(message.content):
            await message.delete()
            await self.add_warning(message.author, "Mot interdit utilisé")
            try:
                await message.author.send("⚠️ Votre message contenait un mot interdit et a été supprimé.")
            except:
                pass
            return
        
        # Anti-majuscules
        if self.config["anti_caps"]["enabled"] and len(message.content) >= self.config["anti_caps"]["min_length"]:
            caps_ratio = sum(1 for c in message.content if c.isupper()) / len(message.content)
            if caps_ratio > self.config["anti_caps"]["threshold"]:
                await message.delete()
                await self.add_warning(message.author, "Trop de majuscules")
                return
        
        # Anti-liens
        if self.config["anti_links"]["enabled"]:
            if self.invite_pattern.search(message.content) or self.link_pattern.search(message.content):
                # Vérifie whitelist
                allowed = False
                for whitelisted_link in self.config["anti_links"]["whitelist"]:
                    if whitelisted_link in message.content:
                        allowed = True
                        break
                
                if not allowed:
                    await message.delete()
                    await self.add_warning(message.author, "Lien/invitation non autorisé")
                    return
        
        # Anti-mass mention
        if self.config["anti_mention"]["enabled"]:
            mention_count = len(message.mentions) + len(message.role_mentions)
            if message.mention_everyone:
                mention_count += 10
            
            if mention_count > self.config["anti_mention"]["max_mentions"]:
                await message.delete()
                await self.add_warning(message.author, "Spam de mentions")
                await self.auto_mute(message.author, 600, "Mass mention")
                return
        
        # Anti-emoji spam
        if self.config["anti_emoji_spam"]["enabled"]:
            emoji_count = len(re.findall(r'<a?:\w+:\d+>', message.content))
            if emoji_count > self.config["anti_emoji_spam"]["max_emojis"]:
                await message.delete()
                await self.add_warning(message.author, "Spam d'emojis")
                return
        
        # Anti-répétition
        if self.repetition_pattern.search(message.content):
            await message.delete()
            await self.add_warning(message.author, "Spam de caractères")
            return
        
        # Anti-fichiers dangereux
        if message.attachments and self.config["file_protection"]["enabled"]:
            self.user_files[message.author.id].append(datetime.utcnow())
            recent_files = [
                ts for ts in self.user_files[message.author.id]
                if datetime.utcnow() - ts < timedelta(minutes=1)
            ]
            
            # Limite de fichiers par minute
            if len(recent_files) > self.config["file_protection"]["max_files_per_min"]:
                await message.delete()
                await self.add_warning(message.author, "Spam de fichiers")
                return
            
            # Extensions dangereuses
            for attachment in message.attachments:
                ext = os.path.splitext(attachment.filename)[1].lower()
                if ext in self.config["file_protection"]["blocked_extensions"]:
                    await message.delete()
                    await self.add_warning(message.author, f"Fichier dangereux détecté ({ext})")
                    return
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Détection anti-raid lors des arrivées"""
        if not self.config["anti_raid"]["enabled"]:
            return
        
        now = datetime.utcnow()
        self.recent_joins.append(now)
        
        # Compte récent
        account_age = (now - member.created_at).total_seconds() / 3600
        if account_age < self.config["anti_raid"]["account_age_hours"]:
            embed = discord.Embed(
                title="⚠️ Compte récent détecté",
                description=f"{member.mention} ({member.id})",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Âge du compte", value=f"{account_age:.1f} heures")
            await self.log_action(member.guild, embed)
        
        # Détection raid
        recent = [
            ts for ts in self.recent_joins
            if (now - ts).total_seconds() < self.config["anti_raid"]["time_window"]
        ]
        
        if len(recent) > self.config["anti_raid"]["max_joins"]:
            # RAID DÉTECTÉ !
            embed = discord.Embed(
                title="🚨 RAID DÉTECTÉ",
                description=f"{len(recent)} arrivées en {self.config['anti_raid']['time_window']}s",
                color=discord.Color.dark_red(),
                timestamp=datetime.utcnow()
            )
            await self.log_action(member.guild, embed)
            
            # Active lockdown automatique
            for channel in member.guild.text_channels:
                if channel.id not in self.lockdown_channels:
                    self.lockdown_channels.add(channel.id)
    
    async def cleanup_old_data(self):
        """Nettoie périodiquement les données anciennes"""
        while True:
            await asyncio.sleep(3600)  # Toutes les heures
            
            # Nettoie les warnings anciens (après 7 jours)
            cutoff = datetime.utcnow() - timedelta(days=7)
            # Note: pour une vraie implémentation, il faudrait stocker les timestamps
            
            # Nettoie les mutes expirés
            expired = [
                user_id for user_id, expiry in self.muted_users.items()
                if datetime.utcnow() > expiry
            ]
            for user_id in expired:
                del self.muted_users[user_id]
    
    # ============ COMMANDES ============
    
    @app_commands.command(name="mots_interdits", description="Gère la liste des mots interdits")
    @app_commands.describe(
        action="Action à effectuer (ajouter/supprimer/liste)",
        mot="Le mot à ajouter ou supprimer"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Ajouter", value="add"),
        app_commands.Choice(name="Supprimer", value="remove"),
        app_commands.Choice(name="Liste", value="list")
    ])
    async def manage_forbidden_words(self, interaction: discord.Interaction, action: str, mot: str = None):
        """Gère les mots interdits"""
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        
        if action == "add":
            if not mot:
                await interaction.response.send_message("❌ Veuillez spécifier un mot.", ephemeral=True)
                return
            
            self.forbidden_words.add(mot.lower())
            self.save_forbidden_words()
            await interaction.response.send_message(f"✅ Mot ajouté: `{mot}`", ephemeral=True)
        
        elif action == "remove":
            if not mot:
                await interaction.response.send_message("❌ Veuillez spécifier un mot.", ephemeral=True)
                return
            
            if mot.lower() in self.forbidden_words:
                self.forbidden_words.remove(mot.lower())
                self.save_forbidden_words()
                await interaction.response.send_message(f"✅ Mot supprimé: `{mot}`", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Mot non trouvé: `{mot}`", ephemeral=True)
        
        elif action == "list":
            if not self.forbidden_words:
                await interaction.response.send_message("📋 Aucun mot interdit.", ephemeral=True)
                return
            
            words_list = ", ".join(f"`{w}`" for w in sorted(self.forbidden_words))
            embed = discord.Embed(
                title="📋 Mots interdits",
                description=words_list[:4000],  # Limite Discord
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="lockdown", description="Active/désactive le lockdown sur ce salon")
    async def lockdown(self, interaction: discord.Interaction):
        """Toggle lockdown sur le salon"""
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        
        channel = interaction.channel
        
        if channel.id in self.lockdown_channels:
            self.lockdown_channels.remove(channel.id)
            await interaction.response.send_message(f"🔓 Lockdown désactivé sur {channel.mention}")
        else:
            self.lockdown_channels.add(channel.id)
            await interaction.response.send_message(f"🔒 Lockdown activé sur {channel.mention}")
    
    @app_commands.command(name="set_log_channel", description="Définit le salon de logs")
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Définit le salon de logs"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        
        self.log_channel_id = channel.id
        await interaction.response.send_message(f"✅ Salon de logs défini: {channel.mention}")
    
    @app_commands.command(name="warnings", description="Affiche les avertissements d'un utilisateur")
    async def check_warnings(self, interaction: discord.Interaction, membre: discord.Member = None):
        """Affiche les warnings d'un membre"""
        target = membre or interaction.user
        warnings = self.user_warnings.get(target.id, 0)
        
        embed = discord.Embed(
            title=f"⚠️ Avertissements de {target.display_name}",
            description=f"Total: **{warnings}** avertissements",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="reset_warnings", description="Réinitialise les avertissements d'un utilisateur")
    async def reset_warnings(self, interaction: discord.Interaction, membre: discord.Member):
        """Reset les warnings"""
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        
        if membre.id in self.user_warnings:
            del self.user_warnings[membre.id]
        
        await interaction.response.send_message(f"✅ Avertissements réinitialisés pour {membre.mention}")
    
    @app_commands.command(name="whitelist", description="Ajoute/retire un rôle de la whitelist")
    @app_commands.describe(role="Le rôle à ajouter/retirer")
    async def whitelist_role(self, interaction: discord.Interaction, role: discord.Role):
        """Gère la whitelist des rôles"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
            return
        
        if role.id in self.whitelisted_roles:
            self.whitelisted_roles.remove(role.id)
            await interaction.response.send_message(f"✅ {role.mention} retiré de la whitelist")
        else:
            self.whitelisted_roles.add(role.id)
            await interaction.response.send_message(f"✅ {role.mention} ajouté à la whitelist")

async def setup(bot):
    await bot.add_cog(SecurityModule(bot))
