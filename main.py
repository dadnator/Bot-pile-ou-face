import os
import discord
from discord import app_commands
from discord.ext import commands
from keep_alive import keep_alive
import random
import asyncio
import sqlite3
from datetime import datetime, timedelta

token = os.environ['TOKEN_BOT_DISCORD']

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

duels = {}
EMOJIS = {"pile": "🪙", "face": "🧿"}
COMMISSION = 0.05

ROULETTE_NUM_IMAGES = {
    "Pile": "https://i.imgur.com/JKbZT3L.png",
    "Face": "https://i.imgur.com/4ascC3Z.png"
}

# --- Connexion SQLite et création table ---
conn = sqlite3.connect("pile_face_stats.db")
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

class RejoindreView(discord.ui.View):
    opposés = {"pile": "face", "face": "pile"}

    def __init__(self, message_id, joueur1, choix_joueur1, montant):
        super().__init__(timeout=300)
        self.message_id = message_id
        self.joueur1 = joueur1
        self.choix_joueur1 = choix_joueur1
        self.montant = montant
        self.joueur2 = None

    @discord.ui.button(label="🎯 Rejoindre le duel", style=discord.ButtonStyle.green, custom_id="rejoindre_duel")
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.joueur1.id:
            await interaction.response.send_message("❌ Tu ne peux pas rejoindre ton propre duel.", ephemeral=True)
            return

        if any(
            data["joueur1"].id == interaction.user.id or
            (data.get("joueur2") and data["joueur2"].id == interaction.user.id)
            for data in duels.values()
        ):
            await interaction.response.send_message("❌ Tu participes déjà à un autre duel.", ephemeral=True)
            return

        self.joueur2 = interaction.user
        duels[self.message_id]["joueur2"] = self.joueur2
        self.rejoindre.disabled = True

        lancer_btn = discord.ui.Button(label="🎲 Lancer Pile ou Face", style=discord.ButtonStyle.success, custom_id="lancer_pof")
        lancer_btn.callback = self.lancer_pof
        self.add_item(lancer_btn)

        embed = interaction.message.embeds[0]
        embed.set_field_at(
            1,
            name="👤 Joueur 2",
            value=f"{self.joueur2.mention}\nChoix : {EMOJIS[self.opposés[self.choix_joueur1]]} `{self.opposés[self.choix_joueur1].upper()}`",
            inline=True
        )
        embed.description += f"\n{self.joueur2.mention} a rejoint ! Un `croupier` peut lancer le tirage."
        embed.color = discord.Color.blue()

        await interaction.response.edit_message(embed=embed, view=self)

    async def lancer_pof(self, interaction: discord.Interaction):
        if not any(role.name == "croupier" for role in interaction.user.roles):
            await interaction.response.send_message("❌ Seuls les `croupiers` peuvent lancer le tirage.", ephemeral=True)
            return

        if not self.joueur2:
            await interaction.response.send_message("❌ Le joueur 2 n’a pas encore rejoint.", ephemeral=True)
            return

        self.children[1].disabled = True
        await interaction.response.edit_message(view=self)

        original_message = await interaction.channel.fetch_message(self.message_id)

        suspense_embed = discord.Embed(
            title="🪙 Le pile ou face est en cours...",
            description="On croise les doigts 🤞🏻 !",
            color=discord.Color.greyple()
        )
        suspense_embed.set_image(url="https://www.cliqueduplateau.com/wordpress/wp-content/uploads/2015/12/flip.gif")
        await original_message.edit(embed=suspense_embed, view=None)

        for i in range(10, 0, -1):
            await asyncio.sleep(1)
            suspense_embed.title = f"🪙 Tirage en cours..."
            await original_message.edit(embed=suspense_embed)

        tirage = random.choice(["pile", "face"])
        gagnant = self.joueur1 if tirage == self.choix_joueur1 else self.joueur2
        gain = int(self.montant * 2 * (1 - COMMISSION))

        result = discord.Embed(
            title="🪙 Résultat : Pile ou Face",
            description=f"Tirage : {EMOJIS[tirage]} **{tirage.upper()}**",
            color=discord.Color.green() if gagnant == self.joueur1 else discord.Color.red()
        )

        # AJOUTE CETTE LIGNE POUR L'IMAGE DU NUMÉRO TIRÉ
        if tirage in ROULETTE_NUM_IMAGES:
            result.set_thumbnail(url=ROULETTE_NUM_IMAGES[numero])
            
        result.add_field(name="👤 Joueur 1", value=f"{self.joueur1.mention} — {EMOJIS[self.choix_joueur1]} `{self.choix_joueur1.upper()}`", inline=True)
        result.add_field(name="👤 Joueur 2", value=f"{self.joueur2.mention} — {EMOJIS[self.opposés[self.choix_joueur1]]} `{self.opposés[self.choix_joueur1].upper()}`", inline=False)

        result.add_field(name=" ", value="─" * 20, inline=False)

        result.add_field(name="💰 Montant misé", value=f"**{self.montant:,.0f}".replace(",", " ") + " kamas** par joueur", inline=False)
        result.add_field(name="🏆 **Gagnant**", value=f"**{gagnant.mention} remporte {gain:,.0f}".replace(",", " ") + " kamas 💰** *(après 5% de commission)*", inline=False)
        
        await original_message.edit(embed=result)
        
         # --- Insertion dans la base ---
        now = datetime.utcnow()
        try:
            c.execute(
                "INSERT INTO paris (joueur1_id, joueur2_id, montant, gagnant_id, date) VALUES (?, ?, ?, ?, ?)",
                (self.joueur1.id, self.joueur2.id, self.montant, gagnant.id, now)
            )
            conn.commit()
            print(f"Duel inséré : {self.joueur1.id} vs {self.joueur2.id} — gagnant: {gagnant.id}")
        except Exception as e:
            print("❌ Erreur insertion base:", e)

        duels.pop(self.message_id, None)

class ChoixPileOuFace(discord.ui.View):
    def __init__(self, interaction, montant):
        super().__init__(timeout=180)
        self.joueur1 = interaction.user
        self.interaction = interaction
        self.montant = montant

    async def lock_choice(self, interaction, choix):
    if interaction.user.id != self.joueur1.id:
        await interaction.response.send_message("❌ Tu ne peux pas faire ce choix.", ephemeral=True)
        return

    opposé = "face" if choix == "pile" else "pile"

    role_croupier = discord.utils.get(interaction.guild.roles, name="croupier")
    role_membre = discord.utils.get(interaction.guild.roles, name="membre")

    contenu_ping = ""
    if role_membre and role_croupier:
        contenu_ping = f"{role_membre.mention} {role_croupier.mention} — Un nouveau duel est prêt ! Un croupier est attendu."

    description = (
        f"{self.joueur1.mention} a choisi : {EMOJIS[choix]} **{choix.upper()}**\n"
        f"Montant misé : **{self.montant:,.0f}".replace(",", " ") + " kamas** 💰\n"
        f"Commission de 5% (gain net : **{int(self.montant * 2 * (1 - COMMISSION)):,.0f}".replace(",", " ") + " kamas**)"
    )

    embed = discord.Embed(
        title="🪙 Duel Pile ou Face",
        description=description,
        color=discord.Color.orange()
    )

    embed.add_field(name="👤 Joueur 1", value=f"{self.joueur1.mention}", inline=True)
    embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)

    await interaction.response.edit_message(view=None)

    rejoindre_view = RejoindreView(message_id=None, joueur1=self.joueur1, choix_joueur1=choix, montant=self.montant)

    message = await interaction.channel.send(
        content=contenu_ping,
        embed=embed,
        view=rejoindre_view,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

    rejoindre_view.message_id = message.id

    duels[message.id] = {
        "joueur1": self.joueur1,
        "choix": choix,
        "montant": self.montant,
        "joueur2": None
    }


    @discord.ui.button(label="🪙 Pile", style=discord.ButtonStyle.primary)
    async def pile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_choice(interaction, "pile")

    @discord.ui.button(label="🧿 Face", style=discord.ButtonStyle.secondary)
    async def face(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_choice(interaction, "face")

# Pagination pour affichage stats
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
        self.first_page.disabled = self.page == 0
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page == self.max_page
        self.last_page.disabled = self.page == self.max_page

    def get_embed(self):
        embed = discord.Embed(title="📊 Statistiques Roulette", color=discord.Color.gold())
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
                f"<:emoji_2:1399792098529509546> **Misés** : **`{mises:,.0f}`".replace(",", " ") + " kamas** | "
                f"<:emoji_2:1399792098529509546> **Gagnés** : **`{kamas_gagnes:,.0f}`".replace(",", " ") + " kamas** | "
                f"**🎯Winrate** : **`{winrate:.1f}%`** (**{victoires}**/**{total_paris}**)\n"
            )
            # Ajoute une ligne de séparation après chaque joueur sauf le dernier de la page
            if i < len(slice_entries) - 1:
                description += "─" * 20 + "\n"

        embed.description = description
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
        return embed


    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.max_page
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

# --- Commande /statsall : stats à vie ---
@bot.tree.command(name="statsall", description="Affiche les stats de roulette à vie")
async def statsall(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel) or interaction.channel.name != "pile-ou-face":
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans le salon #roulette.", ephemeral=True)
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
        await interaction.response.send_message("Aucune donnée statistique disponible.", ephemeral=True)
        return

    view = StatsView(interaction, stats)
    await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=False)


# --- Commande /mystats : stats personnelles ---
@bot.tree.command(name="mystats", description="Affiche tes statistiques de roulette personnelles.")
async def mystats(interaction: discord.Interaction):
    # Récupère l'ID de l'utilisateur qui a lancé la commande
    user_id = interaction.user.id

    # Exécute une requête SQL pour obtenir les stats de l'utilisateur
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
    
    # Récupère le résultat de la requête
    stats_data = c.fetchone()

    # Si aucune donnée n'est trouvée pour l'utilisateur
    if not stats_data:
        embed = discord.Embed(
            title="📊 Tes Statistiques Roulette",
            description="❌ Tu n'as pas encore participé à un duel. Joue ton premier duel pour voir tes stats !",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Extrait les données de la requête
    _, mises, kamas_gagnes, victoires, total_paris = stats_data
    winrate = (victoires / total_paris * 100) if total_paris > 0 else 0.0

    # Crée un embed pour afficher les statistiques
    embed = discord.Embed(
        title=f"📊 Statistiques de {interaction.user.display_name}",
        description="Voici un résumé de tes performances à la roulette.",
        color=discord.Color.gold()
    )

    # Ajoute les champs avec les statistiques
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
        await interaction.response.send_message("❌ Utilise cette commande dans #pile-ou-face.", ephemeral=True)
        return

    if montant <= 0:
        await interaction.response.send_message("❌ Le montant doit être positif.", ephemeral=True)
        return

    if any(
        data["joueur1"].id == interaction.user.id or
        (data.get("joueur2") and data["joueur2"].id == interaction.user.id)
        for data in duels.values()
    ):
        await interaction.response.send_message("❌ Tu participes déjà à un duel.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🪙 Nouveau Duel Pile ou Face",
        description=f"{interaction.user.mention} veut miser **{montant:,} kamas** 💰\nChoisis Pile ou Face :",
        color=discord.Color.gold()
    )

    view = ChoixPileOuFace(interaction, montant)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="quit", description="Annule ton duel.")
async def quit_duel(interaction: discord.Interaction):
    duel_id = next((id for id, data in duels.items() if data["joueur1"].id == interaction.user.id), None)
    if not duel_id:
        await interaction.response.send_message("❌ Aucun duel à annuler.", ephemeral=True)
        return

    duels.pop(duel_id)
    try:
        msg = await interaction.channel.fetch_message(duel_id)
        embed = msg.embeds[0]
        embed.title += " (Annulé)"
        embed.description = "⚠️ Duel annulé."
        embed.color = discord.Color.red()
        await msg.edit(embed=embed, view=None)
    except:
        pass

    await interaction.response.send_message("✅ Duel annulé.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"{bot.user} prêt !")
    try:
        await bot.tree.sync()
        print("✅ Commandes slash synchronisées.")
    except Exception as e:
        print(f"Erreur sync : {e}")

keep_alive()
bot.run(token)

