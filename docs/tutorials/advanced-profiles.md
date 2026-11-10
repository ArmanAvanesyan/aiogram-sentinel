# Advanced Profiles Tutorial

This tutorial will show you how to create sophisticated user profiles and command management systems using aiogram-cmds.

## 🎯 What We'll Build

An advanced bot with:
- Multiple user profiles (guest, user, premium, admin)
- Dynamic command sets based on user status
- Profile-based access control
- Custom profile resolvers

## 📋 Prerequisites

- Completed [Basic Setup Tutorial](basic-setup.md)
- Understanding of [i18n Integration](i18n-integration.md)
- Basic knowledge of user management systems

## 🚀 Step 1: Define User Profiles

Let's create a comprehensive profile system for an e-commerce bot:

```python
from aiogram_cmds import CmdsConfig, CommandDef, ProfileDef, ScopeDef, MenuButtonDef
from aiogram_cmds import CommandScopeManager, ProfileResolver, Flags
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# User database simulation (in real apps, use a proper database)
user_db = {
    # user_id: {"registered": bool, "premium": bool, "admin": bool, "banned": bool}
}

def get_user_status(user_id: int) -> dict:
    """Get user status from database."""
    return user_db.get(user_id, {
        "registered": False,
        "premium": False,
        "admin": False,
        "banned": False
    })

async def on_startup():
    """Set up commands with advanced profiles."""
    
    config = CmdsConfig(
        languages=["en", "ru"],
        fallback_language="en",
        i18n_key_prefix="cmd",
        commands={
            # Basic commands
            "start": CommandDef(i18n_key="start.desc"),
            "help": CommandDef(i18n_key="help.desc"),
            "about": CommandDef(i18n_key="about.desc"),
            
            # Registration commands
            "register": CommandDef(i18n_key="register.desc"),
            "login": CommandDef(i18n_key="login.desc"),
            
            # User commands
            "profile": CommandDef(i18n_key="profile.desc"),
            "settings": CommandDef(i18n_key="settings.desc"),
            "catalog": CommandDef(i18n_key="catalog.desc"),
            "cart": CommandDef(i18n_key="cart.desc"),
            "orders": CommandDef(i18n_key="orders.desc"),
            
            # Premium commands
            "premium": CommandDef(i18n_key="premium.desc"),
            "vip_offers": CommandDef(i18n_key="vip_offers.desc"),
            "priority_support": CommandDef(i18n_key="priority_support.desc"),
            
            # Admin commands
            "admin": CommandDef(i18n_key="admin.desc"),
            "ban": CommandDef(i18n_key="ban.desc"),
            "unban": CommandDef(i18n_key="unban.desc"),
            "stats": CommandDef(i18n_key="stats.desc"),
            "broadcast": CommandDef(i18n_key="broadcast.desc"),
        },
        profiles={
            # Guest profile - unregistered users
            "guest": ProfileDef(include=[
                "start", "help", "about", "register", "login", "catalog"
            ]),
            
            # User profile - registered users
            "user": ProfileDef(include=[
                "start", "help", "about", "profile", "settings", 
                "catalog", "cart", "orders", "premium"
            ]),
            
            # Premium profile - paying customers
            "premium": ProfileDef(include=[
                "start", "help", "about", "profile", "settings",
                "catalog", "cart", "orders", "premium", 
                "vip_offers", "priority_support"
            ]),
            
            # Admin profile - administrators
            "admin": ProfileDef(include=[
                "start", "help", "about", "profile", "settings",
                "catalog", "cart", "orders", "premium",
                "vip_offers", "priority_support",
                "admin", "ban", "unban", "stats", "broadcast"
            ]),
            
            # Banned profile - restricted users
            "banned": ProfileDef(include=["start", "help"]),
        },
        scopes=[
            ScopeDef(scope="all_private_chats", profile="guest"),
        ],
        menu_button=MenuButtonDef(mode="commands"),
    )
    
    # Custom profile resolver
    def advanced_profile_resolver(flags: Flags) -> str:
        user_id = flags.user_id if hasattr(flags, 'user_id') else None
        if not user_id:
            return "guest"
        
        status = get_user_status(user_id)
        
        if status["banned"]:
            return "banned"
        elif status["admin"]:
            return "admin"
        elif status["premium"]:
            return "premium"
        elif status["registered"]:
            return "user"
        else:
            return "guest"
    
    manager = CommandScopeManager(
        bot, 
        config=config, 
        profile_resolver=advanced_profile_resolver
    )
    await manager.setup_all()
    
    logger.info("✅ Bot started with advanced profiles!")

# Message handlers
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if status["banned"]:
        await message.answer("🚫 You are banned from using this bot.")
        return
    
    welcome_msg = "👋 Welcome to our e-commerce bot!"
    if not status["registered"]:
        welcome_msg += "\n\nUse /register to create an account."
    elif status["premium"]:
        welcome_msg += "\n\n🌟 Thank you for being a premium member!"
    elif status["admin"]:
        welcome_msg += "\n\n👑 Welcome, administrator!"
    
    await message.answer(welcome_msg)

@dp.message(Command("register"))
async def handle_register(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if status["registered"]:
        await message.answer("✅ You are already registered!")
        return
    
    # Simulate registration
    user_db[user_id] = {
        "registered": True,
        "premium": False,
        "admin": False,
        "banned": False
    }
    
    # Update user commands
    manager = CommandScopeManager(bot)
    await manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=False,
        user_language="en"
    )
    
    await message.answer("🎉 Registration successful! Your commands have been updated.")

@dp.message(Command("premium"))
async def handle_premium(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if not status["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    if status["premium"]:
        await message.answer("🌟 You are already a premium member!")
        return
    
    # Simulate premium upgrade
    user_db[user_id]["premium"] = True
    
    # Update user commands
    manager = CommandScopeManager(bot)
    await manager.update_user_commands(
        user_id=user_id,
        is_registered=True,
        has_vehicle=True,  # Using has_vehicle as premium flag
        user_language="en"
    )
    
    await message.answer("🌟 Premium upgrade successful! You now have access to VIP features.")

@dp.message(Command("admin"))
async def handle_admin(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if not status["admin"]:
        await message.answer("❌ Access denied. Admin privileges required.")
        return
    
    await message.answer("👑 Admin panel:\n\n/stats - View bot statistics\n/broadcast - Send broadcast message")

@dp.message(Command("ban"))
async def handle_ban(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if not status["admin"]:
        await message.answer("❌ Access denied. Admin privileges required.")
        return
    
    # Extract user ID from message (simplified)
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        user_db[target_id] = user_db.get(target_id, {})
        user_db[target_id]["banned"] = True
        
        # Update target user's commands
        manager = CommandScopeManager(bot)
        await manager.update_user_commands(
            user_id=target_id,
            is_registered=False,
            has_vehicle=False,
            user_language="en"
        )
        
        await message.answer(f"🚫 User {target_id} has been banned.")
    else:
        await message.answer("❌ Reply to a message to ban the user.")

@dp.message(Command("help"))
async def handle_help(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    help_msg = "📋 Available commands:\n\n"
    
    if status["banned"]:
        help_msg += "/start - Start the bot\n/help - Show this help"
    elif not status["registered"]:
        help_msg += "/start - Start the bot\n/register - Create account\n/login - Login\n/catalog - Browse products\n/help - Show this help"
    elif status["admin"]:
        help_msg += "👑 Admin commands:\n/admin - Admin panel\n/ban - Ban user\n/unban - Unban user\n/stats - Statistics\n/broadcast - Broadcast\n\n"
        help_msg += "🌟 Premium commands:\n/vip_offers - VIP offers\n/priority_support - Priority support\n\n"
        help_msg += "👤 User commands:\n/profile - Your profile\n/settings - Settings\n/catalog - Browse products\n/cart - Shopping cart\n/orders - Your orders"
    elif status["premium"]:
        help_msg += "🌟 Premium commands:\n/vip_offers - VIP offers\n/priority_support - Priority support\n\n"
        help_msg += "👤 User commands:\n/profile - Your profile\n/settings - Settings\n/catalog - Browse products\n/cart - Shopping cart\n/orders - Your orders"
    else:
        help_msg += "👤 User commands:\n/profile - Your profile\n/settings - Settings\n/catalog - Browse products\n/cart - Shopping cart\n/orders - Your orders\n/premium - Upgrade to premium"
    
    await message.answer(help_msg)

# Other command handlers
@dp.message(Command("profile"))
async def handle_profile(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    profile_msg = f"👤 Your Profile:\n\n"
    profile_msg += f"ID: {user_id}\n"
    profile_msg += f"Registered: {'✅' if status['registered'] else '❌'}\n"
    profile_msg += f"Premium: {'🌟' if status['premium'] else '❌'}\n"
    profile_msg += f"Admin: {'👑' if status['admin'] else '❌'}\n"
    profile_msg += f"Banned: {'🚫' if status['banned'] else '✅'}"
    
    await message.answer(profile_msg)

@dp.message(Command("catalog"))
async def handle_catalog(message: types.Message):
    await message.answer("🛍️ Product Catalog:\n\n1. Product A - $10\n2. Product B - $20\n3. Product C - $30")

@dp.message(Command("cart"))
async def handle_cart(message: types.Message):
    await message.answer("🛒 Your Cart:\n\nCart is empty. Add products from /catalog")

@dp.message(Command("orders"))
async def handle_orders(message: types.Message):
    await message.answer("📦 Your Orders:\n\nNo orders yet. Start shopping!")

@dp.message(Command("vip_offers"))
async def handle_vip_offers(message: types.Message):
    await message.answer("🌟 VIP Offers:\n\nSpecial discount: 50% off all products!")

@dp.message(Command("priority_support"))
async def handle_priority_support(message: types.Message):
    await message.answer("🎧 Priority Support:\n\nYour message has been prioritized. We'll respond within 1 hour.")

@dp.message(Command("stats"))
async def handle_stats(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if not status["admin"]:
        await message.answer("❌ Access denied. Admin privileges required.")
        return
    
    total_users = len(user_db)
    registered_users = sum(1 for u in user_db.values() if u.get("registered", False))
    premium_users = sum(1 for u in user_db.values() if u.get("premium", False))
    banned_users = sum(1 for u in user_db.values() if u.get("banned", False))
    
    stats_msg = f"📊 Bot Statistics:\n\n"
    stats_msg += f"Total Users: {total_users}\n"
    stats_msg += f"Registered: {registered_users}\n"
    stats_msg += f"Premium: {premium_users}\n"
    stats_msg += f"Banned: {banned_users}\n"
    stats_msg += f"Admins: {sum(1 for u in user_db.values() if u.get('admin', False))}"
    
    await message.answer(stats_msg)

@dp.message()
async def handle_other_messages(message: types.Message):
    await message.answer("🤔 I don't understand that message. Use /help to see available commands.")

async def main():
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

## 🚀 Step 2: Enhanced Profile Resolver

Let's create a more sophisticated profile resolver with additional logic:

```python
from typing import Optional
from dataclasses import dataclass
from aiogram_cmds import ProfileResolver, Flags

@dataclass
class ExtendedFlags(Flags):
    """Extended flags with additional user information."""
    user_id: Optional[int] = None
    chat_id: Optional[int] = None
    is_premium: bool = False
    is_admin: bool = False
    is_banned: bool = False
    subscription_tier: str = "free"  # free, basic, premium, enterprise
    last_activity: Optional[int] = None
    registration_date: Optional[int] = None

def create_advanced_profile_resolver(user_db: dict) -> ProfileResolver:
    """Create an advanced profile resolver with multiple factors."""
    
    def resolver(flags: Flags) -> str:
        user_id = getattr(flags, 'user_id', None)
        if not user_id:
            return "guest"
        
        status = user_db.get(user_id, {})
        
        # Check if user is banned
        if status.get("banned", False):
            return "banned"
        
        # Check if user is admin
        if status.get("admin", False):
            return "admin"
        
        # Check subscription tier
        subscription = status.get("subscription_tier", "free")
        if subscription == "enterprise":
            return "enterprise"
        elif subscription == "premium":
            return "premium"
        elif subscription == "basic":
            return "basic"
        
        # Check if user is registered
        if status.get("registered", False):
            return "user"
        
        return "guest"
    
    return resolver

# Usage
advanced_resolver = create_advanced_profile_resolver(user_db)
manager = CommandScopeManager(bot, profile_resolver=advanced_resolver)
```

## 🚀 Step 3: Dynamic Profile Updates

Let's add functionality to update user profiles dynamically:

```python
async def update_user_profile(user_id: int, updates: dict):
    """Update user profile and refresh commands."""
    if user_id not in user_db:
        user_db[user_id] = {}
    
    user_db[user_id].update(updates)
    
    # Refresh user commands
    manager = CommandScopeManager(bot)
    await manager.update_user_commands(
        user_id=user_id,
        is_registered=user_db[user_id].get("registered", False),
        has_vehicle=user_db[user_id].get("premium", False),
        user_language="en"
    )
    
    logger.info(f"Updated profile for user {user_id}: {updates}")

# Example usage
@dp.message(Command("upgrade"))
async def handle_upgrade(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if not status["registered"]:
        await message.answer("❌ Please register first using /register")
        return
    
    if status["premium"]:
        await message.answer("🌟 You are already a premium member!")
        return
    
    # Simulate payment processing
    await message.answer("💳 Processing payment...")
    
    # Update user profile
    await update_user_profile(user_id, {
        "premium": True,
        "subscription_tier": "premium",
        "premium_since": int(time.time())
    })
    
    await message.answer("🌟 Premium upgrade successful! Your commands have been updated.")
```

## 🚀 Step 4: Profile-Based Middleware

Create middleware to automatically update user profiles:

```python
from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable

class ProfileMiddleware(BaseMiddleware):
    """Middleware to automatically update user profiles."""
    
    def __init__(self, user_db: dict):
        self.user_db = user_db
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        
        # Update last activity
        if user_id not in self.user_db:
            self.user_db[user_id] = {}
        
        self.user_db[user_id]["last_activity"] = int(time.time())
        
        # Add user status to data
        data["user_status"] = self.user_db[user_id]
        
        return await handler(event, data)

# Usage
dp.message.middleware(ProfileMiddleware(user_db))
```

## 🚀 Step 5: Testing Your Profiles

Create a test script to verify profile functionality:

```python
async def test_profiles():
    """Test different user profiles."""
    test_users = [
        {"id": 1, "registered": False, "premium": False, "admin": False, "banned": False},
        {"id": 2, "registered": True, "premium": False, "admin": False, "banned": False},
        {"id": 3, "registered": True, "premium": True, "admin": False, "banned": False},
        {"id": 4, "registered": True, "premium": True, "admin": True, "banned": False},
        {"id": 5, "registered": True, "premium": False, "admin": False, "banned": True},
    ]
    
    for user in test_users:
        user_db[user["id"]] = user
        
        manager = CommandScopeManager(bot)
        await manager.update_user_commands(
            user_id=user["id"],
            is_registered=user["registered"],
            has_vehicle=user["premium"],
            user_language="en"
        )
        
        print(f"User {user['id']}: {get_profile_for_user(user['id'])}")

def get_profile_for_user(user_id: int) -> str:
    """Get profile name for a user."""
    status = get_user_status(user_id)
    
    if status["banned"]:
        return "banned"
    elif status["admin"]:
        return "admin"
    elif status["premium"]:
        return "premium"
    elif status["registered"]:
        return "user"
    else:
        return "guest"
```

## 🎯 Advanced Features

### Profile Inheritance

```python
# Profiles can inherit from other profiles
profiles = {
    "base": ProfileDef(include=["start", "help", "about"]),
    "user": ProfileDef(include=["profile", "settings"], inherit_from="base"),
    "premium": ProfileDef(include=["vip_offers"], inherit_from="user"),
    "admin": ProfileDef(include=["admin", "ban"], inherit_from="premium"),
}
```

### Conditional Commands

```python
def conditional_profile_resolver(flags: Flags) -> str:
    """Resolver with conditional logic."""
    user_id = getattr(flags, 'user_id', None)
    if not user_id:
        return "guest"
    
    status = get_user_status(user_id)
    
    # Time-based conditions
    if status.get("last_activity", 0) < time.time() - 30 * 24 * 3600:  # 30 days
        return "inactive"
    
    # Activity-based conditions
    if status.get("message_count", 0) > 1000:
        return "power_user"
    
    # Standard logic
    if status.get("banned", False):
        return "banned"
    elif status.get("admin", False):
        return "admin"
    elif status.get("premium", False):
        return "premium"
    elif status.get("registered", False):
        return "user"
    
    return "guest"
```

### Profile Analytics

```python
async def get_profile_analytics():
    """Get analytics about user profiles."""
    profiles = {}
    for user_id, status in user_db.items():
        profile = get_profile_for_user(user_id)
        profiles[profile] = profiles.get(profile, 0) + 1
    
    return profiles

@dp.message(Command("analytics"))
async def handle_analytics(message: types.Message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    
    if not status["admin"]:
        await message.answer("❌ Access denied. Admin privileges required.")
        return
    
    analytics = await get_profile_analytics()
    
    msg = "📊 Profile Analytics:\n\n"
    for profile, count in analytics.items():
        msg += f"{profile.title()}: {count} users\n"
    
    await message.answer(msg)
```

## 🚨 Common Issues

### Profile Not Updating
```python
# Make sure to call update_user_commands after profile changes
await manager.update_user_commands(
    user_id=user_id,
    is_registered=new_status["registered"],
    has_vehicle=new_status["premium"],
    user_language="en"
)
```

### Circular Profile Dependencies
```python
# Avoid circular dependencies in profile inheritance
# ❌ Bad
profiles = {
    "user": ProfileDef(include=["admin"], inherit_from="admin"),
    "admin": ProfileDef(include=["user"], inherit_from="user"),
}

# ✅ Good
profiles = {
    "base": ProfileDef(include=["start", "help"]),
    "user": ProfileDef(include=["profile"], inherit_from="base"),
    "admin": ProfileDef(include=["admin"], inherit_from="user"),
}
```

### Performance Issues
```python
# Cache profile resolutions for better performance
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_profile(user_id: int) -> str:
    return get_profile_for_user(user_id)
```

## 🎉 Next Steps

Congratulations! You've successfully created advanced user profiles. Here's what you can do next:

1. **[Dynamic Commands Tutorial](dynamic-commands.md)** - Update commands at runtime
2. **[Examples](https://github.com/ArmanAvanesyan/aiogram-cmds/tree/main/examples)** - See complete profile-based bots
3. **[API Reference](../api/configuration.md)** - Explore advanced configuration options
4. **[Performance Guide](../performance.md)** - Optimize your profile system

## 💡 Tips

- Use consistent naming conventions for profiles
- Implement proper error handling for profile updates
- Cache profile resolutions for better performance
- Use middleware to automatically update user activity
- Test all profile transitions thoroughly
- Consider using a proper database for user management
- Implement profile analytics for insights

---

**Ready for more?** Check out the [Dynamic Commands Tutorial](dynamic-commands.md) to learn how to update commands at runtime!
