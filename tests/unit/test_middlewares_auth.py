"""Unit tests for AuthMiddleware."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram_sentinel.middlewares.auth import AuthMiddleware


@pytest.mark.unit
class TestAuthMiddleware:
    """Test AuthMiddleware functionality."""

    @pytest.mark.asyncio
    async def test_anonymous_user_passes(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_data):
        """Test that anonymous users (user_id=0) pass through."""
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Create anonymous event
        mock_event = MagicMock()
        mock_event.from_user = None
        mock_event.user = None
        mock_event.chat = None
        
        # Process event
        result = await middleware(mock_handler, mock_event, mock_data)
        
        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_event, mock_data)
        
        # Should not set auth flags
        assert "user_exists" not in mock_data
        assert "user_context" not in mock_data

    @pytest.mark.asyncio
    async def test_user_registration(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test that users are automatically registered."""
        # Mock unregistered user
        mock_user_repo.is_registered.return_value = False
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)
        
        # Should register user
        mock_user_repo.register_user.assert_called_once()
        call_args = mock_user_repo.register_user.call_args
        assert call_args[0][0] == 12345  # User ID
        assert "username" in call_args[1]
        assert "registered_at" in call_args[1]
        
        # Should set user_exists flag
        assert mock_data["user_exists"] is True

    @pytest.mark.asyncio
    async def test_registered_user_no_duplicate_registration(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test that registered users are not registered again."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)
        
        # Should not register user again
        mock_user_repo.register_user.assert_not_called()
        
        # Should set user_exists flag
        assert mock_data["user_exists"] is True

    @pytest.mark.asyncio
    async def test_require_registered_decorator_allowed(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test that registered users can access @require_registered handlers."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        # Set require_registered decorator
        mock_handler._sentinel_require_registered = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)
        
        # Should not set auth_required flag
        assert "sentinel_auth_required" not in mock_data

    @pytest.mark.asyncio
    async def test_require_registered_decorator_blocked(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test that unregistered users are blocked from @require_registered handlers."""
        # Mock unregistered user
        mock_user_repo.is_registered.return_value = False
        
        # Set require_registered decorator
        mock_handler._sentinel_require_registered = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should not call handler
        mock_handler.assert_not_called()
        
        # Should return None (blocked)
        assert result is None
        
        # Should set auth_required flag
        assert mock_data["sentinel_auth_required"] is True

    @pytest.mark.asyncio
    async def test_resolve_user_hook_success(self, mock_user_repo, mock_blocklist_backend, mock_resolve_user, mock_handler, mock_message, mock_data):
        """Test successful user resolution with hook."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend, resolve_user=mock_resolve_user)
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should call handler and return result
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)
        
        # Should set user context
        assert "user_context" in mock_data
        assert mock_data["user_context"]["user_id"] == 12345
        assert mock_data["user_context"]["username"] == "testuser"
        
        # Should set user_exists flag
        assert mock_data["user_exists"] is True

    @pytest.mark.asyncio
    async def test_resolve_user_hook_veto(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test user resolution hook vetoing the request."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        # Mock vetoing resolver
        async def vetoing_resolver(event, data):
            return None  # Veto the request
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend, resolve_user=vetoing_resolver)
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should not call handler
        mock_handler.assert_not_called()
        
        # Should return None (vetoed)
        assert result is None
        
        # Should set auth_vetoed flag
        assert mock_data["sentinel_auth_vetoed"] is True

    @pytest.mark.asyncio
    async def test_resolve_user_hook_error(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test user resolution hook error handling."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        # Mock erroring resolver
        async def erroring_resolver(event, data):
            raise Exception("Resolver error")
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend, resolve_user=erroring_resolver)
        
        # Should raise the error
        with pytest.raises(Exception, match="Resolver error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_extract_user_info_from_message(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_data):
        """Test user info extraction from message."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Create message with user
        mock_message = MagicMock()
        mock_message.from_user.id = 12345
        mock_message.from_user.username = "testuser"
        
        # Process event
        await middleware(mock_handler, mock_message, mock_data)
        
        # Should register user with correct info
        mock_user_repo.register_user.assert_called_once()
        call_args = mock_user_repo.register_user.call_args
        assert call_args[0][0] == 12345
        assert call_args[1]["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_extract_user_info_from_callback_query(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_data):
        """Test user info extraction from callback query."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Create callback query with user
        mock_callback = MagicMock()
        mock_callback.from_user.id = 67890
        mock_callback.from_user.username = "callbackuser"
        
        # Process event
        await middleware(mock_handler, mock_callback, mock_data)
        
        # Should register user with correct info
        mock_user_repo.register_user.assert_called_once()
        call_args = mock_user_repo.register_user.call_args
        assert call_args[0][0] == 67890
        assert call_args[1]["username"] == "callbackuser"

    @pytest.mark.asyncio
    async def test_extract_user_info_from_chat(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_data):
        """Test user info extraction from chat (fallback)."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Create event with only chat
        mock_event = MagicMock()
        mock_event.from_user = None
        mock_event.user = None
        mock_event.chat.id = 11111
        mock_event.chat.username = "chatuser"
        
        # Process event
        await middleware(mock_handler, mock_event, mock_data)
        
        # Should register user with chat info
        mock_user_repo.register_user.assert_called_once()
        call_args = mock_user_repo.register_user.call_args
        assert call_args[0][0] == 11111
        assert call_args[1]["username"] == "chatuser"

    @pytest.mark.asyncio
    async def test_no_user_info_available(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_data):
        """Test handling when no user info is available."""
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Create event with no user information
        mock_event = MagicMock()
        mock_event.from_user = None
        mock_event.user = None
        mock_event.chat = None
        
        # Process event
        result = await middleware(mock_handler, mock_event, mock_data)
        
        # Should call handler (anonymous user)
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_event, mock_data)

    @pytest.mark.asyncio
    async def test_user_repo_error(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test handling when user repo raises an error."""
        # Mock user repo error
        mock_user_repo.is_registered.side_effect = Exception("User repo error")
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Should raise the error
        with pytest.raises(Exception, match="User repo error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_handler_error_propagation(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test that handler errors are propagated."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        # Mock handler error
        mock_handler.side_effect = Exception("Handler error")
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Should propagate handler error
        with pytest.raises(Exception, match="Handler error"):
            await middleware(mock_handler, mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_data_preservation(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test that data dictionary is preserved."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        # Add some data
        mock_data["existing_key"] = "existing_value"
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Process event
        await middleware(mock_handler, mock_message, mock_data)
        
        # Should preserve existing data
        assert mock_data["existing_key"] == "existing_value"

    @pytest.mark.asyncio
    async def test_auth_flags_preservation(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_message, mock_data):
        """Test that existing auth flags are preserved."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        # Set existing auth flags
        mock_data["user_exists"] = "existing_value"
        mock_data["user_context"] = {"existing": "context"}
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Process event
        await middleware(mock_handler, mock_message, mock_data)
        
        # Should preserve existing flags
        assert mock_data["user_exists"] == "existing_value"
        assert mock_data["user_context"] == {"existing": "context"}

    @pytest.mark.asyncio
    async def test_middleware_initialization(self, mock_user_repo, mock_blocklist_backend):
        """Test middleware initialization."""
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Should store the backends
        assert middleware._user_repo is mock_user_repo
        assert middleware._blocklist_backend is mock_blocklist_backend
        assert middleware._resolve_user is None

    @pytest.mark.asyncio
    async def test_middleware_initialization_with_resolver(self, mock_user_repo, mock_blocklist_backend, mock_resolve_user):
        """Test middleware initialization with resolver."""
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend, resolve_user=mock_resolve_user)
        
        # Should store the resolver
        assert middleware._resolve_user is mock_resolve_user

    @pytest.mark.asyncio
    async def test_edge_case_empty_username(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_data):
        """Test handling with empty username."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Create message with empty username
        mock_message = MagicMock()
        mock_message.from_user.id = 12345
        mock_message.from_user.username = ""
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should work normally
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)

    @pytest.mark.asyncio
    async def test_edge_case_none_username(self, mock_user_repo, mock_blocklist_backend, mock_handler, mock_data):
        """Test handling with None username."""
        # Mock registered user
        mock_user_repo.is_registered.return_value = True
        
        middleware = AuthMiddleware(mock_user_repo, mock_blocklist_backend)
        
        # Create message with None username
        mock_message = MagicMock()
        mock_message.from_user.id = 12345
        mock_message.from_user.username = None
        
        # Process event
        result = await middleware(mock_handler, mock_message, mock_data)
        
        # Should work normally
        assert result == "handler_result"
        mock_handler.assert_called_once_with(mock_message, mock_data)
