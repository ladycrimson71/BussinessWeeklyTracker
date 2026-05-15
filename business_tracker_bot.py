import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "business_tracker.json"

MANAGER_ROLES = ["🗃️Business Management"]

ARCHIVE_CHANNEL_NAME = "📁│business-archives"

STARTING_BUSINESSES = [
    "Bean Machine",
    "Cafe Corretto",
    "Cyber Garage",
    "Dreamworks",
    "Harrloom Salon",
    "High Notes",
    "Moms Pie",
    "Mystic Spells",
    "Purple Haze Garage & Grill",
    "Slut City",
    "Sweet Tooth Gelato",
    "The Cherry Popper Icecream Company",
    "Treys Bakery",
    "UwU Cafe",
    "Vanilla Unicorn",
    "Weedland Coffee Shop",
    "White Widow",
]


def default_business():
    return {
        "opened": False,
        "hosted_event": False,
        "hiring_event": False,
        "notes": "",
        "event_notes": "",
        "hiring_notes": "",
        "proof": "",
        "total_opens": 0,
        "weeks_inactive": 0,
        "days_opened": 0,
        "total_minutes_open": 0,
        "currently_open": False,
        "open_time": "",
        "last_session": ""
    }

def load_data():
    if not os.path.exists(DATA_FILE):
        data = {
            "businesses": {name: default_business() for name in STARTING_BUSINESSES},
            "archives": [],
            "last_auto_archive": "",
            "last_auto_reset": ""
        }
        save_data(data)
        return data

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    for name in STARTING_BUSINESSES:
        if name not in data["businesses"]:
            data["businesses"][name] = default_business()

    for name in data["businesses"]:
        for key, value in default_business().items():
            data["businesses"][name].setdefault(key, value)

    data.setdefault("archives", [])
    data.setdefault("last_auto_archive", "")
    data.setdefault("last_auto_reset", "")

    save_data(data)
    return data


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def is_manager(interaction: discord.Interaction):
    return any(role.name in MANAGER_ROLES for role in interaction.user.roles)


def find_business(data, business):
    for name in data["businesses"]:
        if name.lower() == business.lower():
            return name
    return None


def format_minutes(minutes):
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


def make_report(data):
    businesses = dict(sorted(data["businesses"].items()))

    lines = []

    for name, info in businesses.items():
        opened = "✅" if info.get("opened") else "❌"
        event = "✅" if info.get("hosted_event") else "❌"
        hiring = "✅" if info.get("hiring_event") else "❌"
        proof = "✅" if info.get("proof") else "❌"

        line = (
            f"**{name}**\n"
            f"{opened} Opened | {event} Event | {hiring} Hiring | {proof} Proof"
        )

        time_line = (
            f"\n📅 Days Opened: {info.get('days_opened', 0)}"
            f"\n⏰ Total Time Open: {format_minutes(info.get('total_minutes_open', 0))}"
            f"\n🟢 Currently Open: {'Yes' if info.get('currently_open') else 'No'}"
        )

        if info.get("last_session"):
            time_line += f"\n🕒 Last Session: {info['last_session']}"

        line += time_line

        notes = []

        if info.get("notes"):
            notes.append(f"📝 {info['notes']}")
        if info.get("event_notes"):
            notes.append(f"🎉 {info['event_notes']}")
        if info.get("hiring_notes"):
            notes.append(f"💼 {info['hiring_notes']}")
        if info.get("proof"):
            notes.append(f"📸 {info['proof']}")

        if notes:
            line += "\n" + "\n".join(notes)

        lines.append(line)

    return f"""
🗃️ **Business Weekly Check-In Station**
📅 **Week Saved:** {datetime.now().strftime("%B %d, %Y")}

{chr(10).join(lines)}
"""

def reset_week_data(data):
    for business, info in data["businesses"].items():
        if info["opened"]:
            info["total_opens"] += 1
            info["weeks_inactive"] = 0
        else:
            info["weeks_inactive"] += 1

        info["opened"] = False
        info["hosted_event"] = False
        info["hiring_event"] = False
        info["notes"] = ""
        info["proof"] = ""
        info["event_notes"] = ""
        info["hiring_notes"] = ""
        info["days_opened"] = 0
        info["total_minutes_open"] = 0
        info["currently_open"] = False
        info["open_time"] = ""
        info["last_session"] = ""
        info["total_opens"] = 0

    save_data(data)


class BusinessModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"Business {action}")
        self.action = action

        self.business = discord.ui.TextInput(
            label="Business Name",
            placeholder="Example: Purple Haze Garage & Grill",
            required=True
        )

        self.notes = discord.ui.TextInput(
            label="Notes / Proof",
            placeholder="Add notes, event info, hiring info, or proof link",
            required=False,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.business)
        self.add_item(self.notes)

    async def on_submit(self, interaction: discord.Interaction):
        if not is_manager(interaction):
            await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
            return

        data = load_data()
        match = find_business(data, str(self.business))

        if not match:
            await interaction.response.send_message("❌ Business not found. Use `/business_add` first.", ephemeral=True)
            return

        note_text = str(self.notes)

        if self.action == "Opened":
            info = data["businesses"][match]

            if not info.get("currently_open"):
                info["currently_open"] = True
                info["open_time"] = datetime.now().isoformat()
                info["days_opened"] += 1

            info["opened"] = True
            info["notes"] = note_text

            message = f"✅ **{match}** marked as opened and clock started."

        elif self.action == "Close":
            info = data["businesses"][match]

            if not info.get("currently_open") or not info.get("open_time"):
                await interaction.response.send_message(
                    f"⚠️ **{match}** is not currently marked open.",
                    ephemeral=True
                )
                return

            opened_at = datetime.fromisoformat(info["open_time"])
            now = datetime.now()

            minutes_open = int((now - opened_at).total_seconds() / 60)

            info["total_minutes_open"] += minutes_open
            info["currently_open"] = False
            info["open_time"] = ""
            info["last_session"] = format_minutes(minutes_open)

            message = (
                f"🔒 **{match}** closed. "
                f"Time open: **{format_minutes(minutes_open)}**."
            )

        elif self.action == "Event":
            data["businesses"][match]["hosted_event"] = True
            data["businesses"][match]["event_notes"] = note_text
            message = f"🎉 **{match}** marked as hosted an event this week."

        elif self.action == "Hiring":
            data["businesses"][match]["hiring_event"] = True
            data["businesses"][match]["hiring_notes"] = note_text
            message = f"💼 **{match}** marked as hosted a hiring/job event this week."

        elif self.action == "Proof":
            data["businesses"][match]["proof"] = note_text
            message = f"📸 Proof added for **{match}**."

        elif self.action == "Notes":
            data["businesses"][match]["notes"] = note_text
            message = f"📝 Note added for **{match}**."

        save_data(data)
        await interaction.response.send_message(message, ephemeral=True)


class BusinessPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Opened", style=discord.ButtonStyle.green, emoji="✅", custom_id="business_opened_button")
    async def opened_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BusinessModal("Opened"))

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="business_close_button")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_manager(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission to use this.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(BusinessModal("Close"))

    @discord.ui.button(label="Event", style=discord.ButtonStyle.blurple, emoji="🎉", custom_id="business_event_button")
    async def event_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BusinessModal("Event"))

    @discord.ui.button(label="Hiring", style=discord.ButtonStyle.primary, emoji="💼", custom_id="business_hiring_button")
    async def hiring_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BusinessModal("Hiring"))

    @discord.ui.button(label="Proof", style=discord.ButtonStyle.secondary, emoji="📸", custom_id="business_proof_button")
    async def proof_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BusinessModal("Proof"))

    @discord.ui.button(label="Notes", style=discord.ButtonStyle.secondary, emoji="📝", custom_id="business_notes_button")
    async def notes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BusinessModal("Notes"))

    @discord.ui.button(label="Report", style=discord.ButtonStyle.success, emoji="📊", custom_id="business_report_button")
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_manager(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission to use this.",
                ephemeral=True
            )
            return

        data = load_data()
        report = make_report(data)

        chunks = [report[i:i + 1900] for i in range(0, len(report), 1900)]

        await interaction.response.send_message(chunks[0], ephemeral=True)

        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, emoji="🔄", custom_id="business_reset_button")
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_manager(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission to use this.",
                ephemeral=True
            )
            return

        data = load_data()
        reset_week_data(data)

        await interaction.response.send_message(
            "🔄 Weekly business tracker has been reset.",
            ephemeral=True
        )

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    bot.add_view(BusinessPanel())
    await bot.tree.sync()
    auto_weekly_tasks.start()
    print(f"✅ Logged in as {bot.user}")
    print("✅ Business Tracker slash commands synced")

@tasks.loop(minutes=1)
async def auto_weekly_tasks():
    now = datetime.now()
    data = load_data()

    # Sunday 8:58 PM auto archive
    if now.weekday() == 6 and now.hour == 20 and now.minute == 58:
        today = now.strftime("%Y-%m-%d")

        if data.get("last_auto_archive") != today:
            report = make_report(data)
            data["archives"].append({
                "date": now.strftime("%Y-%m-%d %H:%M"),
                "report": report
            })
            data["last_auto_archive"] = today
            save_data(data)

            for guild in bot.guilds:
                channel = discord.utils.get(guild.text_channels, name=ARCHIVE_CHANNEL_NAME)
                if channel:
                    await channel.send(report + "\n💾 **Auto weekly report saved.**")

    # Monday 12:01 AM auto reset
    if now.weekday() == 0 and now.hour == 0 and now.minute == 1:
        today = now.strftime("%Y-%m-%d")

        if data.get("last_auto_reset") != today:
            reset_week_data(data)
            data["last_auto_reset"] = today
            save_data(data)


@bot.tree.command(name="business_list", description="Show all IC businesses and weekly status.")
async def business_list(interaction: discord.Interaction):
    data = load_data()
    report = make_report(data)

    chunks = [report[i:i + 1900] for i in range(0, len(report), 1900)]

    await interaction.response.send_message(chunks[0], ephemeral=True)

    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(name="business_opened", description="Mark a business as opened this week.")
@app_commands.describe(business="Business name", notes="Optional notes")
async def business_opened(interaction: discord.Interaction, business: str, notes: str = ""):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    match = find_business(data, business)

    if not match:
        await interaction.response.send_message("❌ Business not found. Use `/business_add` first.", ephemeral=True)
        return

    info = data["businesses"][match]

    if not info.get("currently_open"):
        info["currently_open"] = True
        info["open_time"] = datetime.now().isoformat()
        info["days_opened"] += 1

    info["opened"] = True
    info["notes"] = notes

    save_data(data)

    await interaction.response.send_message(
        f"✅ **{match}** marked as opened and clock started."
    )

@bot.tree.command(name="business_notopened", description="Mark a business as not opened this week.")
@app_commands.describe(business="Business name")
async def business_notopened(interaction: discord.Interaction, business: str):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    match = find_business(data, business)

    if not match:
        await interaction.response.send_message("❌ Business not found.", ephemeral=True)
        return

    data["businesses"][match]["opened"] = False
    data["businesses"][match]["notes"] = ""
    data["businesses"][match]["proof"] = ""
    save_data(data)

    await interaction.response.send_message(f"❌ **{match}** marked as not opened.")

@bot.tree.command(name="business_event", description="Mark a business as having hosted an event this week.")
@app_commands.describe(business="Business name", notes="Optional event notes")
async def business_event(interaction: discord.Interaction, business: str, notes: str = ""):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    match = find_business(data, business)

    if not match:
        await interaction.response.send_message("❌ Business not found.", ephemeral=True)
        return

    data["businesses"][match]["hosted_event"] = True
    data["businesses"][match]["event_notes"] = notes
    save_data(data)

    await interaction.response.send_message(f"🎉 **{match}** marked as hosted an event this week.")

@bot.tree.command(name="business_hiring", description="Mark a business as having hosted a hiring/job event this week.")
@app_commands.describe(business="Business name", notes="Optional hiring notes")
async def business_hiring(interaction: discord.Interaction, business: str, notes: str = ""):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    match = find_business(data, business)

    if not match:
        await interaction.response.send_message("❌ Business not found.", ephemeral=True)
        return

    data["businesses"][match]["hiring_event"] = True
    data["businesses"][match]["hiring_notes"] = notes
    save_data(data)

    await interaction.response.send_message(f"💼 **{match}** marked as hosted a hiring/job event this week.")

@bot.tree.command(name="business_proof", description="Add proof or screenshot link for a business.")
@app_commands.describe(business="Business name", proof="Screenshot link or proof note")
async def business_proof(interaction: discord.Interaction, business: str, proof: str):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    match = find_business(data, business)

    if not match:
        await interaction.response.send_message("❌ Business not found.", ephemeral=True)
        return

    data["businesses"][match]["proof"] = proof
    save_data(data)

    await interaction.response.send_message(f"📸 Proof added for **{match}**.")


@bot.tree.command(name="business_note", description="Add or update notes for a business.")
@app_commands.describe(business="Business name", note="Note to save")
async def business_note(interaction: discord.Interaction, business: str, note: str):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    match = find_business(data, business)

    if not match:
        await interaction.response.send_message("❌ Business not found.", ephemeral=True)
        return

    data["businesses"][match]["notes"] = note
    save_data(data)

    await interaction.response.send_message(f"📝 Note added for **{match}**.")


@bot.tree.command(name="business_stats", description="Show business activity stats.")
async def business_stats(interaction: discord.Interaction):
    data = load_data()

    sorted_businesses = sorted(
        data["businesses"].items(),
        key=lambda item: item[1].get("total_opens", 0),
        reverse=True
    )

    lines = [
        f"📊 **{name}** — {info.get('total_opens', 0)} weekly opens"
        for name, info in sorted_businesses
    ]

    await interaction.response.send_message(
        "📊 **Business Activity Stats**\n\n" + "\n".join(lines)
    )


@bot.tree.command(name="business_inactive", description="Show businesses inactive for 2+ weeks.")
async def business_inactive(interaction: discord.Interaction):
    data = load_data()

    inactive = [
        f"⚠️ **{name}** — {info.get('weeks_inactive', 0)} weeks inactive"
        for name, info in sorted(data["businesses"].items())
        if info.get("weeks_inactive", 0) >= 2
    ]

    await interaction.response.send_message(
        "⚠️ **Inactive Businesses**\n\n" + ("\n".join(inactive) if inactive else "No businesses inactive for 2+ weeks.")
    )


@bot.tree.command(name="business_add", description="Add a new IC business to the tracker.")
@app_commands.describe(business="New business name")
async def business_add(interaction: discord.Interaction, business: str):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()

    if find_business(data, business):
        await interaction.response.send_message("⚠️ That business is already on the list.", ephemeral=True)
        return

    data["businesses"][business] = default_business()
    data["businesses"][business]["notes"] = "➕ New IC business added"
    data["businesses"] = dict(sorted(data["businesses"].items()))
    save_data(data)

    await interaction.response.send_message(f"➕ **{business}** added to the weekly tracker.")


@bot.tree.command(name="business_remove", description="Remove a business from the tracker.")
@app_commands.describe(business="Business name")
async def business_remove(interaction: discord.Interaction, business: str):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    match = find_business(data, business)

    if not match:
        await interaction.response.send_message("❌ Business not found.", ephemeral=True)
        return

    del data["businesses"][match]
    save_data(data)

    await interaction.response.send_message(f"🗑️ **{match}** removed from the tracker.")


@bot.tree.command(name="business_report", description="Save and post this week's business report.")
async def business_report(interaction: discord.Interaction):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    report = make_report(data)

    data["archives"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "report": report
    })
    save_data(data)

    await interaction.response.send_message(report + "\n💾 **This weekly report has been saved.**")

@bot.tree.command(name="business_panel", description="Post the business management button panel.")
async def business_panel(interaction: discord.Interaction):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🗃️ Business Weekly Check-In Station",
        description=(
            "Use the buttons below to update weekly business activity.\n\n"
            "✅ **Opened** — Mark a business as opened\n"
            "🎉 **Event** — Mark a business event\n"
            "💼 **Hiring** — Mark a hiring/job event\n"
            "📸 **Proof** — Add screenshot/proof link\n"
            "📝 **Notes** — Add notes\n"
            "📊 **Report** — View weekly checklist\n"
            "🔄 **Reset** — Reset the week"
        ),
        color=discord.Color.purple()
    )

    embed.set_footer(text="Business Weekly Check Ins")

    await interaction.response.send_message(embed=embed, view=BusinessPanel())

@bot.tree.command(name="business_resetweek", description="Reset all businesses for a new week.")
async def business_resetweek(interaction: discord.Interaction):
    if not is_manager(interaction):
        await interaction.response.send_message("❌ You do not have permission to use this.", ephemeral=True)
        return

    data = load_data()
    reset_week_data(data)

    await interaction.response.send_message("🔄 Weekly business tracker has been reset.")

bot.run(TOKEN)
