import os
import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from keep_alive import keep_alive
import sqlite3
from datetime import datetime

token = os.environ['TOKEN_BOT_DISCORD']

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

duels = {}

EMOJIS = {
    "pile": "🪙",
    "face": "🪙"
}

COMMISSION = 0.05

POF_IMAGES = {
    "suspense": "https://i.makeagif.com/media/11-22-2017/gXYMAo.gif",
    "pile": "https://i.imgur.com/8fGg6E1.png", 
    "face": "https://i.imgur.com/k9b62fU.png"  
}

conn = sqlite3.connect("pile_ou_face_stats.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS paris (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    joueur1_id INTEGER NOT NULL,
    joueur2_id INTEGER NOT NULL,
    montant INTEGER NOT NULL,
    gagnant_id INTEGER NOT NULL,
    date TIMESTAMP NOT NULL
)
""")
conn.commit()

async def lancer_le_pile_ou_face(interaction, duel_data, message_id_final):
    joueur1 = duel_data["joueur1"]
    joueur2 = duel_data["joueur2"]
    choix_joueur1 = duel_data["valeur"]
    montant = duel_data["montant"]
    croupier = interaction.user

    suspense_embed = discord.Embed(
        title="🪙 Le pièce tourne...",
        description="On croise les doigts 🤞🏻 !",
        color=discord.Color.greyple()
    )
    suspense_embed.set_image(url=POF_IMAGES["suspense"])
    
    original_message = await interaction.channel.send(embed=suspense_embed)

    for i in range(5, 0, -1):
        await asyncio.sleep(1)
        suspense_embed.title = f"🪙 Tirage en cours ..."
        await original_message.edit(embed=suspense_embed)

    await asyncio.sleep(1)

    resultat = random.choice(["pile", "face"])
    opposés = {"pile": "face", "face": "pile"}

    choix_joueur2 = opposés[choix_joueur1]
    gagnant = joueur1 if resultat == choix_joueur1 else joueur2
    net_gain = int(montant * 2 * (1 - COMMISSION))

    result_embed = discord.Embed(
        title="🎲 Résultat du Duel Pile ou Face",
        description=(
            f"🎯 **Résultat** : `{resultat.upper()}`\n"
        ),
        color=discord.Color.green() if gagnant == joueur1 else discord.Color.red()
    )

    if resultat in POF_IMAGES:
        result_embed.set_thumbnail(url=POF_IMAGES[resultat])

    result_embed.add_field(name="👤 Joueur 1", value=f"{joueur1.mention}\nChoix : {EMOJIS[choix_joueur1]} `{choix_joueur1.upper()}`", inline=True)
    result_embed.add_field(name="👤 Joueur 2", value=f"{joueur2.mention}\nChoix : {EMOJIS[choix_joueur2]} `{choix_joueur2.upper()}`", inline=True)
    result_embed.add_field(name=" ", value="─" * 20, inline=False)
    
    result_embed.add_field(name="💰 Montant misé", value=f"**{montant:,}".replace(",", "\u00A0") + "\u00A0kamas** par joueur", inline=False)
    result_embed.add_field(name="🏆 Gagnant", value=f"**{gagnant.mention}** remporte **{net_gain:,}".replace(",", "\u00A0") + "\u00A0kamas** 💰 (après 5% de commission)", inline=False)
    
    result_embed.set_footer(text="🪙 Duel terminé • Bonne chance pour le prochain !")
    
    await interaction.channel.send(embed=result_embed)

    try:
        old_message_with_buttons = await interaction.channel.fetch_message(message_id_final)
        await old_message_with_buttons.delete()
    except discord.NotFound:
        pass

    try:
        await original_message.delete()
    except discord.NotFound:
        pass

    now = datetime.utcnow()
    try:
        c.execute(
            "INSERT INTO paris (joueur1_id, joueur2_id, montant, gagnant_id, date) VALUES (?, ?, ?, ?, ?)",
            (joueur1.id, joueur2.id, montant, gagnant.id, now)
        )
        conn.commit()
    except Exception as e:
        print("❌ Erreur insertion base:", e)

    duels.pop(duel_data["message_id_initial"], None)

# --- Vues Discord ---
class RejoindreView(discord.ui.View):
    opposés = {"pile": "face", "face": "pile"}

    def __init__(self, message_id, joueur1, valeur_choisie, montant):
        super().__init__(timeout=None)
        self.message_id_initial = message_id
        self.joueur1 = joueur1
        self.valeur_choisie = valeur_choisie
        self.montant = montant
        self.joueur2 = None
        self.croupier = None
        
        self.rejoindre_croupier_button = None
        self.lancer_pof_button = None

    @discord.ui.button(label="🎯 Rejoindre le duel", style=discord.ButtonStyle.green, custom_id="rejoindre_duel_pof")
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        joueur2 = interaction.user
        
        if joueur2.id == self.joueur1.id:
            await interaction.response.send_message("❌ Tu ne peux pas rejoindre ton propre duel.", ephemeral=True)
            return

        for data in duels.values():
            if data["joueur1"].id == joueur2.id or (
                "joueur2" in data and data["joueur2"] and data["joueur2"].id == joueur2.id
            ):
                await interaction.response.send_message(
                    "❌ Tu participes déjà à un autre duel. Termine-le avant d’en rejoindre un autre.",
                    ephemeral=True
                )
                return

        self.joueur2 = joueur2
        duel_data = duels.get(self.message_id_initial)
        duel_data["joueur2"] = joueur2
        
        self.rejoindre.disabled = True
        
        if not self.rejoindre_croupier_button:
            self.rejoindre_croupier_button = discord.ui.Button(
                label="🎲 Rejoindre en tant que Croupier", style=discord.ButtonStyle.secondary, custom_id="rejoindre_croupier_pof"
            )
            self.rejoindre_croupier_button.callback = self.rejoindre_croupier
            self.add_item(self.rejoindre_croupier_button)

        embed = interaction.message.embeds[0]
        embed.title = f"Duel entre {self.joueur1.display_name} et {self.joueur2.display_name}"
        
        valeur_joueur2 = self.opposés[self.valeur_choisie]
        
        embed.set_field_at(1, name="👤 Joueur 2", value=f"{self.joueur2.mention} - {EMOJIS[valeur_joueur2]} `{valeur_joueur2.upper()}`", inline=True)
        embed.set_field_at(2, name="Status", value="🎲 Un croupier est attendu pour lancer le duel.", inline=False)
        embed.set_footer(text="Cliquez sur le bouton pour rejoindre en tant que croupier.")
        
        role_croupier = discord.utils.get(interaction.guild.roles, name="croupier")
        contenu_ping = ""
        if role_croupier:
            contenu_ping = f"{role_croupier.mention} — Un nouveau duel est prêt ! Un croupier est attendu."
        
        await interaction.response.edit_message(
            content=contenu_ping,
            embed=embed,
            view=self,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )


    async def rejoindre_croupier(self, interaction: discord.Interaction):
        role_croupier = discord.utils.get(interaction.guild.roles, name="croupier")

        if not role_croupier or role_croupier not in interaction.user.roles:
            await interaction.response.send_message("❌ Tu n'as pas le rôle de `croupier` pour rejoindre ce duel.", ephemeral=True)
            return

        if self.croupier:
            await interaction.response.send_message(f"❌ Un croupier ({self.croupier.mention}) a déjà rejoint le duel.", ephemeral=True)
            return
            
        self.croupier = interaction.user
        duel_data = duels.get(self.message_id_initial)
        duel_data["croupier"] = self.croupier

        embed = interaction.message.embeds[0]
        
        embed.set_field_at(2, name="Status", value=f"✅ Prêt à jouer ! Croupier : {self.croupier.mention}", inline=False)
        embed.set_footer(text="Le croupier peut lancer la partie.")
        
        self.rejoindre_croupier_button.disabled = True
        
        if not self.lancer_pof_button:
            self.lancer_pof_button = discord.ui.Button(
                label="🪙 Lancer le pile ou face", style=discord.ButtonStyle.success, custom_id="lancer_pof_button"
            )
            self.lancer_pof_button.callback = self.lancer_pof
            self.add_item(self.lancer_pof_button)
        
        await interaction.response.edit_message(content="", embed=embed, view=self)


    async def lancer_pof(self, interaction: discord.Interaction):
        duel_data = duels.get(self.message_id_initial)
        
        if not duel_data or not duel_data.get("joueur2"):
            await interaction.response.send_message("❌ Le duel n'est pas prêt. Il faut deux joueurs.", ephemeral=True)
            return
        
        if interaction.user.id != self.croupier.id:
            await interaction.response.send_message("❌ Seul le croupier peut lancer la pièce.", ephemeral=True)
            return
        
        await interaction.response.defer()

        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
        
        await lancer_le_pile_ou_face(interaction, duel_data, interaction.message.id)

class PariView(discord.ui.View):
    def __init__(self, interaction, montant):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.montant = montant
        self.joueur1 = interaction.user

    async def lock_in_choice(self, interaction, valeur):
        if interaction.user.id != self.joueur1.id:
            await interaction.response.send_message("❌ Seul le joueur qui a lancé le duel peut choisir le pari.", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(
            content=f"✅ Pari choisi : **{EMOJIS[valeur]} {valeur.upper()}** pour **{self.montant:,}".replace(",", " ") + " kamas**. Le duel est en cours de création...",
            embed=None,
            view=self
        )

        opposés = {"pile": "face", "face": "pile"}
        choix_restant = opposés[valeur]

        public_embed = discord.Embed(
            title=f"🪙 Duel Pile ou Face en attente de joueur",
            description=(
                f"{self.joueur1.mention} a choisi : {EMOJIS[valeur]} **{valeur.upper()}** \n"
                f"Montant misé : **{self.montant:,}".replace(",", " ") + " kamas** 💰"
            ),
            color=discord.Color.orange()
        )
        public_embed.add_field(name="👤 Joueur 1", value=f"{self.joueur1.mention} - {EMOJIS[valeur]} `{valeur.upper()}`", inline=True)
        public_embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)
        public_embed.add_field(name="Status", value="🎯 En attente d'un second joueur.", inline=False)
        public_embed.set_footer(text=f"📋 Pari pris : {self.joueur1.display_name} - {EMOJIS[valeur]} {valeur.upper()} | Choix restant : {EMOJIS[choix_restant]} {choix_restant.upper()}")

        public_rejoindre_view = RejoindreView(message_id=None, joueur1=self.joueur1, valeur_choisie=valeur, montant=self.montant)
        
        role_membre = discord.utils.get(interaction.guild.roles, name="membre")
        contenu_ping = ""
        if role_membre:
            contenu_ping = f"{role_membre.mention} — Un nouveau duel est prêt ! Un joueur est attendu."
        
        public_message = await interaction.followup.send(
            content=contenu_ping,
            embed=public_embed,
            view=public_rejoindre_view,
            ephemeral=False,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )

        public_rejoindre_view.message_id_initial = public_message.id

        duels[public_message.id] = {
            "joueur1": self.joueur1,
            "montant": self.montant,
            "valeur": valeur,
            "joueur2": None,
            "croupier": None,
            "message_id_initial": public_message.id
        }

    @discord.ui.button(label="🪙 Pile", style=discord.ButtonStyle.secondary, custom_id="pari_pile_pof")
    async def pile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "pile")

    @discord.ui.button(label="🪙 Face", style=discord.ButtonStyle.secondary, custom_id="pari_face_pof")
    async def face(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "face")

class StatsView(discord.ui.View):
    def __init__(self, ctx, entries, page=0):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.entries = entries
        self.page = page
        self.entries_per_page = 10
        self.max_page = (len(entries) - 1) // self.entries_per_page
        self.update_buttons()

    def update_buttons(self):
        for button in self.children:
            if button.custom_id == "first_page_pof":
                button.disabled = self.page == 0
            elif button.custom_id == "prev_page_pof":
                button.disabled = self.page == 0
            elif button.custom_id == "next_page_pof":
                button.disabled = self.page == self.max_page
            elif button.custom_id == "last_page_pof":
                button.disabled = self.page == self.max_page

    def get_embed(self):
        embed = discord.Embed(title="📊 Statistiques Pile ou Face", color=discord.Color.gold())
        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        slice_entries = self.entries[start:end]

        if not slice_entries:
            embed.description = "Aucune donnée à afficher."
            return embed

        description = ""
        for i, (user_id, mises, kamas_gagnes, victoires, winrate, total_paris) in enumerate(slice_entries):
            rank = self.page * self.entries_per_page + i + 1
            description += (
                f"**#{rank}** <@{user_id}> — "
                f"🪙 **Misés** : **`{mises:,.0f}`".replace(",", " ") + " kamas** | "
                f"💰 **Gagnés** : **`{kamas_gagnes:,.0f}`".replace(",", " ") + " kamas** | "
                f"**🎯Winrate** : **`{winrate:.1f}%`** (**{victoires}**/**{total_paris}**)\n"
            )
            if i < len(slice_entries) - 1:
                description += "─" * 20 + "\n"

        embed.description = description
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
        return embed

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary, custom_id="first_page_pof")
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary, custom_id="prev_page_pof")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary, custom_id="next_page_pof")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary, custom_id="last_page_pof")
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

@bot.tree.command(name="statsall", description="Affiche les statistiques de tous les joueurs au Pile ou Face.")
async def statsall(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or interaction.channel.name != "pile-ou-face":
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon de jeu pile ou face.", ephemeral=True)
        return

    c.execute("""
    SELECT joueur_id,
            SUM(montant) as total_mise,
            SUM(CASE WHEN gagnant_id = joueur_id THEN montant * 2 * 0.95 ELSE 0 END) as kamas_gagnes,
            SUM(CASE WHEN gagnant_id = joueur_id THEN 1 ELSE 0 END) as victoires,
            COUNT(*) as total_paris
    FROM (
        SELECT joueur1_id as joueur_id, montant, gagnant_id FROM paris
        UNION ALL
        SELECT joueur2_id as joueur_id, montant, gagnant_id FROM paris
    )
    GROUP BY joueur_id
    """)
    data = c.fetchall()

    stats = []
    for user_id, mises, kamas_gagnes, victoires, total_paris in data:
        winrate = (victoires / total_paris * 100) if total_paris > 0 else 0.0
        stats.append((user_id, mises, kamas_gagnes, victoires, winrate, total_paris))

    stats.sort(key=lambda x: x[2], reverse=True)

    if not stats:
        await interaction.response.send_message("Aucune donnée statistique disponible pour le Pile ou Face.", ephemeral=True)
        return

    view = StatsView(interaction, stats)
    await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=False)

@bot.tree.command(name="mystats", description="Affiche tes statistiques personnelles au Pile ou Face.")
async def mystats(interaction: discord.Interaction):
    user_id = interaction.user.id
    if not isinstance(interaction.channel, discord.TextChannel) or interaction.channel.name != "pile-ou-face":
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon de jeu pile ou face.", ephemeral=True)
        return

    c.execute("""
    SELECT joueur_id,
            SUM(montant) as total_mise,
            SUM(CASE WHEN gagnant_id = joueur_id THEN montant * 2 * 0.95 ELSE 0 END) as kamas_gagnes,
            SUM(CASE WHEN gagnant_id = joueur_id THEN 1 ELSE 0 END) as victoires,
            COUNT(*) as total_paris
    FROM (
        SELECT joueur1_id as joueur_id, montant, gagnant_id FROM paris
        UNION ALL
        SELECT joueur2_id as joueur_id, montant, gagnant_id FROM paris
    )
    WHERE joueur_id = ?
    GROUP BY joueur_id
    """, (user_id,))
    
    stats_data = c.fetchone()

    if not stats_data:
        embed = discord.Embed(
            title="📊 Tes Statistiques Pile ou Face",
            description="❌ Tu n'as pas encore participé à un duel. Joue ton premier duel pour voir tes stats !",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    _, mises, kamas_gagnes, victoires, total_paris = stats_data
    winrate = (victoires / total_paris * 100) if total_paris > 0 else 0.0

    embed = discord.Embed(
        title=f"📊 Statistiques de {interaction.user.display_name}",
        description="Voici un résumé de tes performances au Pile ou Face.",
        color=discord.Color.gold()
    )

    embed.add_field(name="Total misé", value=f"**{mises:,.0f}".replace(",", " ") + " kamas**", inline=False)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Total gagné", value=f"**{kamas_gagnes:,.0f}".replace(",", " ") + " kamas**", inline=False)
    embed.add_field(name=" ", value="─" * 20, inline=False)
    embed.add_field(name="Duels joués", value=f"**{total_paris}**", inline=True)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Victoires", value=f"**{victoires}**", inline=True)
    embed.add_field(name=" ", value="─" * 3, inline=False)
    embed.add_field(name="Taux de victoire", value=f"**{winrate:.1f}%**", inline=False)

    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.set_footer(text="Bonne chance pour tes prochains duels !")

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="duel", description="Lancer un duel pile ou face avec un montant.")
@app_commands.describe(montant="Montant misé en kamas")
async def duel(interaction: discord.Interaction, montant: int):
    if not isinstance(interaction.channel, discord.TextChannel) or interaction.channel.name != "pile-ou-face":
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon #pile-ou-face.", ephemeral=True)
        return

    if montant <= 0:
        await interaction.response.send_message("❌ Le montant doit être supérieur à 0.", ephemeral=True)
        return

    for duel_data in duels.values():
        if duel_data["joueur1"].id == interaction.user.id or (
            "joueur2" in duel_data and duel_data["joueur2"] and duel_data["joueur2"].id == interaction.user.id
        ):
            await interaction.response.send_message(
                "❌ Tu participes déjà à un autre duel. Termine-le ou utilise `/quit` pour l'annuler.",
                ephemeral=True
            )
            return

    embed = discord.Embed(
        title="🪙 Nouveau Duel Pile ou Face",
        description=f"Choisis ton pari pour **{montant:,}".replace(",", " ") + " kamas** 💰",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Ce message n'est visible que par toi.")

    view = PariView(interaction, montant)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="quit", description="Annule le duel en cours que tu as lancé.")
async def quit_duel(interaction: discord.Interaction):
    duel_a_annuler_id = None
    is_joueur2 = False

    for message_id, duel_data in duels.items():
        if duel_data["joueur1"].id == interaction.user.id:
            duel_a_annuler_id = message_id
            break
    
    if not duel_a_annuler_id:
        for message_id, duel_data in duels.items():
            if "joueur2" in duel_data and duel_data["joueur2"] and duel_data["joueur2"].id == interaction.user.id:
                duel_a_annuler_id = message_id
                is_joueur2 = True
                break

    if duel_a_annuler_id is None:
        await interaction.response.send_message("❌ Tu n'as aucun duel en attente à annuler.", ephemeral=True)
        return

    if not is_joueur2:
        duel_data = duels.pop(duel_a_annuler_id)
        try:
            message_initial = await interaction.channel.fetch_message(duel_a_annuler_id)
            embed_initial = message_initial.embeds[0]
            embed_initial.color = discord.Color.red()
            embed_initial.title += " (Annulé)"
            embed_initial.description = "⚠️ Ce duel a été annulé par son créateur."
            await message_initial.edit(embed=embed_initial, view=None)
        except Exception:
            pass
        await interaction.response.send_message("✅ Ton duel a bien été annulé.", ephemeral=True)
    else:
        duel_data = duels.pop(duel_a_annuler_id)
        try:
            message_initial = await interaction.channel.fetch_message(duel_a_annuler_id)
            joueur1 = duel_data["joueur1"]
            montant = duel_data["montant"]
            valeur_choisie = duel_data["valeur"]
            
            opposés = {"pile": "face", "face": "pile"}
            choix_restant = opposés[valeur_choisie]

            new_embed = discord.Embed(
                title=f"🪙 Duel Pile ou Face en attente de joueur",
                description=(
                    f"{joueur1.mention} a choisi : {EMOJIS[valeur_choisie]} **{valeur_choisie.upper()}** \n"
                    f"Montant misé : **{montant:,}".replace(",", " ") + " kamas** 💰"
                ),
                color=discord.Color.orange()
            )
            new_embed.add_field(name="👤 Joueur 1", value=f"{joueur1.mention} - {EMOJIS[valeur_choisie]} `{valeur_choisie.upper()}`", inline=True)
            new_embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)
            new_embed.add_field(name="Status", value="🎯 En attente d'un second joueur.", inline=False)
            new_embed.set_footer(text=f"📋 Pari pris : {joueur1.display_name} - {EMOJIS[valeur_choisie]} {valeur_choisie.upper()} | Choix restant : {EMOJIS[choix_restant]} {choix_restant.upper()}")
            
            new_view = RejoindreView(message_id=message_initial.id, joueur1=joueur1, valeur_choisie=valeur_choisie, montant=montant)
            
            duels[message_initial.id] = {
                "joueur1": joueur1,
                "montant": montant,
                "valeur": valeur_choisie,
                "joueur2": None,
                "croupier": None,
                "message_id_initial": message_initial.id
            }

            role_membre = discord.utils.get(interaction.guild.roles, name="membre")
            contenu_ping = ""
            if role_membre:
                contenu_ping = f"{role_membre.mention} — Un nouveau duel est prêt ! Un joueur est attendu."

            await message_initial.edit(content=contenu_ping, embed=new_embed, view=new_view, allowed_mentions=discord.AllowedMentions(roles=True))
            await interaction.response.send_message("✅ Tu as quitté le duel. Le créateur attend maintenant un autre joueur.", ephemeral=True)
        except Exception as e:
            print(f"Erreur lors de l'annulation du duel par joueur2: {e}")
            await interaction.response.send_message("❌ Une erreur s'est produite lors de l'annulation du duel.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"{bot.user} est prêt !")
    try:
        await bot.tree.sync()
        print("✅ Commandes synchronisées.")
    except Exception as e:
        print(f"Erreur : {e}")

keep_alive()
bot.run(token)
