# Security

This document outlines security considerations, best practices, and recommendations for using aiogram-sentinel in production environments.

## Overview

aiogram-sentinel is designed with security in mind, providing multiple layers of protection for Telegram bots. However, proper configuration and usage are essential for maintaining security.

## Security Features

### 1. Rate Limiting

**Protection against:**
- Spam attacks
- DoS (Denial of Service) attempts
- Resource exhaustion
- API abuse

**Implementation:**
```python
# Configure rate limits
config = SentinelConfig(
    default_rate_limit=10,  # 10 requests per window
    default_rate_window=60,  # 60 second window
)

# Per-handler limits
@rate_limit(limit=3, window=30)  # Stricter limits for sensitive commands
async def admin_command(message: Message):
    # Admin-only command with strict rate limiting
    pass
```

**Best Practices:**
- Set appropriate limits based on your bot's usage patterns
- Use stricter limits for sensitive operations
- Monitor rate limit violations for attack patterns
- Implement progressive rate limiting for repeat offenders

### 2. User Blocking

**Protection against:**
- Malicious users
- Banned users attempting to return
- Users who have blocked your bot

**Implementation:**
```python
# Automatic blocking based on membership changes
async def on_user_blocked(user_id: int, username: str, data: dict):
    """Handle user blocking with security logging."""
    # Log to security audit system
    await security_audit.log_block(user_id, username, data)
    
    # Notify security team
    await notify_security_team(f"User blocked: {username} (ID: {user_id})")
    
    # Clean up user data
    await cleanup_user_data(user_id)
```

**Best Practices:**
- Maintain a persistent blocklist
- Log all blocking events for audit trails
- Implement manual unblocking procedures
- Monitor block patterns for coordinated attacks

### 3. User Authentication

**Protection against:**
- Unauthorized access
- Bot users
- Unregistered users accessing sensitive features

**Implementation:**
```python
async def resolve_user(event, data):
    """Custom user validation with security checks."""
    user = event.from_user
    
    # Block bot users
    if user.is_bot:
        return None
    
    # Check against security blacklist
    if await security_blacklist.is_blacklisted(user.id):
        return None
    
    # Verify user registration
    if not await user_service.is_verified(user.id):
        return None
    
    # Return user context
    return {
        "user_id": user.id,
        "username": user.username,
        "role": await user_service.get_role(user.id),
        "permissions": await user_service.get_permissions(user.id),
    }
```

**Best Practices:**
- Implement multi-factor authentication for sensitive operations
- Maintain user verification status
- Use role-based access control
- Regularly audit user permissions

### 4. Message Debouncing

**Protection against:**
- Duplicate message attacks
- Message flooding
- Resource waste from duplicate processing

**Implementation:**
```python
# Debounce sensitive operations
@debounce(delay=5.0)  # 5 second debounce for sensitive commands
async def transfer_money(message: Message):
    # Financial operation with debouncing
    pass
```

**Best Practices:**
- Use longer debounce delays for sensitive operations
- Implement content-based debouncing for critical commands
- Monitor debounce patterns for attack detection

## Security Considerations

### 1. Data Protection

#### User Data

**What we store:**
- User IDs (required for functionality)
- Usernames (optional, for logging)
- Timestamps (for rate limiting and debouncing)
- Basic user context (for authentication)

**What we don't store:**
- Message content (except for debouncing fingerprints)
- Personal information
- Sensitive data
- Payment information

**Data Retention:**
```python
# Configure data retention
config = SentinelConfig(
    # Redis TTL for automatic cleanup
    redis_url="redis://localhost:6379",
    redis_prefix="my_bot:",
    
    # Memory backend cleanup (automatic)
    backend="memory",
)
```

#### Key Management

**Redis Key Security:**
```python
# Use secure key prefixes
config = SentinelConfig(
    redis_prefix="secure_bot:prod:",  # Environment-specific prefix
    redis_url="redis://user:password@secure-redis.example.com:6379/0"
)
```

**Key Patterns:**
- `prefix:rate:user_id:handler` - Rate limiting keys
- `prefix:debounce:user_id:handler:fingerprint` - Debouncing keys
- `prefix:blocklist` - Blocklist key
- `prefix:user:user_id` - User data keys

### 2. Network Security

#### Redis Security

**Production Configuration:**
```python
# Secure Redis connection
config = SentinelConfig(
    backend="redis",
    redis_url="rediss://user:password@redis.example.com:6380/0",  # SSL enabled
)
```

**Security Measures:**
- Use SSL/TLS for Redis connections
- Implement Redis AUTH
- Use Redis ACLs for fine-grained access control
- Monitor Redis access logs
- Use Redis Sentinel for high availability

#### Bot Token Security

**Environment Variables:**
```bash
# Never hardcode tokens
export BOT_TOKEN="your_secure_bot_token"
export REDIS_PASSWORD="your_redis_password"
```

**Secrets Management:**
- Use environment variables
- Implement secrets rotation
- Use cloud secrets management (AWS Secrets Manager, Azure Key Vault)
- Never commit tokens to version control

### 3. Application Security

#### Input Validation

**User Input Sanitization:**
```python
async def resolve_user(event, data):
    """Validate and sanitize user input."""
    user = event.from_user
    
    # Validate user ID
    if not isinstance(user.id, int) or user.id <= 0:
        return None
    
    # Sanitize username
    username = user.username
    if username:
        # Remove potentially dangerous characters
        username = re.sub(r'[^\w\-_.]', '', username)
    
    return {
        "user_id": user.id,
        "username": username,
        "first_name": user.first_name[:100] if user.first_name else None,  # Limit length
    }
```

#### Error Handling

**Secure Error Messages:**
```python
async def on_rate_limited(event, data, retry_after):
    """Send secure rate limit message."""
    try:
        # Don't expose internal details
        await event.answer(
            "⏰ Please wait before sending another message.",
            show_alert=True
        )
    except Exception as e:
        # Log error securely
        logger.error(f"Failed to send rate limit message: {e}")
        # Don't expose error details to user
```

### 4. Monitoring and Logging

#### Security Logging

**Audit Trail:**
```python
async def security_log(event_type: str, user_id: int, details: dict):
    """Log security events for audit."""
    log_entry = {
        "timestamp": time.time(),
        "event_type": event_type,
        "user_id": user_id,
        "details": details,
        "ip_address": await get_user_ip(user_id),  # If available
    }
    
    # Log to secure audit system
    await audit_system.log(log_entry)
    
    # Alert on suspicious patterns
    if await is_suspicious_pattern(event_type, user_id):
        await security_team.alert(log_entry)
```

**Event Types to Log:**
- Rate limit violations
- User blocking/unblocking
- Authentication failures
- Suspicious user behavior
- System errors

#### Monitoring

**Key Metrics:**
- Rate limit violation frequency
- Block/unblock event patterns
- Authentication success/failure rates
- System performance metrics
- Error rates

**Alerting:**
```python
async def monitor_security_metrics():
    """Monitor security metrics and alert on anomalies."""
    # Check for attack patterns
    if await detect_ddos_attack():
        await security_team.alert("Potential DDoS attack detected")
    
    # Check for credential stuffing
    if await detect_credential_stuffing():
        await security_team.alert("Potential credential stuffing attack")
    
    # Check for unusual user behavior
    if await detect_unusual_behavior():
        await security_team.alert("Unusual user behavior detected")
```

## Security Best Practices

### 1. Configuration Security

#### Environment-Specific Configuration

**Development:**
```python
# Development configuration
config = SentinelConfig(
    backend="memory",
    default_rate_limit=100,  # Relaxed for testing
    default_rate_window=60,
)
```

**Production:**
```python
# Production configuration
config = SentinelConfig(
    backend="redis",
    redis_url="rediss://user:password@secure-redis.example.com:6380/0",
    redis_prefix="prod_bot:",
    default_rate_limit=10,  # Strict limits
    default_rate_window=60,
    require_registration=True,  # Require registration
)
```

#### Secrets Management

**Environment Variables:**
```bash
# .env file (never commit)
BOT_TOKEN=your_bot_token_here
REDIS_URL=rediss://user:password@redis.example.com:6380/0
SECRET_KEY=your_secret_key_here
```

**Application Code:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

config = SentinelConfig(
    backend="redis",
    redis_url=os.getenv("REDIS_URL"),
    redis_prefix=os.getenv("REDIS_PREFIX", "bot:"),
)
```

### 2. Access Control

#### Role-Based Access Control

```python
async def resolve_user(event, data):
    """Implement role-based access control."""
    user = event.from_user
    
    # Get user role
    user_role = await user_service.get_role(user.id)
    
    # Check permissions
    if user_role == "admin":
        permissions = ["read", "write", "admin"]
    elif user_role == "user":
        permissions = ["read"]
    else:
        permissions = []
    
    return {
        "user_id": user.id,
        "role": user_role,
        "permissions": permissions,
    }
```

#### Command Authorization

```python
@require_registered()
async def admin_command(message: Message):
    """Admin-only command with authorization check."""
    user_context = message.conf.get("user_context", {})
    
    if "admin" not in user_context.get("permissions", []):
        await message.answer("❌ Access denied. Admin privileges required.")
        return
    
    # Admin command logic
    await message.answer("✅ Admin command executed.")
```

### 3. Incident Response

#### Security Incident Handling

```python
async def handle_security_incident(incident_type: str, user_id: int, details: dict):
    """Handle security incidents."""
    # Log incident
    await security_log("incident", user_id, {
        "type": incident_type,
        "details": details,
        "timestamp": time.time(),
    })
    
    # Immediate response
    if incident_type == "ddos_attack":
        # Block attacking IPs
        await block_attacking_ips(details.get("ip_addresses", []))
    
    elif incident_type == "credential_stuffing":
        # Lock affected accounts
        await lock_user_account(user_id)
    
    # Notify security team
    await security_team.notify(incident_type, user_id, details)
    
    # Update threat intelligence
    await threat_intelligence.update(incident_type, details)
```

#### Recovery Procedures

```python
async def recover_from_incident(incident_id: str):
    """Recover from security incident."""
    # Get incident details
    incident = await security_log.get_incident(incident_id)
    
    # Restore affected services
    if incident["type"] == "rate_limit_bypass":
        # Reset rate limits
        await reset_rate_limits(incident["affected_users"])
    
    # Update security measures
    await update_security_measures(incident)
    
    # Document lessons learned
    await document_lessons_learned(incident)
```

## Compliance

### 1. Data Privacy

#### GDPR Compliance

**Data Minimization:**
- Only collect necessary user data
- Implement data retention policies
- Provide data deletion capabilities

**User Rights:**
```python
async def handle_data_request(user_id: int, request_type: str):
    """Handle GDPR data requests."""
    if request_type == "access":
        # Provide user data
        user_data = await get_user_data(user_id)
        return user_data
    
    elif request_type == "deletion":
        # Delete user data
        await delete_user_data(user_id)
        return {"status": "deleted"}
    
    elif request_type == "portability":
        # Export user data
        user_data = await export_user_data(user_id)
        return user_data
```

#### CCPA Compliance

**California Consumer Privacy Act:**
- Implement opt-out mechanisms
- Provide data disclosure
- Respect deletion requests

### 2. Security Standards

#### OWASP Top 10

**Protection Against:**
- Injection attacks (input validation)
- Broken authentication (user validation)
- Sensitive data exposure (data minimization)
- XML external entities (input sanitization)
- Broken access control (role-based access)
- Security misconfiguration (secure defaults)
- Cross-site scripting (input sanitization)
- Insecure deserialization (data validation)
- Using components with known vulnerabilities (dependency management)
- Insufficient logging and monitoring (comprehensive logging)

#### ISO 27001

**Information Security Management:**
- Implement security policies
- Regular security assessments
- Incident response procedures
- Continuous improvement

## Security Checklist

### Pre-Production

- [ ] Configure secure Redis connection with SSL
- [ ] Implement proper secrets management
- [ ] Set appropriate rate limits
- [ ] Configure security logging
- [ ] Implement user authentication
- [ ] Set up monitoring and alerting
- [ ] Test security measures
- [ ] Document security procedures

### Production

- [ ] Monitor security metrics
- [ ] Regular security audits
- [ ] Update dependencies
- [ ] Review access logs
- [ ] Test incident response procedures
- [ ] Backup security configurations
- [ ] Train team on security procedures
- [ ] Regular security assessments

### Ongoing

- [ ] Monitor for new threats
- [ ] Update security measures
- [ ] Review and update policies
- [ ] Conduct security training
- [ ] Perform penetration testing
- [ ] Update incident response procedures
- [ ] Review compliance requirements
- [ ] Document security improvements

## Security Resources

### Documentation

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [ISO 27001](https://www.iso.org/isoiec-27001-information-security.html)

### Tools

- [Redis Security](https://redis.io/docs/management/security/)
- [Telegram Bot API Security](https://core.telegram.org/bots/security)
- [Python Security](https://python-security.readthedocs.io/)

### Communities

- [OWASP Community](https://owasp.org/community/)
- [Python Security](https://python-security.readthedocs.io/)
- [Telegram Bot Development](https://t.me/BotDevelopment)
