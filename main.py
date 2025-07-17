import os
import discord
from discord import app_commands
from discord.ext import commands
from keep_alive import keep_alive
import random
import asyncio

token = os.environ['TOKEN_BOT_DISCORD']

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

duels = {}
EMOJIS = {"pile": "🪙", "face": "🧿"}

COMMISSION = 0.05

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

        for _ in range(10):
            await asyncio.sleep(1)
            await original_message.edit(embed=suspense_embed)

        tirage = random.choice(["pile", "face"])
        gagnant = self.joueur1 if tirage == self.choix_joueur1 else self.joueur2
        gain = int(self.montant * 2 * (1 - COMMISSION))

        result = discord.Embed(
            title="🪙 Résultat : Pile ou Face",
            description=f"Tirage : {EMOJIS[tirage]} **{tirage.upper()}**",
            color=discord.Color.green() if gagnant == self.joueur1 else discord.Color.red()
        )
        result.add_field(name="👤 Joueur 1", value=f"{self.joueur1.mention} — {EMOJIS[self.choix_joueur1]} `{self.choix_joueur1.upper()}`", inline=True)
        result.add_field(name="👤 Joueur 2", value=f"{self.joueur2.mention} — {EMOJIS[self.opposés[self.choix_joueur1]]} `{self.opposés[self.choix_joueur1].upper()}`", inline=False)
        result.add_field(name=" ", value="─" * 20, inline=False)
        result.add_field(name="🏆 Gagnant", value=f"{gagnant.mention} remporte **{gain:,} kamas** 💰 (après 5% de commission)", inline=False)

        await original_message.edit(embed=result)
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

        embed = discord.Embed(
            title="🪙 Duel Pile ou Face",
            description=(
                f"{self.joueur1.mention} a choisi : {EMOJIS[choix]} **{choix.upper()}**\n"
                f"Montant misé : **{self.montant:,} kamas** 💰\n"
                f"Commission de 5% (gain net : **{int(self.montant * 2 * (1 - COMMISSION)):,} kamas**)"
            ),
            color=discord.Color.orange()
        )
        embed.add_field(name="👤 Joueur 1", value=f"{self.joueur1.mention}", inline=True)
        embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)

        await interaction.response.edit_message(embed=embed, view=None)

        rejoindre_view = RejoindreView(message_id=None, joueur1=self.joueur1, choix_joueur1=choix, montant=self.montant)

        # 🔽 AJOUT ICI : ping membre + croupier
        role_membre = discord.utils.get(interaction.guild.roles, name="membre")
        role_croupier = discord.utils.get(interaction.guild.roles, name="croupier")

        mention_text = ""
        if role_membre:
            mention_text += f"{role_membre.mention} "
        if role_croupier:
            mention_text += f"{role_croupier.mention}"

        message = await interaction.channel.send(
            content=mention_text.strip(),
            embed=embed,
            view=rejoindre_view
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
