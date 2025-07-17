import os
import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from keep_alive import keep_alive

token = os.environ['TOKEN_BOT_DISCORD']

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

duels = {}

EMOJIS = {
    "pile": "🪙",
    "face": "🧿"
}

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
        joueur2 = interaction.user

        if joueur2.id == self.joueur1.id:
            await interaction.response.send_message("❌ Tu ne peux pas rejoindre ton propre duel.", ephemeral=True)
            return

        duel_data = duels.get(self.message_id)
        if duel_data is None:
            await interaction.response.send_message("❌ Ce duel n'existe plus ou a déjà été joué.", ephemeral=True)
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
        duel_data["joueur2"] = joueur2

        self.rejoindre.disabled = True

        self.lancer_piece_button = discord.ui.Button(
            label="🪙 Lancer la pièce", style=discord.ButtonStyle.success, custom_id="lancer_piece"
        )
        self.lancer_piece_button.callback = self.lancer_piece
        self.add_item(self.lancer_piece_button)

        embed = interaction.message.embeds[0]
        embed.set_field_at(
            index=1,
            name="👤 Joueur 2",
            value=f"{joueur2.mention}\nChoix : {EMOJIS[self.opposés[self.choix_joueur1]]} `{self.opposés[self.choix_joueur1].upper()}`",
            inline=True
        )
        embed.description = (
            f"{self.joueur1.mention} a choisi : {EMOJIS[self.choix_joueur1]} **{self.choix_joueur1.upper()}**\n"
            f"Montant : **{self.montant:,} kamas** 💰\n\n"
            f"{joueur2.mention} a rejoint le duel ! Un membre du groupe `croupier` peut lancer la pièce."
        )
        embed.color = discord.Color.blue()

        await interaction.response.edit_message(embed=embed, view=self)

    async def lancer_piece(self, interaction: discord.Interaction):
        role_croupier_found = any(role.name == "croupier" for role in interaction.user.roles)

        if not role_croupier_found:
            await interaction.response.send_message("❌ Seuls les membres du groupe `croupier` peuvent lancer la pièce.", ephemeral=True)
            return

        if self.joueur2 is None:
            await interaction.response.send_message("❌ Le joueur 2 n'a pas encore rejoint le duel.", ephemeral=True)
            return

        self.lancer_piece_button.disabled = True
        await interaction.response.edit_message(view=self)

        original_message = interaction.message

        suspense_embed = discord.Embed(
            title="🪙 La pièce est en l'air...",
            description="On croise les doigts 🤞🏻 !",
            color=discord.Color.greyple()
        )
        suspense_embed.set_image(url="https://i.makeagif.com/media/9-17-2015/b4L3kw.gif")  # animation pièce en vol
        await original_message.edit(embed=suspense_embed, view=None)

        for i in range(10, 0, -1):
            await asyncio.sleep(1)
            suspense_embed.title = f"🪙 La pièce tourne... {i}"
            await original_message.edit(embed=suspense_embed)

        resultat = random.choice(["pile", "face"])

        gagnant = self.joueur1 if resultat == self.choix_joueur1 else self.joueur2
        net_gain = int(self.montant * 2 * (1 - COMMISSION))

        result_embed = discord.Embed(
            title="🎲 Résultat du Duel Pile ou Face",
            description=(
                f"🪙 **Résultat** : {EMOJIS[resultat]} `{resultat.upper()}`"
            ),
            color=discord.Color.green() if gagnant == self.joueur1 else discord.Color.red()
        )
        result_embed.add_field(name="👤 Joueur 1", value=f"{self.joueur1.mention}\nChoix : {EMOJIS[self.choix_joueur1]} `{self.choix_joueur1.upper()}`", inline=True)
        result_embed.add_field(name="👤 Joueur 2", value=f"{self.joueur2.mention}\nChoix : {EMOJIS[self.opposés[self.choix_joueur1]]} `{self.opposés[self.choix_joueur1].upper()}`", inline=True)
        result_embed.add_field(name=" ", value="─" * 20, inline=False)
        result_embed.add_field(name="🏆 Gagnant", value=f"**{gagnant.mention}** remporte **{net_gain:,} kamas** 💰 (après 5% de commission)", inline=False)
        result_embed.set_footer(text="🪙 Duel terminé • Bonne chance pour le prochain !")

        await original_message.edit(embed=result_embed, view=None)
        duels.pop(self.message_id, None)


class PariView(discord.ui.View):
    def __init__(self, interaction, montant):
        super().__init__(timeout=180)
        self.interaction = interaction
        self.montant = montant
        self.joueur1 = interaction.user

    async def lock_in_choice(self, interaction, choix):
        if interaction.user.id != self.joueur1.id:
            await interaction.response.send_message("❌ Seul le joueur qui a lancé le duel peut choisir le pari.", ephemeral=True)
            return

        opposés = {"pile": "face", "face": "pile"}

        role_croupier = discord.utils.get(interaction.guild.roles, name="croupier")
        role_membre = discord.utils.get(interaction.guild.roles, name="membre")

        contenu_ping = ""
        if role_membre and role_croupier:
            contenu_ping = f"{role_membre.mention} {role_croupier.mention} — Un nouveau duel Pile ou Face est prêt ! Un croupier est attendu."

        embed = discord.Embed(
            title="🪙 Duel Pile ou Face",
            description=(
                f"{self.joueur1.mention} a choisi : {EMOJIS[choix]} **{choix.upper()}**\n"
                f"Montant misé : **{self.montant:,} kamas** 💰\n"
                f"Commission de 5% par joueur appliquée (Total gagné : **{int(self.montant * 2 * (1 - COMMISSION)):,} kamas**)"
            ),
            color=discord.Color.orange()
        )
        embed.add_field(name="👤 Joueur 1", value=f"{self.joueur1.mention} - {EMOJIS[choix]} {choix}", inline=True)
        embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)
        embed.set_footer(text=f"📋 Pari pris : {self.joueur1.display_name} - {EMOJIS[choix]} {choix.upper()} | Choix restant : {EMOJIS[opposés[choix]]} {opposés[choix].upper()}")

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
            "montant": self.montant,
            "choix": choix,
            "joueur2": None
        }

    @discord.ui.button(label="🪙 Pile", style=discord.ButtonStyle.primary, custom_id="pari_pile")
    async def pile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "pile")

    @discord.ui.button(label="🧿 Face", style=discord.ButtonStyle.secondary, custom_id="pari_face")
    async def face(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "face")


@bot.tree.command(name="duel", description="Lancer un duel Pile ou Face avec un montant.")
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
        description=f"{interaction.user.mention} veut lancer un duel pour **{montant:,} kamas** 💰",
        color=discord.Color.gold()
    )
    embed.add_field(name="Choix du pari", value="Clique sur un bouton ci-dessous : 🪙 Pile / 🧿 Face", inline=False)

    view = PariView(interaction, montant)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="quit", description="Annule le duel en cours que tu as lancé.")
async def quit_duel(interaction: discord.Interaction):
    duel_a_annuler = None
    for message_id, duel_data in duels.items():
        if duel_data["joueur1"].id == interaction.user.id:
            duel_a_annuler = message_id
            break

    if duel_a_annuler is None:
        await interaction.response.send_message("❌ Tu n'as aucun duel en attente à annuler.", ephemeral=True)
        return

    duels.pop(duel_a_annuler)

    try:
        message = await interaction.channel.fetch_message(duel_a_annuler)
        embed = message.embeds[0]
        embed.color = discord.Color.red()
        embed.title += " (Annulé)"
        embed.description = "⚠️ Ce duel a été annulé par son créateur."
        await message.edit(embed=embed, view=None)
    except Exception:
        pass

    await interaction.response.send_message("✅ Ton duel a bien été annulé.", ephemeral=True)


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
