# Dynamic Commands Tutorial

This tutorial will show you how to update bot commands dynamically at runtime, creating responsive bots that adapt to user actions and system events.

## 🎯 What We'll Build

A dynamic bot that:
- Updates commands based on user actions
- Responds to system events
- Manages command state transitions
- Provides real-time command updates

## 📋 Prerequisites

- Completed [Basic Setup Tutorial](basic-setup.md)
- Understanding of [Advanced Profiles](advanced-profiles.md)
- Basic knowledge of event-driven programming

## 🚀 Step 1: Basic Dynamic Updates

Let's start with a simple bot that updates commands based on user actions:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram_cmds import CommandScopeManager, CmdsConfig, CommandDef, ProfileDef, ScopeDef
from aiogram_cmds import ProfileResolver, Flags
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# User state management
user_states = {
    # user_id: {"registered": bool, "premium": bool, "in_game": bool, "last_action": int}
}

def get_user_state(user_id: int) -> dict:
    """Get user state from memory."""
    return user_states.get(user_id, {
        "registered": False,
        "premium": False,
        "in_game": False,
        "last_action": 0
    })

def update_user_state(user_id: int, updates: dict):
    """Update user state."""
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id].update(updates)
    user_states[user_id]["last_action"] = int(time.time())

async def update_user_commands(user_id: int):
    """Update commands for a specific user."""
    state = get_user_state(user_id)
    
    manager = CommandScopeManager(bot)
    await manager.update_user_commands(
        user_id=user_id,
        is_registered=state["registered"],
        has_vehicle=state["premium"],
        user_language="en"
    )
    
    logger.info(f"Updated commands for user {user_id}: {state}")

async def on_startup():
    """Set up initial commands."""
    config = CmdsConfig(
        languages=["en"],
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "register": CommandDef(i18n_key="register.desc"),
            "profile": CommandDef(i18n_key="profile.desc"),
            "game": CommandDef(i18n_key="game.desc"),
            "shop": CommandDef(i18n_key="shop.desc"),
            "inventory": CommandDef(i18n_key="inventory.desc"),
            "premium": CommandDef(i18n_key="premium.desc"),
        },
        profiles={
            "guest": ProfileDef(include=["start", "help", "register"]),
            "user": ProfileDef(include=["start", "help", "profile", "game", "shop"]),
            "gamer": ProfileDef(include=["start", "help", "profile", "game", "shop", "inventory"]),
            "premium": ProfileDef(include=["start", "help", "profile", "game", "shop", "inventory", "premium"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
    )
    
    def dynamic_profile_resolver(flags: Flags) -> str:
        user_id = getattr(flags, 'user_id', None)
        if not user_id:
            return "guest"
        
        state = get_user_state(user_id)
        
        if state["premium"]:
            return "premium"
        elif state["in_game"]:
            return "gamer"
        elif state["registered"]:
            return "user"
        else:
            return "guest"
    
    manager = CommandScopeManager(bot, config=config, profile_resolver=dynamic_profile_resolver)
    await manager.setup_all()
    
    logger.info("✅ Bot started with dynamic commands!")

# Message handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer(
            "👋 Welcome to the Dynamic Bot!\n\n"
            "Use /register to create an account and unlock more commands."
        )
    else:
        await message.answer(
            f"👋 Welcome back!\n\n"
            f"Your current status:\n"
            f"• Registered: {'✅' if state['registered'] else '❌'}\n"
            f"• Premium: {'🌟' if state['premium'] else '❌'}\n"
            f"• In Game: {'🎮' if state['in_game'] else '❌'}\n\n"
            f"Use /help to see your available commands."
        )

@dp.message(Command("register"))
async def handle_register(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if state["registered"]:
        await message.answer("✅ You are already registered!")
        return
    
    # Simulate registration process
    await message.answer("🔄 Registering...")
    
    # Update user state
    update_user_state(user_id, {"registered": True})
    
    # Update commands
    await update_user_commands(user_id)
    
    await message.answer(
        "🎉 Registration successful!\n\n"
        "Your commands have been updated. You now have access to:\n"
        "• /profile - View your profile\n"
        "• /game - Start playing\n"
        "• /shop - Browse items"
    )

@dp.message(Command("game"))
async def handle_game(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    if state["in_game"]:
        await message.answer("🎮 You are already in a game! Use /inventory to check your items.")
        return
    
    # Start game
    update_user_state(user_id, {"in_game": True})
    await update_user_commands(user_id)
    
    await message.answer(
        "🎮 Game started!\n\n"
        "You now have access to:\n"
        "• /inventory - View your items\n"
        "• /shop - Buy new items\n\n"
        "Type 'exit' to leave the game."
    )

@dp.message(Command("inventory"))
async def handle_inventory(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["in_game"]:
        await message.answer("❌ You are not in a game. Use /game to start playing.")
        return
    
    await message.answer(
        "🎒 Your Inventory:\n\n"
        "• Sword of Power (Level 5)\n"
        "• Health Potion x3\n"
        "• Magic Scroll x1\n"
        "• Gold: 150 coins"
    )

@dp.message(Command("shop"))
async def handle_shop(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    shop_msg = "🛍️ Shop:\n\n"
    shop_msg += "1. Health Potion - 50 gold\n"
    shop_msg += "2. Magic Scroll - 100 gold\n"
    shop_msg += "3. Premium Sword - 500 gold\n"
    shop_msg += "4. Premium Armor - 1000 gold\n\n"
    
    if not state["premium"]:
        shop_msg += "🌟 Upgrade to premium for exclusive items!"
    
    await message.answer(shop_msg)

@dp.message(Command("premium"))
async def handle_premium(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    if state["premium"]:
        await message.answer("🌟 You are already a premium member!")
        return
    
    # Simulate premium upgrade
    await message.answer("💳 Processing premium upgrade...")
    
    update_user_state(user_id, {"premium": True})
    await update_user_commands(user_id)
    
    await message.answer(
        "🌟 Premium upgrade successful!\n\n"
        "You now have access to:\n"
        "• Exclusive premium items in /shop\n"
        "• Priority support\n"
        "• Special commands"
    )

@dp.message(Command("profile"))
async def handle_profile(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    profile_msg = f"👤 Your Profile:\n\n"
    profile_msg += f"ID: {user_id}\n"
    profile_msg += f"Registered: {'✅' if state['registered'] else '❌'}\n"
    profile_msg += f"Premium: {'🌟' if state['premium'] else '❌'}\n"
    profile_msg += f"In Game: {'🎮' if state['in_game'] else '❌'}\n"
    profile_msg += f"Last Action: {time.ctime(state['last_action'])}"
    
    await message.answer(profile_msg)

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    help_msg = "📋 Available commands:\n\n"
    
    if not state["registered"]:
        help_msg += "• /start - Start the bot\n"
        help_msg += "• /register - Create account\n"
        help_msg += "• /help - Show this help"
    elif state["premium"]:
        help_msg += "🌟 Premium Commands:\n"
        help_msg += "• /premium - Premium features\n\n"
        help_msg += "🎮 Game Commands:\n"
        help_msg += "• /game - Start/stop game\n"
        help_msg += "• /inventory - View items\n"
        help_msg += "• /shop - Browse items\n\n"
        help_msg += "👤 User Commands:\n"
        help_msg += "• /profile - Your profile\n"
        help_msg += "• /help - Show this help"
    elif state["in_game"]:
        help_msg += "🎮 Game Commands:\n"
        help_msg += "• /game - Stop game\n"
        help_msg += "• /inventory - View items\n"
        help_msg += "• /shop - Browse items\n\n"
        help_msg += "👤 User Commands:\n"
        help_msg += "• /profile - Your profile\n"
        help_msg += "• /premium - Upgrade to premium\n"
        help_msg += "• /help - Show this help"
    else:
        help_msg += "👤 User Commands:\n"
        help_msg += "• /profile - Your profile\n"
        help_msg += "• /game - Start playing\n"
        help_msg += "• /shop - Browse items\n"
        help_msg += "• /premium - Upgrade to premium\n"
        help_msg += "• /help - Show this help"
    
    await message.answer(help_msg)

# Handle game exit
@dp.message(F.text.lower() == "exit")
async def handle_game_exit(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["in_game"]:
        await message.answer("❌ You are not in a game.")
        return
    
    # Exit game
    update_user_state(user_id, {"in_game": False})
    await update_user_commands(user_id)
    
    await message.answer(
        "🎮 Game ended!\n\n"
        "Your commands have been updated. You no longer have access to /inventory."
    )

@dp.message()
async def handle_other_messages(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if state["in_game"]:
        await message.answer(
            "🎮 You are in a game! Available commands:\n"
            "• /inventory - View your items\n"
            "• /shop - Browse items\n"
            "• Type 'exit' to leave the game"
        )
    else:
        await message.answer("🤔 I don't understand that message. Use /help to see available commands.")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🚀 Step 2: Event-Driven Command Updates

Let's create a system that responds to various events:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram_cmds import CommandScopeManager
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Event system
class EventManager:
    def __init__(self):
        self.listeners = {}
        self.user_events = {}
    
    def on(self, event_type: str, callback):
        """Register event listener."""
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(callback)
    
    async def emit(self, event_type: str, user_id: int, data: dict = None):
        """Emit event to listeners."""
        if event_type not in self.listeners:
            return
        
        event_data = {
            "user_id": user_id,
            "timestamp": int(time.time()),
            "data": data or {}
        }
        
        # Store event for user
        if user_id not in self.user_events:
            self.user_events[user_id] = []
        self.user_events[user_id].append({
            "type": event_type,
            **event_data
        })
        
        # Notify listeners
        for callback in self.listeners[event_type]:
            try:
                await callback(event_data)
            except Exception as e:
                logger.error(f"Error in event listener: {e}")

# Global event manager
event_manager = EventManager()

# User state with events
user_states = {}

def get_user_state(user_id: int) -> dict:
    return user_states.get(user_id, {
        "registered": False,
        "premium": False,
        "level": 1,
        "experience": 0,
        "coins": 100,
        "last_login": 0,
        "streak": 0,
        "achievements": [],
        "active_quests": [],
        "inventory": [],
        "last_event": None
    })

def update_user_state(user_id: int, updates: dict):
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id].update(updates)

async def update_user_commands(user_id: int):
    """Update commands based on current state."""
    state = get_user_state(user_id)
    
    manager = CommandScopeManager(bot)
    await manager.update_user_commands(
        user_id=user_id,
        is_registered=state["registered"],
        has_vehicle=state["premium"],
        user_language="en"
    )

# Event listeners
@event_manager.on("user_registered")
async def on_user_registered(event_data):
    """Handle user registration event."""
    user_id = event_data["user_id"]
    logger.info(f"User {user_id} registered")
    
    # Update commands
    await update_user_commands(user_id)
    
    # Send welcome message
    await bot.send_message(
        user_id,
        "🎉 Welcome to the game! Your commands have been updated."
    )

@event_manager.on("level_up")
async def on_level_up(event_data):
    """Handle level up event."""
    user_id = event_data["user_id"]
    new_level = event_data["data"]["new_level"]
    
    logger.info(f"User {user_id} leveled up to {new_level}")
    
    # Update commands if level 10 (unlock new features)
    if new_level >= 10:
        await update_user_commands(user_id)
        await bot.send_message(
            user_id,
            f"🌟 Level {new_level} reached! New commands unlocked!"
        )

@event_manager.on("premium_upgrade")
async def on_premium_upgrade(event_data):
    """Handle premium upgrade event."""
    user_id = event_data["user_id"]
    
    logger.info(f"User {user_id} upgraded to premium")
    
    # Update commands
    await update_user_commands(user_id)
    
    # Send premium welcome
    await bot.send_message(
        user_id,
        "🌟 Premium upgrade successful! Premium commands unlocked!"
    )

@event_manager.on("quest_completed")
async def on_quest_completed(event_data):
    """Handle quest completion event."""
    user_id = event_data["user_id"]
    quest_name = event_data["data"]["quest_name"]
    
    logger.info(f"User {user_id} completed quest: {quest_name}")
    
    # Check if this unlocks new commands
    if quest_name == "first_quest":
        await update_user_commands(user_id)
        await bot.send_message(
            user_id,
            "🎯 First quest completed! New commands unlocked!"
        )

@event_manager.on("daily_login")
async def on_daily_login(event_data):
    """Handle daily login event."""
    user_id = event_data["user_id"]
    streak = event_data["data"]["streak"]
    
    logger.info(f"User {user_id} daily login, streak: {streak}")
    
    # Unlock special commands for long streaks
    if streak >= 7:
        await update_user_commands(user_id)
        await bot.send_message(
            user_id,
            f"🔥 {streak} day streak! Special commands unlocked!"
        )

async def on_startup():
    """Set up initial commands."""
    config = CmdsConfig(
        languages=["en"],
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "register": CommandDef(i18n_key="register.desc"),
            "profile": CommandDef(i18n_key="profile.desc"),
            "play": CommandDef(i18n_key="play.desc"),
            "shop": CommandDef(i18n_key="shop.desc"),
            "inventory": CommandDef(i18n_key="inventory.desc"),
            "quests": CommandDef(i18n_key="quests.desc"),
            "daily": CommandDef(i18n_key="daily.desc"),
            "premium": CommandDef(i18n_key="premium.desc"),
            "leaderboard": CommandDef(i18n_key="leaderboard.desc"),
            "achievements": CommandDef(i18n_key="achievements.desc"),
        },
        profiles={
            "guest": ProfileDef(include=["start", "help", "register"]),
            "newbie": ProfileDef(include=["start", "help", "profile", "play", "shop"]),
            "player": ProfileDef(include=["start", "help", "profile", "play", "shop", "inventory", "quests", "daily"]),
            "veteran": ProfileDef(include=["start", "help", "profile", "play", "shop", "inventory", "quests", "daily", "leaderboard", "achievements"]),
            "premium": ProfileDef(include=["start", "help", "profile", "play", "shop", "inventory", "quests", "daily", "leaderboard", "achievements", "premium"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
    )
    
    def event_driven_profile_resolver(flags: Flags) -> str:
        user_id = getattr(flags, 'user_id', None)
        if not user_id:
            return "guest"
        
        state = get_user_state(user_id)
        
        if state["premium"]:
            return "premium"
        elif state["level"] >= 20:
            return "veteran"
        elif state["level"] >= 5:
            return "player"
        elif state["registered"]:
            return "newbie"
        else:
            return "guest"
    
    manager = CommandScopeManager(bot, config=config, profile_resolver=event_driven_profile_resolver)
    await manager.setup_all()
    
    logger.info("✅ Bot started with event-driven commands!")

# Message handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer(
            "👋 Welcome to the Event-Driven Bot!\n\n"
            "Use /register to create an account and start your adventure!"
        )
    else:
        # Check for daily login
        last_login = state.get("last_login", 0)
        current_time = int(time.time())
        
        if current_time - last_login > 24 * 3600:  # 24 hours
            # Daily login
            new_streak = state.get("streak", 0) + 1
            update_user_state(user_id, {
                "last_login": current_time,
                "streak": new_streak,
                "coins": state.get("coins", 0) + 10
            })
            
            await event_manager.emit("daily_login", user_id, {"streak": new_streak})
        
        await message.answer(
            f"👋 Welcome back!\n\n"
            f"Level: {state['level']}\n"
            f"Experience: {state['experience']}\n"
            f"Coins: {state['coins']}\n"
            f"Streak: {state.get('streak', 0)} days\n\n"
            f"Use /help to see your available commands."
        )

@dp.message(Command("register"))
async def handle_register(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if state["registered"]:
        await message.answer("✅ You are already registered!")
        return
    
    # Simulate registration
    await message.answer("🔄 Creating your account...")
    
    update_user_state(user_id, {
        "registered": True,
        "last_login": int(time.time()),
        "streak": 1
    })
    
    # Emit registration event
    await event_manager.emit("user_registered", user_id)
    
    await message.answer("🎉 Account created! Welcome to the game!")

@dp.message(Command("play"))
async def handle_play(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    # Simulate gameplay
    await message.answer("🎮 Playing...")
    
    # Random experience gain
    exp_gain = random.randint(10, 50)
    new_exp = state["experience"] + exp_gain
    new_level = state["level"]
    
    # Check for level up
    if new_exp >= new_level * 100:
        new_level += 1
        await event_manager.emit("level_up", user_id, {"new_level": new_level})
    
    update_user_state(user_id, {
        "experience": new_exp,
        "level": new_level,
        "coins": state["coins"] + random.randint(5, 15)
    })
    
    await message.answer(
        f"🎮 Game completed!\n\n"
        f"Experience gained: +{exp_gain}\n"
        f"Coins earned: +{random.randint(5, 15)}\n"
        f"Current level: {new_level}"
    )

@dp.message(Command("quests"))
async def handle_quests(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    # Simulate quest completion
    if "first_quest" not in state.get("achievements", []):
        await message.answer("🎯 Completing your first quest...")
        
        update_user_state(user_id, {
            "achievements": state.get("achievements", []) + ["first_quest"],
            "coins": state["coins"] + 50
        })
        
        await event_manager.emit("quest_completed", user_id, {"quest_name": "first_quest"})
        
        await message.answer("🎉 First quest completed! +50 coins!")
    else:
        await message.answer(
            "📋 Available Quests:\n\n"
            "1. Daily Challenge - Play 3 games (0/3)\n"
            "2. Coin Collector - Earn 100 coins (0/100)\n"
            "3. Level Up - Reach level 5 (0/5)\n\n"
            "Complete quests to unlock new commands!"
        )

@dp.message(Command("premium"))
async def handle_premium(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    if state["premium"]:
        await message.answer("🌟 You are already a premium member!")
        return
    
    # Simulate premium upgrade
    await message.answer("💳 Processing premium upgrade...")
    
    update_user_state(user_id, {"premium": True})
    
    # Emit premium upgrade event
    await event_manager.emit("premium_upgrade", user_id)
    
    await message.answer("🌟 Premium upgrade successful!")

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    help_msg = "📋 Available commands:\n\n"
    
    if not state["registered"]:
        help_msg += "• /start - Start the bot\n"
        help_msg += "• /register - Create account\n"
        help_msg += "• /help - Show this help"
    else:
        help_msg += "🎮 Game Commands:\n"
        help_msg += "• /play - Play the game\n"
        help_msg += "• /quests - View/complete quests\n"
        help_msg += "• /daily - Daily rewards\n\n"
        
        if state["level"] >= 5:
            help_msg += "📊 Advanced Commands:\n"
            help_msg += "• /inventory - View items\n"
            help_msg += "• /shop - Browse items\n\n"
        
        if state["level"] >= 20:
            help_msg += "🏆 Veteran Commands:\n"
            help_msg += "• /leaderboard - View rankings\n"
            help_msg += "• /achievements - View achievements\n\n"
        
        if state["premium"]:
            help_msg += "🌟 Premium Commands:\n"
            help_msg += "• /premium - Premium features\n\n"
        
        help_msg += "👤 User Commands:\n"
        help_msg += "• /profile - Your profile\n"
        help_msg += "• /help - Show this help"
    
    await message.answer(help_msg)

@dp.message()
async def handle_other_messages(message: types.Message):
    await message.answer("🤔 I don't understand that message. Use /help to see available commands.")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🚀 Step 3: Scheduled Command Updates

Let's add scheduled updates that run periodically:

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram_cmds import CommandScopeManager
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Scheduled tasks
class Scheduler:
    def __init__(self):
        self.tasks = []
        self.running = False
    
    def add_task(self, func, interval: int):
        """Add a scheduled task."""
        self.tasks.append((func, interval))
    
    async def start(self):
        """Start the scheduler."""
        self.running = True
        for func, interval in self.tasks:
            asyncio.create_task(self._run_task(func, interval))
    
    async def _run_task(self, func, interval: int):
        """Run a task periodically."""
        while self.running:
            try:
                await func()
            except Exception as e:
                logger.error(f"Error in scheduled task: {e}")
            await asyncio.sleep(interval)
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False

# Global scheduler
scheduler = Scheduler()

# User states
user_states = {}

def get_user_state(user_id: int) -> dict:
    return user_states.get(user_id, {
        "registered": False,
        "premium": False,
        "level": 1,
        "experience": 0,
        "coins": 100,
        "last_activity": 0,
        "energy": 100,
        "daily_bonus": False,
        "weekly_challenge": False,
        "monthly_reward": False
    })

def update_user_state(user_id: int, updates: dict):
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id].update(updates)

async def update_user_commands(user_id: int):
    """Update commands for a user."""
    state = get_user_state(user_id)
    
    manager = CommandScopeManager(bot)
    await manager.update_user_commands(
        user_id=user_id,
        is_registered=state["registered"],
        has_vehicle=state["premium"],
        user_language="en"
    )

# Scheduled tasks
async def daily_reset():
    """Reset daily bonuses and challenges."""
    logger.info("Running daily reset...")
    
    for user_id, state in user_states.items():
        if state["registered"]:
            # Reset daily bonus
            update_user_state(user_id, {"daily_bonus": False})
            
            # Check for weekly challenge
            if not state.get("weekly_challenge", False):
                update_user_state(user_id, {"weekly_challenge": True})
            
            # Update commands if needed
            await update_user_commands(user_id)
            
            # Notify user
            try:
                await bot.send_message(
                    user_id,
                    "🌅 Daily reset complete! New challenges available!"
                )
            except Exception as e:
                logger.error(f"Failed to send daily reset message to {user_id}: {e}")

async def energy_regeneration():
    """Regenerate user energy."""
    logger.info("Regenerating user energy...")
    
    for user_id, state in user_states.items():
        if state["registered"] and state["energy"] < 100:
            new_energy = min(100, state["energy"] + 10)
            update_user_state(user_id, {"energy": new_energy})
            
            if new_energy == 100:
                try:
                    await bot.send_message(
                        user_id,
                        "⚡ Your energy is fully restored!"
                    )
                except Exception as e:
                    logger.error(f"Failed to send energy message to {user_id}: {e}")

async def weekly_challenge():
    """Start weekly challenges."""
    logger.info("Starting weekly challenges...")
    
    for user_id, state in user_states.items():
        if state["registered"] and state["level"] >= 5:
            update_user_state(user_id, {"weekly_challenge": True})
            
            try:
                await bot.send_message(
                    user_id,
                    "🎯 New weekly challenge available! Use /challenge to participate!"
                )
            except Exception as e:
                logger.error(f"Failed to send challenge message to {user_id}: {e}")

async def monthly_rewards():
    """Distribute monthly rewards."""
    logger.info("Distributing monthly rewards...")
    
    for user_id, state in user_states.items():
        if state["registered"] and not state.get("monthly_reward", False):
            reward_coins = state["level"] * 10
            update_user_state(user_id, {
                "monthly_reward": True,
                "coins": state["coins"] + reward_coins
            })
            
            try:
                await bot.send_message(
                    user_id,
                    f"🎁 Monthly reward: {reward_coins} coins!"
                )
            except Exception as e:
                logger.error(f"Failed to send monthly reward to {user_id}: {e}")

async def on_startup():
    """Set up initial commands and scheduler."""
    config = CmdsConfig(
        languages=["en"],
        commands={
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "register": CommandDef(i18n_key="register.desc"),
            "profile": CommandDef(i18n_key="profile.desc"),
            "play": CommandDef(i18n_key="play.desc"),
            "shop": CommandDef(i18n_key="shop.desc"),
            "inventory": CommandDef(i18n_key="inventory.desc"),
            "daily": CommandDef(i18n_key="daily.desc"),
            "challenge": CommandDef(i18n_key="challenge.desc"),
            "energy": CommandDef(i18n_key="energy.desc"),
            "premium": CommandDef(i18n_key="premium.desc"),
        },
        profiles={
            "guest": ProfileDef(include=["start", "help", "register"]),
            "user": ProfileDef(include=["start", "help", "profile", "play", "shop", "daily"]),
            "active": ProfileDef(include=["start", "help", "profile", "play", "shop", "daily", "challenge", "energy"]),
            "premium": ProfileDef(include=["start", "help", "profile", "play", "shop", "daily", "challenge", "energy", "premium"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
    )
    
    def scheduled_profile_resolver(flags: Flags) -> str:
        user_id = getattr(flags, 'user_id', None)
        if not user_id:
            return "guest"
        
        state = get_user_state(user_id)
        
        if state["premium"]:
            return "premium"
        elif state.get("weekly_challenge", False):
            return "active"
        elif state["registered"]:
            return "user"
        else:
            return "guest"
    
    manager = CommandScopeManager(bot, config=config, profile_resolver=scheduled_profile_resolver)
    await manager.setup_all()
    
    # Set up scheduled tasks
    scheduler.add_task(daily_reset, 24 * 3600)  # Daily
    scheduler.add_task(energy_regeneration, 300)  # Every 5 minutes
    scheduler.add_task(weekly_challenge, 7 * 24 * 3600)  # Weekly
    scheduler.add_task(monthly_rewards, 30 * 24 * 3600)  # Monthly
    
    # Start scheduler
    await scheduler.start()
    
    logger.info("✅ Bot started with scheduled command updates!")

# Message handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer(
            "👋 Welcome to the Scheduled Bot!\n\n"
            "Use /register to create an account and start your adventure!"
        )
    else:
        await message.answer(
            f"👋 Welcome back!\n\n"
            f"Level: {state['level']}\n"
            f"Energy: {state['energy']}/100\n"
            f"Coins: {state['coins']}\n"
            f"Daily Bonus: {'✅' if state['daily_bonus'] else '❌'}\n"
            f"Weekly Challenge: {'✅' if state['weekly_challenge'] else '❌'}\n\n"
            f"Use /help to see your available commands."
        )

@dp.message(Command("register"))
async def handle_register(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if state["registered"]:
        await message.answer("✅ You are already registered!")
        return
    
    update_user_state(user_id, {
        "registered": True,
        "last_activity": int(time.time())
    })
    
    await update_user_commands(user_id)
    await message.answer("🎉 Account created! Welcome to the game!")

@dp.message(Command("daily"))
async def handle_daily(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    if state["daily_bonus"]:
        await message.answer("✅ You've already claimed your daily bonus today!")
        return
    
    # Give daily bonus
    bonus_coins = random.randint(50, 100)
    update_user_state(user_id, {
        "daily_bonus": True,
        "coins": state["coins"] + bonus_coins
    })
    
    await message.answer(f"🎁 Daily bonus: {bonus_coins} coins!")

@dp.message(Command("challenge"))
async def handle_challenge(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    if not state.get("weekly_challenge", False):
        await message.answer("❌ No weekly challenge available right now.")
        return
    
    # Complete challenge
    reward_coins = random.randint(100, 200)
    update_user_state(user_id, {
        "weekly_challenge": False,
        "coins": state["coins"] + reward_coins
    })
    
    await update_user_commands(user_id)
    await message.answer(f"🎯 Weekly challenge completed! Reward: {reward_coins} coins!")

@dp.message(Command("energy"))
async def handle_energy(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    if not state["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    await message.answer(f"⚡ Your energy: {state['energy']}/100")

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    user_id = message.from_user.id
    state = get_user_state(user_id)
    
    help_msg = "📋 Available commands:\n\n"
    
    if not state["registered"]:
        help_msg += "• /start - Start the bot\n"
        help_msg += "• /register - Create account\n"
        help_msg += "• /help - Show this help"
    else:
        help_msg += "🎮 Game Commands:\n"
        help_msg += "• /play - Play the game\n"
        help_msg += "• /daily - Daily bonus\n"
        help_msg += "• /energy - Check energy\n\n"
        
        if state.get("weekly_challenge", False):
            help_msg += "🎯 Challenge Commands:\n"
            help_msg += "• /challenge - Complete weekly challenge\n\n"
        
        if state["premium"]:
            help_msg += "🌟 Premium Commands:\n"
            help_msg += "• /premium - Premium features\n\n"
        
        help_msg += "👤 User Commands:\n"
        help_msg += "• /profile - Your profile\n"
        help_msg += "• /shop - Browse items\n"
        help_msg += "• /help - Show this help"
    
    await message.answer(help_msg)

@dp.message()
async def handle_other_messages(message: types.Message):
    await message.answer("🤔 I don't understand that message. Use /help to see available commands.")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🚨 Common Issues

### Commands Not Updating
```python
# Make sure to call update_user_commands after state changes
await update_user_commands(user_id)
```

### Event Listeners Not Firing
```python
# Check if event manager is properly initialized
event_manager = EventManager()
event_manager.on("event_name", callback)
await event_manager.emit("event_name", user_id, data)
```

### Scheduled Tasks Not Running
```python
# Make sure scheduler is started
await scheduler.start()
```

### Performance Issues
```python
# Batch command updates for better performance
async def batch_update_commands(user_ids: list):
    for user_id in user_ids:
        await update_user_commands(user_id)
```

## 🎉 Next Steps

Congratulations! You've successfully implemented dynamic command updates. Here's what you can do next:

1. **[Examples](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/examples)** - See complete dynamic bots
2. **[API Reference](../api/core.md)** - Explore advanced features
3. **[Performance Guide](../performance.md)** - Optimize your dynamic system
4. **[Configuration Guide](../configuration.md)** - Advanced configuration options

## 💡 Tips

- Use events for decoupled command updates
- Implement proper error handling for all updates
- Cache user states for better performance
- Use scheduled tasks for periodic updates
- Test all state transitions thoroughly
- Monitor command update performance
- Implement rollback mechanisms for failed updates

---

**Ready for more?** Check out the [Examples](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/examples) to see complete dynamic bots in action!
